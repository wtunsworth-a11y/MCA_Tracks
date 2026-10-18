"""Pull just the KML out of a huge KMZ in Drive, without downloading the photos.

    export GOOGLE_OAUTH_TOKEN='ya29....'
    python3 scripts/fetch_kmz_member.py <driveFileId> [destdir]

A KMZ is a ZIP: a small doc.kml holding the placemarks, and a files/ folder
holding the JPEGs. In the waypoint drop of 18 Oct 2026 the photos are about
1.81 GB and the KML is a rounding error on that, so downloading the archive to
get at the KML wastes the whole plateau's bandwidth and fills the container.

The Drive API honours HTTP Range on alt=media, and a ZIP's index lives at the
END of the file, so the whole thing can be done in three ranged requests:

    1. the last 64 KB          -> find the End Of Central Directory record
    2. the central directory   -> every member's name, size and offset
    3. the member itself       -> inflate it

Typically a few hundred KB moved instead of 1.81 GB. The photos stay in Drive,
which is where they belong: they are over GitHub's blob limit many times over
and they carry precise settlement locations.

The token is read from the environment and never written to disk.
Get one at https://developers.google.com/oauthplayground/ with scope
https://www.googleapis.com/auth/drive.readonly — it lasts about an hour.
"""
import os
import struct
import sys
import urllib.error
import urllib.request
import zlib
from pathlib import Path

API = "https://www.googleapis.com/drive/v3/files/{}?alt=media"

EOCD_SIG = b"PK\x05\x06"
EOCD64_LOC_SIG = b"PK\x06\x07"
EOCD64_SIG = b"PK\x06\x06"
CEN_SIG = b"PK\x01\x02"


def token():
    t = os.environ.get("GOOGLE_OAUTH_TOKEN", "").strip()
    if not t:
        sys.exit("set GOOGLE_OAUTH_TOKEN first - see the module docstring")
    return t


def get_range(url, tok, start, end=None):
    """Bytes [start, end] inclusive; a negative start means 'last N bytes'."""
    rng = f"bytes={start}" if start < 0 else f"bytes={start}-{'' if end is None else end}"
    req = urllib.request.Request(url, headers={
        "Authorization": f"Bearer {tok}",
        "Range": rng,
    })
    try:
        with urllib.request.urlopen(req, timeout=300) as r:
            return r.read(), r.headers.get("Content-Range", "")
    except urllib.error.HTTPError as e:
        body = e.read()[:300].decode("utf-8", "replace")
        sys.exit(f"HTTP {e.code} on {rng}\n{body}")


def total_size(content_range):
    # "bytes 123-456/1805765146"
    if "/" in content_range:
        tail = content_range.rsplit("/", 1)[1].strip()
        if tail.isdigit():
            return int(tail)
    return None


def find_directory(url, tok):
    """-> (central directory offset, size, entry count)."""
    tail, crange = get_range(url, tok, -65557)      # max EOCD + comment
    size = total_size(crange)
    i = tail.rfind(EOCD_SIG)
    if i < 0:
        sys.exit("no End Of Central Directory found - not a ZIP/KMZ?")
    count, cd_size, cd_off = struct.unpack("<HLL", tail[i + 10:i + 20])

    # ZIP64 when any field is saturated.
    if cd_off == 0xFFFFFFFF or cd_size == 0xFFFFFFFF or count == 0xFFFF:
        j = tail.rfind(EOCD64_LOC_SIG)
        if j < 0:
            sys.exit("ZIP64 expected but no locator found")
        eocd64_off = struct.unpack("<Q", tail[j + 8:j + 16])[0]
        blob, _ = get_range(url, tok, eocd64_off, eocd64_off + 55)
        if not blob.startswith(EOCD64_SIG):
            sys.exit("ZIP64 EOCD signature missing")
        count, cd_size, cd_off = struct.unpack("<QQQ", blob[32:56])
    return cd_off, cd_size, count, size


def members(url, tok, cd_off, cd_size):
    blob, _ = get_range(url, tok, cd_off, cd_off + cd_size - 1)
    out, p = [], 0
    while p + 46 <= len(blob) and blob[p:p + 4] == CEN_SIG:
        method, = struct.unpack("<H", blob[p + 10:p + 12])
        csize, usize = struct.unpack("<LL", blob[p + 20:p + 28])
        nlen, elen, clen = struct.unpack("<HHH", blob[p + 28:p + 34])
        lho, = struct.unpack("<L", blob[p + 42:p + 46])
        name = blob[p + 46:p + 46 + nlen].decode("utf-8", "replace")
        extra = blob[p + 46 + nlen:p + 46 + nlen + elen]

        # ZIP64 extra field carries the real sizes/offset when saturated.
        if 0xFFFFFFFF in (csize, usize, lho) and extra:
            q = 0
            while q + 4 <= len(extra):
                hid, hsz = struct.unpack("<HH", extra[q:q + 4])
                if hid == 0x0001:
                    vals, r = [], q + 4
                    for cur in (usize, csize, lho):
                        if cur == 0xFFFFFFFF and r + 8 <= q + 4 + hsz:
                            vals.append(struct.unpack("<Q", extra[r:r + 8])[0])
                            r += 8
                        else:
                            vals.append(cur)
                    usize, csize, lho = vals
                    break
                q += 4 + hsz
        out.append(dict(name=name, method=method, csize=csize, usize=usize, lho=lho))
        p += 46 + nlen + elen + clen
    return out


def fetch_member(url, tok, m):
    # The local header repeats the name and may have a different extra length,
    # so read it rather than trusting the central directory's.
    head, _ = get_range(url, tok, m["lho"], m["lho"] + 29)
    nlen, elen = struct.unpack("<HH", head[26:30])
    start = m["lho"] + 30 + nlen + elen
    raw, _ = get_range(url, tok, start, start + m["csize"] - 1)
    if m["method"] == 0:
        return raw
    if m["method"] == 8:
        return zlib.decompress(raw, -zlib.MAX_WBITS)
    sys.exit(f'unsupported compression method {m["method"]} for {m["name"]}')


def main():
    if len(sys.argv) < 2:
        sys.exit(__doc__)
    file_id = sys.argv[1]
    dest = Path(sys.argv[2] if len(sys.argv) > 2 else "data/raw/waypoints")
    url, tok = API.format(file_id), token()

    cd_off, cd_size, count, size = find_directory(url, tok)
    print(f"archive {size:,} bytes, {count} members, index at {cd_off:,}")

    entries = members(url, tok, cd_off, cd_size)
    kml = [m for m in entries if m["name"].lower().endswith((".kml", ".xml"))]
    other = len(entries) - len(kml)
    print(f"  {len(kml)} KML/XML member(s), {other} other file(s) left in Drive")
    if not kml:
        sys.exit("no KML inside the archive")

    dest.mkdir(parents=True, exist_ok=True)
    moved = 0
    for m in kml:
        data = fetch_member(url, tok, m)
        out = dest / Path(m["name"]).name
        out.write_bytes(data)
        moved += m["csize"]
        print(f'  {m["name"]} -> {out}  ({len(data):,} bytes)')

    saved = (size - moved) / size * 100 if size else 0
    print(f"moved ~{moved:,} bytes instead of {size:,} - {saved:.2f}% left in Drive")


if __name__ == "__main__":
    main()
