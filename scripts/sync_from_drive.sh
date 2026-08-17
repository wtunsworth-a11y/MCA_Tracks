#!/usr/bin/env bash
#
# Run this ON YOUR OWN MACHINE (not in the Claude sandbox, which has no network
# route to Google Drive). It pulls only new or changed track files from the
# Drive folder into data/raw, then commits and pushes them.
#
# ---------------------------------------------------------------------------
# One-time setup
# ---------------------------------------------------------------------------
#   1. Install rclone:            https://rclone.org/install/
#   2. Authorise it to Drive:     rclone config
#        - "n" for new remote, name it  gdrive
#        - storage type:              drive
#        - leave client_id/secret blank, scope 1 (full) or 2 (read-only)
#        - say yes to the browser login, accept the defaults otherwise
#   3. Check it can see the folder:
#        rclone lsl gdrive: --drive-root-folder-id 1UR9_fpkrn_I2lCs8O2yZsC7u9xCv1bsy
#
# Already using Google Drive for Desktop? Skip rclone entirely — set
# LOCAL_DRIVE_PATH below to the synced folder and this uses rsync instead.
#
# ---------------------------------------------------------------------------
# Usage
# ---------------------------------------------------------------------------
#   ./scripts/sync_from_drive.sh            # sync, commit and push
#   ./scripts/sync_from_drive.sh --dry-run  # show what would change, do nothing
#
set -euo pipefail

DRIVE_FOLDER_ID="1UR9_fpkrn_I2lCs8O2yZsC7u9xCv1bsy"
REMOTE="gdrive:"
BRANCH="claude/managalas-track-maps-3xd3bq"

# Set this to your Drive-for-Desktop path to bypass rclone, e.g.
#   LOCAL_DRIVE_PATH="$HOME/Library/CloudStorage/GoogleDrive-you@gmail.com/My Drive/MCA_Tracks"
LOCAL_DRIVE_PATH="${LOCAL_DRIVE_PATH:-}"

# Files above this size are skipped: GitHub hard-rejects blobs over 100 MB.
MAX_BYTES=$((95 * 1024 * 1024))

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DEST="$REPO_ROOT/data/raw"
DRY_RUN=""
[[ "${1:-}" == "--dry-run" ]] && DRY_RUN="--dry-run"

mkdir -p "$DEST"

echo "==> Syncing track files into $DEST"

# --max-size keeps the oversized KMZ out of git; --ignore-existing is NOT used,
# so genuinely updated files still come across.
COMMON_ARGS=(
  --include "*.gpx" --include "*.kmz" --include "*.kml" --include "*.gpkg"
  --max-size "${MAX_BYTES}b"
  --progress
)

if [[ -n "$LOCAL_DRIVE_PATH" ]]; then
  echo "    source: local Drive folder ($LOCAL_DRIVE_PATH)"
  [[ -d "$LOCAL_DRIVE_PATH" ]] || { echo "!! not a directory: $LOCAL_DRIVE_PATH" >&2; exit 1; }
  rclone copy "$LOCAL_DRIVE_PATH" "$DEST" "${COMMON_ARGS[@]}" ${DRY_RUN:+--dry-run}
else
  command -v rclone >/dev/null || { echo "!! rclone not installed — see the header of this script" >&2; exit 1; }
  echo "    source: $REMOTE (folder id $DRIVE_FOLDER_ID)"
  rclone copy "$REMOTE" "$DEST" \
    --drive-root-folder-id "$DRIVE_FOLDER_ID" \
    "${COMMON_ARGS[@]}" ${DRY_RUN:+--dry-run}
fi

if [[ -n "$DRY_RUN" ]]; then
  echo "==> Dry run only; nothing copied or committed."
  exit 0
fi

# Warn about anything too big to have come across, so it is never a silent gap.
echo
echo "==> Checking for files skipped as too large"
if [[ -n "$LOCAL_DRIVE_PATH" ]]; then
  find "$LOCAL_DRIVE_PATH" -maxdepth 1 -type f -size +${MAX_BYTES}c -printf "    SKIPPED (too big for git): %f  %s bytes\n" 2>/dev/null || true
else
  rclone lsl "$REMOTE" --drive-root-folder-id "$DRIVE_FOLDER_ID" --min-size "${MAX_BYTES}b" 2>/dev/null \
    | awk '{ $1=$1; print "    SKIPPED (too big for git):", $NF, "-", $1, "bytes" }' || true
fi

cd "$REPO_ROOT"
git add -A data/raw

if git diff --cached --quiet; then
  echo
  echo "==> Nothing new — data/raw already matches Drive."
  exit 0
fi

echo
echo "==> Staged changes:"
git diff --cached --name-status data/raw

git commit -m "Sync track files from Google Drive"
git push -u origin "$BRANCH"

echo
echo "==> Pushed. Tell Claude to pull and re-run the pipeline."
