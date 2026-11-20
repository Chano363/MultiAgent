"""Guards for the upload-provenance chain (diagnostics 19.34-C/D, 2026-11-20).

Two real defects were found after the W4 window:

C) Cloud metadata.git_commit pointed at the WRONG code.
   rsync excludes .git/, so the cloud repo keeps a stale .git from the image /
   previous deployment. `git rev-parse HEAD` there returns that stale commit
   (measured: 154c1b8, which does NOT contain the ADR-081 mechanism) while the
   code actually executed came from the current worktree (dcbe214 branch).
   metadata therefore claimed a code version that was not running -> violates
   red line 5 (authoritative metadata) and misleads any later audit.
   Fix = write .git_commit (local HEAD) at upload time and make
   src/metadata.py prefer it over `git rev-parse HEAD`.

D) The reference speed table lives under outputs/, which rsync excludes, so the
   cloud silently used whatever copy the image happened to have. The table is an
   evaluation INPUT (it gates the AB backstop penalty, not just the reward), so
   a mismatched copy means train/eval are not same-source.
   Fix = stage npz + meta into .upload_payload/ and verify the md5 on the cloud
   side at boot.

These tests lock both fixes so a later edit cannot silently drop them.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
METADATA_PY = ROOT / "src" / "metadata.py"
PREPARE_SH = ROOT / "scripts" / "cloud" / "prepare_upload.sh"
BOOTSTRAP_SH = ROOT / "scripts" / "cloud" / "instance_bootstrap.sh"


def test_metadata_prefers_uploaded_git_commit_file():
    """.git_commit is the authoritative "what was actually uploaded" anchor.
    If git rev-parse HEAD were consulted first, the cloud would report the
    stale deployment commit again."""
    src = METADATA_PY.read_text(encoding="utf-8")
    fn = src.split("def git_commit(", 1)[1].split("\ndef ", 1)[0]
    # strip the docstring so mentions inside prose do not count as code order
    body = fn.split('"""', 2)[-1] if fn.count('"""') >= 2 else fn
    i_file = body.find(".git_commit")
    i_revparse = body.find("rev-parse")
    assert i_file != -1, "git_commit() no longer reads .git_commit"
    assert i_revparse != -1, "git_commit() lost the git rev-parse fallback"
    assert i_file < i_revparse, (
        "git_commit() must read .git_commit BEFORE git rev-parse "
        "(the cloud .git is a stale deployment leftover)")


def test_prepare_upload_script_exists_and_writes_git_commit():
    assert PREPARE_SH.is_file(), "scripts/cloud/prepare_upload.sh missing"
    src = PREPARE_SH.read_text(encoding="utf-8")
    assert ".git_commit" in src
    assert "rev-parse HEAD" in src
    assert ".upload_payload" in src
    assert "ref_speed_table.npz" in src
    # the ref table pair must travel together (env validates npz + meta)
    assert "ref_speed_meta.json" in src
    assert "MANIFEST.txt" in src


def test_bootstrap_verifies_upload_provenance_on_cloud():
    """The cloud side must VERIFY, not just receive: manifest md5 vs the ref
    table actually on disk, plus the .git_commit label."""
    src = BOOTSTRAP_SH.read_text(encoding="utf-8")
    assert ".upload_payload/MANIFEST.txt" in src
    assert "upload_provenance" in src
    assert "ref_table_md5" in src
    assert ".git_commit" in src


def test_bootstrap_has_no_nested_heredoc_python_call():
    """A nested heredoc python call inside $( ) hung the shell (2026-11-20
    observed: prepare_upload.sh produced no output past step 1). Keep the
    python call on one line with -c instead."""
    for p in (PREPARE_SH, BOOTSTRAP_SH):
        src = p.read_text(encoding="utf-8")
        assert "<<'PYEOF'" not in src, f"{p.name} still uses a nested heredoc"
