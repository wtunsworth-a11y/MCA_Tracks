#!/usr/bin/env bash
#
# Fetch every file listed in data/drive_manifest.tsv straight from the Drive API
# into data/raw. The sandbox can reach www.googleapis.com (drive.google.com is
# blocked, the API host is not), so all this needs is an access token.
#
# The token is read from the environment and never written to disk.
#
#   export GOOGLE_OAUTH_TOKEN='ya29....'
#   ./scripts/fetch_from_drive.sh
#
# Get a token: https://developers.google.com/oauthplayground/
#   scope  https://www.googleapis.com/auth/drive.readonly
# It expires in about an hour, which is the point — it is not a stored secret.
#
set -uo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
MANIFEST="$REPO_ROOT/data/drive_manifest.tsv"
DEST="$REPO_ROOT/data/raw"

: "${GOOGLE_OAUTH_TOKEN:?set GOOGLE_OAUTH_TOKEN first — see the header of this script}"
[[ -f "$MANIFEST" ]] || { echo "!! no manifest at $MANIFEST" >&2; exit 1; }

mkdir -p "$DEST"

ok=0; skipped=0; failed=0
declare -a FAILURES=()

# Skip the header, then walk name/size/modified/id.
while IFS=$'\t' read -r name size modified id; do
  [[ "$name" == "name" || -z "${id:-}" ]] && continue

  target="$DEST/$name"
  if [[ -f "$target" && "$(stat -c%s "$target")" == "$size" ]]; then
    skipped=$((skipped + 1))
    continue
  fi

  printf '  fetching %-58s %10s bytes ... ' "$name" "$size"
  code=$(curl -sS -L -m 600 \
    -H "Authorization: Bearer ${GOOGLE_OAUTH_TOKEN}" \
    -o "$target.part" \
    -w '%{http_code}' \
    "https://www.googleapis.com/drive/v3/files/${id}?alt=media" 2>/dev/null)

  got=$(stat -c%s "$target.part" 2>/dev/null || echo 0)

  if [[ "$code" == "200" && "$got" == "$size" ]]; then
    mv "$target.part" "$target"
    echo "ok"
    ok=$((ok + 1))
  else
    # Keep the body around only if it looks like a short error payload.
    if [[ "$code" != "200" ]]; then
      detail="HTTP $code: $(head -c 160 "$target.part" 2>/dev/null | tr -d '\n')"
    else
      detail="size mismatch — got $got, expected $size"
    fi
    rm -f "$target.part"
    echo "FAILED"
    FAILURES+=("$name — $detail")
    failed=$((failed + 1))
  fi
done < "$MANIFEST"

echo
echo "fetched $ok · already present $skipped · failed $failed"

if (( failed )); then
  echo
  echo "Failures:"
  for f in "${FAILURES[@]}"; do echo "  - $f"; done
  exit 1
fi
