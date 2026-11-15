"""Every import in scripts/ must be pinned in requirements.txt.

    python3 scripts/check_requirements.py

Exits non-zero if a script imports something the file does not list, so the
drift is caught by the chain rather than by someone noticing months later.

Will, 15 Nov 2026: "have things like requirements been modified as we moved
forwards?" They had not. A container rebuild wiped the environment and the
audit that followed found three packages in use and unlisted: pyproj in nine
scripts including the two that build the KML layers, pillow in the
map-digitising pair, and folium in make_maps.py.

pyproj and pillow are the instructive ones. They were never missing, because
rasterio and geopandas drag them in, so everything worked while they sat
unpinned - and a pinned geopandas quietly decides their version. That is the
same class of fault requirements.txt was written to prevent.
"""
import ast
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SCRIPTS = ROOT / "scripts"
REQ = ROOT / "requirements.txt"

# Where the import name and the distribution name differ.
ALIAS = {"skimage": "scikit-image", "PIL": "pillow", "yaml": "pyyaml",
         "sklearn": "scikit-learn", "cv2": "opencv-python"}


def norm(name):
    return name.lower().replace("-", "_")


def pinned():
    out = {}
    for line in REQ.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out[norm(re.split(r"[=<>!~]", line)[0].strip())] = line
    return out


def imports():
    stdlib = set(sys.stdlib_module_names)
    local = {p.stem for p in SCRIPTS.glob("*.py")}
    found = {}
    for p in sorted(SCRIPTS.glob("*.py")):
        try:
            tree = ast.parse(p.read_text())
        except SyntaxError as e:
            print(f"!! {p.name} does not parse: {e}", file=sys.stderr)
            return None
        for n in ast.walk(tree):
            if isinstance(n, ast.Import):
                names = [a.name for a in n.names]
            elif isinstance(n, ast.ImportFrom) and n.level == 0 and n.module:
                names = [n.module]
            else:
                continue
            for name in names:
                top = name.split(".")[0]
                if top in stdlib or top in local or top.startswith("_"):
                    continue
                found.setdefault(top, set()).add(p.name)
    return found


def main():
    req, used = pinned(), imports()
    if used is None:
        return 2
    missing = []
    for mod in sorted(used):
        if norm(ALIAS.get(mod, mod)) not in req:
            missing.append((mod, sorted(used[mod])))
    if missing:
        print("NOT PINNED in requirements.txt:")
        for mod, files in missing:
            print(f"  {mod}  <- {', '.join(files)}")
        print("\nAdd each with the version actually installed:")
        print("  python3 -c \"import M; print(M.__version__)\"")
        return 1
    print(f"requirements.txt covers all {len(used)} third-party imports "
          f"across {len(list(SCRIPTS.glob('*.py')))} scripts")
    return 0


if __name__ == "__main__":
    sys.exit(main())
