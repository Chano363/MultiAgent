#!/usr/bin/env bash
# Prepare the upload payload for a cloud training window.
#
# Why this exists (diagnostics 19.34-C/D, 2026-11-20):
#   rsync excludes .git/ and outputs/:
#     1) provenance: the cloud repo keeps a STALE .git (deployment leftover), so
#        `git rev-parse HEAD` there returns an old commit that does NOT contain
#        the current mechanism (measured: metadata.git_commit=154c1b8 while the
#        code actually run came from the dcbe214 worktree) => metadata pointed at
#        the wrong code. Fix: write .git_commit (local HEAD) and make
#        src/metadata.py prefer it.
#     2) reference speed table: env_cfg.speed_ref_table lives under outputs/, which
#        rsync excludes => the cloud silently used whatever copy the image had.
#        Fix: stage the npz + meta into .upload_payload/ (not excluded) so the
#        cloud provably uses the SAME table as the local run.
#
# Usage: bash scripts/cloud/prepare_upload.sh [--config <yaml>]
# Outputs: .git_commit (local HEAD), .upload_payload/ref/<table files>,
#          .upload_payload/MANIFEST.txt (md5 of every staged file)
set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
cd "$ROOT"

CONFIG="configs/experiments/formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml"
while [ $# -gt 0 ]; do
  case "$1" in
    --config) CONFIG="$2"; shift 2;;
    *) echo "unknown arg: $1" >&2; exit 2;;
  esac
done

PY_BIN="${PY:-python3}"

# 1) local HEAD -> .git_commit (authoritative for "what code is actually uploaded")
HEAD_SHA="$(git -C "$ROOT" rev-parse HEAD 2>/dev/null || true)"
if [ -z "$HEAD_SHA" ]; then
  echo "FATAL: cannot resolve local HEAD (run inside the git worktree)" >&2
  exit 3
fi
printf '%s\n' "$HEAD_SHA" > "$ROOT/.git_commit"
echo "[prepare] .git_commit = $HEAD_SHA"

# 1b) worktree fingerprint (content-side anchor, independent of .git labels)
TREE_SHA="$(git -C "$ROOT" rev-parse 'HEAD^{tree}' 2>/dev/null || echo unknown)"
DIRTY="$(git -C "$ROOT" status --porcelain --untracked-files=no 2>/dev/null | wc -l | tr -d ' ')"
echo "[prepare] tree=$TREE_SHA tracked_dirty_files=$DIRTY"

# 2) stage the reference speed table (npz + meta must travel together: the env
#    validates the pair, see train_fleet_env _load_ref_table).
STAGE="$ROOT/.upload_payload"
rm -rf "$STAGE"
mkdir -p "$STAGE/ref"

TMP_JSON="$(mktemp)"
printf '%s' "$CONFIG" > "${TMP_JSON}.cfg"
"$PY_BIN" -c 'import sys,yaml;cfg=yaml.safe_load(open(sys.argv[1],encoding="utf-8")) or {};print(((cfg.get("env_cfg") or {}).get("speed_ref_table") or ""))' "$CONFIG" > "$TMP_JSON" 2>/dev/null || true
REF_PATH="$(cat "$TMP_JSON" 2>/dev/null | tr -d '\r' | head -1)"
rm -f "$TMP_JSON" "${TMP_JSON}.cfg"

if [ -z "$REF_PATH" ]; then
  echo "[prepare] WARN config has no env_cfg.speed_ref_table (nothing to stage)"
elif [ ! -f "$REF_PATH" ]; then
  echo "FATAL: speed_ref_table not found locally: $REF_PATH" >&2
  exit 3
else
  REFDIR="$(dirname "$REF_PATH")"
  cp -f "$REFDIR/ref_speed_table.npz" "$STAGE/ref/" || true
  cp -f "$REFDIR/ref_speed_meta.json" "$STAGE/ref/" || true
  echo "[prepare] staged ref table from $REFDIR"
fi

# 3) manifest with md5 of everything staged
{
  echo "git_commit=$HEAD_SHA"
  echo "git_tree=$TREE_SHA"
  echo "tracked_dirty_files=$DIRTY"
  echo "staged_at=$(date -Is)"
  echo "--- md5 ---"
  for f in $(cd "$STAGE" && find . -type f | sort); do
    md5sum "$STAGE/$f" 2>/dev/null || true
  done
} > "$STAGE/MANIFEST.txt"
echo "[prepare] manifest written:"
head -8 "$STAGE/MANIFEST.txt"
echo "[prepare] DONE"
