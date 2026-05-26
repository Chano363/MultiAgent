#!/usr/bin/env python3
"""Minimal local skills store CLI.

Features:
- Reads a local index JSON from file:// URI (or plain path).
- Search skills by keyword.
- Install a skill zip into a target directory.
- List locally installed skills from a lock file.
- Upgrade installed skills from update manifest defined in skill config.json.
- Self-upgrade the CLI binary/script from an update manifest URL in config.json.
"""

import argparse
import hashlib
import json
import os
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request
import zipfile
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from skills_upgrade import cmd_upgrade as run_skills_upgrade


DEFAULT_INSTALL_ROOT = "./skills"
LOCKFILE_NAME = ".skills_store_lock.json"
SKILL_CONFIG_NAME = "config.json"
SKILL_META_NAME = "_meta.json"
CLI_CONFIG_NAME = "config.json"
CLI_VERSION_FILE_NAME = "version.json"
CLI_METADATA_FILE_NAME = "metadata.json"
CLI_VERSION_FALLBACK = "2026.3.3"
DEFAULT_INDEX_URI_FALLBACK = "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/skills.json"
DEFAULT_SEARCH_URL_FALLBACK = "https://api.skillhub.cn/api/v1/search"
SELF_UPGRADE_CHECK_TIMEOUT_SECONDS = 2
DEFAULT_CLI_HOME = "~/.skillhub"
SELF_UPGRADE_REEXEC_ENV = "SKILLHUB_SELF_UPGRADE_REEXEC"
SKIP_SELF_UPGRADE_ENV = "SKILLHUB_SKIP_SELF_UPGRADE"
SKIP_WORKSPACE_SKILLS_ENV = "SKILLHUB_SKIP_WORKSPACE_SKILLS"
DEFAULT_SELF_UPDATE_MANIFEST_URL_FALLBACK = "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/version.json"
DEFAULT_SKILLS_DOWNLOAD_URL_TEMPLATE_FALLBACK = (
    "https://skillhub-1388575217.cos.ap-guangzhou.myqcloud.com/skills/{slug}.zip"
)
DEFAULT_PRIMARY_DOWNLOAD_URL_TEMPLATE_FALLBACK = (
    "https://api.skillhub.cn/api/v1/download?slug={slug}"
)
DEFAULT_OPENCLAW_CONFIG_PATH = "~/.openclaw/openclaw.json"
DEFAULT_OPENCLAW_WORKSPACE_PATH = "~/.openclaw/workspace"
DEFAULT_OPENCLAW_PLUGIN_DIR = "~/.openclaw/extensions/skillhub"
POST_UPGRADE_SKILL_MIGRATION_MIN_VERSION = (3, 13)
FIND_SKILLS_SLUG = "find-skills"
SKILLHUB_PREFERENCE_SLUG = "skillhub-preference"


def load_cli_version(base_dir: Path) -> str:
    version_path = base_dir / CLI_VERSION_FILE_NAME
    if not version_path.exists():
        return CLI_VERSION_FALLBACK
    try:
        raw = json.loads(version_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return CLI_VERSION_FALLBACK
    if not isinstance(raw, dict):
        return CLI_VERSION_FALLBACK
    value = raw.get("version")
    if isinstance(value, str) and value.strip():
        return value.strip()
    return CLI_VERSION_FALLBACK


def load_cli_metadata(base_dir: Path) -> Dict[str, str]:
    metadata_path = base_dir / CLI_METADATA_FILE_NAME
    if not metadata_path.exists():
        return {}
    try:
        raw = json.loads(metadata_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {}
    if not isinstance(raw, dict):
        return {}
    out: Dict[str, str] = {}
    for key in (
        "skills_index_url",
        "skills_download_url_template",
        "self_update_manifest_url",
        "skills_search_url",
        "skills_primary_download_url_template",
    ):
        value = raw.get(key)
        if isinstance(value, str) and value.strip():
            out[key] = value.strip()
    return out


CLI_VERSION = load_cli_version(Path(__file__).resolve().parent)
CLI_METADATA = load_cli_metadata(Path(__file__).resolve().parent)
DEFAULT_INDEX_URI = CLI_METADATA.get("skills_index_url", DEFAULT_INDEX_URI_FALLBACK)
DEFAULT_SELF_UPDATE_MANIFEST_URL = CLI_METADATA.get(
    "self_update_manifest_url",
    DEFAULT_SELF_UPDATE_MANIFEST_URL_FALLBACK,
)
DEFAULT_SKILLS_DOWNLOAD_URL_TEMPLATE = CLI_METADATA.get(
    "skills_download_url_template",
    DEFAULT_SKILLS_DOWNLOAD_URL_TEMPLATE_FALLBACK,
)
DEFAULT_SEARCH_URL = os.environ.get("SKILLHUB_SEARCH_URL", "").strip() or CLI_METADATA.get(
    "skills_search_url",
    DEFAULT_SEARCH_URL_FALLBACK,
)
DEFAULT_PRIMARY_DOWNLOAD_URL_TEMPLATE = (
    os.environ.get("SKILLHUB_PRIMARY_DOWNLOAD_URL_TEMPLATE", "").strip()
    or CLI_METADATA.get(
        "skills_primary_download_url_template",
        DEFAULT_PRIMARY_DOWNLOAD_URL_TEMPLATE_FALLBACK,
    )
)
CLI_USER_AGENT = f"skills-store-cli/{CLI_VERSION}"


def verbose_enabled() -> bool:
    return os.environ.get("LOG", "") == "VERBOSE"


def verbose_log(message: str) -> None:
    if verbose_enabled():
        print(f"[self-upgrade][verbose] {message}")


def die(message: str, code: int = 1) -> None:
    print(f"Error: {message}", file=sys.stderr)
    raise SystemExit(code)


def normalize_file_uri(uri_or_path: str) -> Path:
    parsed = urllib.parse.urlparse(uri_or_path)
    if parsed.scheme == "file":
        # Support:
        # - file:///abs/path
        # - file://localhost/abs/path
        # - file://./relative/path
        if parsed.netloc in ("", "localhost"):
            combined = parsed.path
        else:
            combined = f"{parsed.netloc}{parsed.path}"

        raw_path = urllib.request.url2pathname(combined)
        if not raw_path.strip():
            die(f"Invalid file URI: {uri_or_path}")
        candidate = Path(raw_path).expanduser()
        if not candidate.is_absolute():
            candidate = Path.cwd() / candidate
        return candidate.resolve()
    if parsed.scheme:
        die(f"Only file:// is supported for --index. Got: {uri_or_path}")
    return Path(uri_or_path).expanduser().resolve()


def parse_path_like_uri(uri_or_path: str) -> Path:
    parsed = urllib.parse.urlparse(uri_or_path)
    if parsed.scheme == "file":
        return normalize_file_uri(uri_or_path)
    if parsed.scheme:
        die(f"Only file:// or local paths are supported here. Got: {uri_or_path}")
    return Path(uri_or_path).expanduser().resolve()


def append_slug_zip(base_uri_or_path: str, slug: str) -> str:
    base = base_uri_or_path.strip()
    if not base:
        return ""
    if "{slug}" in base:
        return base.replace("{slug}", urllib.parse.quote(slug))
    parsed = urllib.parse.urlparse(base)
    suffix = f"{urllib.parse.quote(slug)}.zip"
    if parsed.scheme in ("http", "https"):
        return urllib.parse.urljoin(base.rstrip("/") + "/", suffix)
    base_path = parse_path_like_uri(base)
    return (base_path / f"{slug}.zip").resolve().as_uri()


def fill_slug_template(url_template: str, slug: str) -> str:
    raw = str(url_template or "").strip()
    if not raw:
        return ""
    if "{slug}" not in raw:
        return raw
    return raw.replace("{slug}", urllib.parse.quote(slug))


def read_json_from_uri(uri_or_path: str, timeout: int = 20) -> Dict[str, Any]:
    parsed = urllib.parse.urlparse(uri_or_path)
    if parsed.scheme in ("", "file"):
        path = parse_path_like_uri(uri_or_path)
        if not path.exists():
            raise RuntimeError(f"JSON source not found: {path}")
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON in {path}: {exc}") from exc
    elif parsed.scheme in ("http", "https"):
        req = urllib.request.Request(
            uri_or_path,
            headers={
                "User-Agent": CLI_USER_AGENT,
                "Accept": "application/json",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=timeout) as response:
                payload = response.read().decode("utf-8")
                raw = json.loads(payload)
        except urllib.error.HTTPError as exc:
            raise RuntimeError(f"Failed to fetch JSON ({exc.code}) from {uri_or_path}") from exc
        except urllib.error.URLError as exc:
            raise RuntimeError(f"Failed to fetch JSON from {uri_or_path}: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Invalid JSON from {uri_or_path}: {exc}") from exc
    else:
        raise RuntimeError(f"Unsupported URI scheme for JSON source: {uri_or_path}")

    if not isinstance(raw, dict):
        raise RuntimeError(f"JSON source must be an object: {uri_or_path}")
    return raw


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def first_non_empty_string(obj: Dict[str, Any], keys: List[str]) -> str:
    for key in keys:
        value = obj.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return ""


def normalize_version_text(v: str) -> str:
    return v.strip()


def parse_version_key(version: str) -> Optional[Tuple[int, ...]]:
    raw = version.strip().lower()
    if raw.startswith("v"):
        raw = raw[1:]
    if not raw:
        return None
    core = raw.split("-", 1)[0].split("+", 1)[0]
    parts = core.split(".")
    out: List[int] = []
    for part in parts:
        if not part.isdigit():
            return None
        out.append(int(part))
    return tuple(out) if out else None


def version_is_newer(candidate: str, current: str) -> bool:
    candidate = candidate.strip()
    current = current.strip()
    if not candidate:
        return False
    if not current:
        return True
    a = parse_version_key(candidate)
    b = parse_version_key(current)
    if a is not None and b is not None:
        return a > b
    return candidate != current


def parse_bool_like(value: Any) -> Optional[bool]:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return bool(value)
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in ("1", "true", "yes", "on"):
            return True
        if normalized in ("0", "false", "no", "off"):
            return False
    return None


def self_update_url_from_config(config: Dict[str, Any]) -> str:
    direct = first_non_empty_string(
        config,
        ["self_update_url", "selfUpdateUrl", "update_url", "updateUrl", "manifest_url", "manifestUrl"],
    )
    if direct:
        return direct

    for key in ("self_update", "selfUpdate", "update", "upgrade"):
        nested = as_dict(config.get(key))
        url_value = first_non_empty_string(nested, ["url", "uri", "manifest", "manifest_url", "manifestUrl"])
        if url_value:
            return url_value
    return ""


def self_update_enabled_from_config(config: Dict[str, Any]) -> Optional[bool]:
    for key in ("auto_self_upgrade", "autoSelfUpgrade", "self_update_auto", "selfUpdateAuto"):
        parsed = parse_bool_like(config.get(key))
        if parsed is not None:
            return parsed

    for key in ("self_update", "selfUpdate", "update", "upgrade"):
        nested = as_dict(config.get(key))
        for nested_key in ("auto", "enabled", "auto_upgrade", "autoUpgrade", "enabled_auto_upgrade"):
            parsed = parse_bool_like(nested.get(nested_key))
            if parsed is not None:
                return parsed
    return None


def resolve_self_update_manifest_url(config_path: Path) -> str:
    if config_path.exists():
        verbose_log(f"reading config: {config_path}")
        try:
            raw = json.loads(config_path.read_text(encoding="utf-8"))
        except json.JSONDecodeError:
            verbose_log("config JSON invalid; fallback to default manifest URL")
            raw = {}
        if isinstance(raw, dict):
            manifest_url_raw = self_update_url_from_config(raw)
            if manifest_url_raw:
                verbose_log(f"manifest URL from config: {manifest_url_raw}")
                return resolve_uri_with_base(manifest_url_raw, config_path.parent)
    else:
        verbose_log(f"config not found: {config_path}; use default manifest URL")
    verbose_log(f"using default manifest URL: {DEFAULT_SELF_UPDATE_MANIFEST_URL}")
    return DEFAULT_SELF_UPDATE_MANIFEST_URL


def should_run_startup_self_upgrade(config_path: Path) -> bool:
    env_override = parse_bool_like(os.environ.get(SKIP_SELF_UPGRADE_ENV, ""))
    if env_override is True:
        verbose_log(f"startup check skipped by env {SKIP_SELF_UPGRADE_ENV}=true")
        return False
    if not config_path.exists():
        return True
    try:
        raw = json.loads(config_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        verbose_log("startup check: config JSON invalid; keep default auto upgrade")
        return True
    if isinstance(raw, dict):
        enabled = self_update_enabled_from_config(raw)
        if enabled is False:
            verbose_log("startup check skipped by config auto_self_upgrade=false")
            return False
    return True


def find_cli_script_in_extracted(root: Path) -> Optional[Path]:
    direct = root / "skills_store_cli.py"
    if direct.exists():
        return direct
    nested = root / "cli" / "skills_store_cli.py"
    if nested.exists():
        return nested
    matches = list(root.rglob("skills_store_cli.py"))
    return matches[0] if matches else None


def find_peer_file_in_extracted(root: Path, filename: str) -> Optional[Path]:
    direct = root / filename
    if direct.exists():
        return direct
    nested = root / "cli" / filename
    if nested.exists():
        return nested
    matches = list(root.rglob(filename))
    return matches[0] if matches else None


def find_skill_file_in_extracted(root: Path, filename: str) -> Optional[Path]:
    direct = root / "skill" / filename
    if direct.exists():
        return direct
    nested = root / "cli" / "skill" / filename
    if nested.exists():
        return nested
    for match in root.rglob(filename):
        if match.parent.name == "skill":
            return match
    return None


def version_at_least(version: str, minimum: Tuple[int, ...]) -> bool:
    parsed = parse_version_key(version)
    if parsed is None:
        return False
    return parsed >= minimum


def resolve_openclaw_config_path() -> Path:
    override = os.environ.get("OPENCLAW_CONFIG_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(DEFAULT_OPENCLAW_CONFIG_PATH).expanduser().resolve()


def resolve_skillhub_config_path() -> Path:
    override = os.environ.get("SKILLHUB_CONFIG_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path(f"{DEFAULT_CLI_HOME}/{CLI_CONFIG_NAME}").expanduser().resolve()


def read_json_object(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return {}
    if not isinstance(raw, dict):
        return {}
    return raw


def should_install_workspace_skills() -> bool:
    env_override = parse_bool_like(os.environ.get(SKIP_WORKSPACE_SKILLS_ENV, ""))
    if env_override is True:
        verbose_log(f"workspace skills install skipped by env {SKIP_WORKSPACE_SKILLS_ENV}=true")
        return False
    if env_override is False:
        return True

    config = read_json_object(resolve_skillhub_config_path())
    configured = parse_bool_like(config.get("install_workspace_skills"))
    if configured is not None:
        return configured
    return True


def openclaw_config_has_skillhub_entry(config: Dict[str, Any]) -> bool:
    plugins = as_dict(config.get("plugins"))
    entries = as_dict(plugins.get("entries"))
    return "skillhub" in entries


def skillhub_plugin_dir_present() -> bool:
    plugin_dir = Path(DEFAULT_OPENCLAW_PLUGIN_DIR).expanduser().resolve()
    if not plugin_dir.exists() or not plugin_dir.is_dir():
        return False
    try:
        next(plugin_dir.iterdir())
        return True
    except StopIteration:
        return False
    except Exception:
        return False


def detect_skillhub_plugin_behavior(config_path: Path) -> Tuple[bool, Dict[str, Any]]:
    config = read_json_object(config_path)
    config_has_entry = openclaw_config_has_skillhub_entry(config)
    plugin_dir_exists = skillhub_plugin_dir_present()
    return plugin_dir_exists or config_has_entry, config


def resolve_openclaw_bin() -> str:
    from_path = shutil.which("openclaw")
    if from_path:
        return from_path
    fallback = Path("~/.local/share/pnpm/openclaw").expanduser().resolve()
    if fallback.exists() and os.access(fallback, os.X_OK):
        return str(fallback)
    return ""


def disable_skillhub_plugin_via_openclaw(openclaw_bin: str) -> bool:
    if not openclaw_bin:
        return False
    try:
        result = subprocess.run(
            [openclaw_bin, "config", "unset", "plugins.entries.skillhub"],
            check=False,
            capture_output=True,
            text=True,
        )
    except Exception as exc:
        verbose_log(f"disable plugin by openclaw failed: {exc}")
        return False
    if result.returncode == 0:
        verbose_log("removed skillhub plugin config via openclaw config unset")
        return True
    err = (result.stderr or result.stdout or "").strip()
    if "config path not found" in err.lower():
        verbose_log("skillhub plugin config already absent")
        return True
    if err:
        verbose_log(f"openclaw config unset failed: {err}")
    return False


def resolve_openclaw_workspace_path(config: Dict[str, Any]) -> Path:
    env_workspace = os.environ.get("OPENCLAW_WORKSPACE", "").strip()
    if env_workspace:
        return Path(env_workspace).expanduser().resolve()

    for key in ("workspace", "workspace_dir", "workspaceDir", "workspace_path", "workspacePath"):
        value = config.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value.strip()).expanduser().resolve()

    paths = as_dict(config.get("paths"))
    for key in ("workspace", "workspaceDir", "workspace_path", "workspacePath"):
        value = paths.get(key)
        if isinstance(value, str) and value.strip():
            return Path(value.strip()).expanduser().resolve()

    return Path(DEFAULT_OPENCLAW_WORKSPACE_PATH).expanduser().resolve()


def read_skill_template(template_path: Optional[Path]) -> str:
    if template_path and template_path.exists():
        try:
            content = template_path.read_text(encoding="utf-8").strip()
            if content:
                return content
        except Exception:
            pass
    return ""


def install_workspace_skill(workspace_path: Path, slug: str, content: str) -> Path:
    target = workspace_path / "skills" / slug / "SKILL.md"
    target.parent.mkdir(parents=True, exist_ok=True)
    payload = content if content.endswith("\n") else (content + "\n")
    target.write_text(payload, encoding="utf-8")
    return target


def run_post_upgrade_plugin_migration(
    latest_version: str,
    find_skill_template: Optional[Path],
    preference_skill_template: Optional[Path],
) -> None:
    # This migration belongs to the OTA self-upgrade path and runs only after
    # a successful CLI upgrade.
    if not version_at_least(latest_version, POST_UPGRADE_SKILL_MIGRATION_MIN_VERSION):
        verbose_log(f"post-upgrade migration skipped; version<{POST_UPGRADE_SKILL_MIGRATION_MIN_VERSION}")
        return

    config_path = resolve_openclaw_config_path()
    has_plugin_behavior, config = detect_skillhub_plugin_behavior(config_path)
    if not has_plugin_behavior:
        verbose_log("post-upgrade migration skipped; no skillhub plugin behavior detected")
        return

    verbose_log("skillhub plugin behavior detected; run migration to workspace skills")
    openclaw_bin = resolve_openclaw_bin()
    disabled = disable_skillhub_plugin_via_openclaw(openclaw_bin) if openclaw_bin else False

    if not disabled:
        verbose_log("skip plugin-disable fallback; openclaw command unavailable or failed")

    if not should_install_workspace_skills():
        verbose_log("workspace skills install disabled by config/env; skip install")
        return

    config_after = read_json_object(config_path)
    workspace_path = resolve_openclaw_workspace_path(config_after if config_after else config)
    # Template sources are package files in plain text:
    # skill/SKILL.md and skill/SKILL.skillhub-preference.md.
    find_skill_text = read_skill_template(find_skill_template)
    preference_skill_text = read_skill_template(preference_skill_template)

    if find_skill_text:
        find_target = install_workspace_skill(workspace_path, FIND_SKILLS_SLUG, find_skill_text)
        verbose_log(f"installed migrated skill: {find_target}")
    else:
        verbose_log("find-skills template missing in package; skip install")

    if preference_skill_text:
        preference_target = install_workspace_skill(
            workspace_path,
            SKILLHUB_PREFERENCE_SLUG,
            preference_skill_text,
        )
        verbose_log(f"installed migrated skill: {preference_target}")
    else:
        verbose_log("skillhub-preference template missing in package; skip install")


def resolve_uri_with_base(raw: str, base_dir: Path) -> str:
    value = raw.strip()
    if not value:
        return ""
    parsed = urllib.parse.urlparse(value)
    if parsed.scheme in ("http", "https"):
        return value
    if parsed.scheme == "file":
        return parse_path_like_uri(value).as_uri()
    if parsed.scheme != "":
        die(f"Unsupported URI scheme: {value}")
    return (base_dir / value).resolve().as_uri()


def extract_update_manifest_info(manifest: Dict[str, Any]) -> Tuple[str, str, str]:
    candidates = [manifest]
    for key in ("latest", "release", "data", "skill", "package"):
        nested = manifest.get(key)
        if isinstance(nested, dict):
            candidates.append(nested)

    latest_version = ""
    package_uri = ""
    sha256 = ""
    for item in candidates:
        if not latest_version:
            latest_version = first_non_empty_string(item, ["version", "latest_version", "latestVersion"])
        if not package_uri:
            package_uri = first_non_empty_string(
                item,
                ["zip_url", "zipUrl", "download_url", "downloadUrl", "package_url", "packageUrl", "url"],
            )
        if not sha256:
            sha256 = first_non_empty_string(item, ["sha256", "sha_256", "checksum"])
    return latest_version, package_uri, sha256.lower()


def install_zip_to_target(
    slug: str,
    zip_uri: str,
    target_dir: Path,
    force: bool,
    expected_sha256: str = "",
) -> None:
    if target_dir.exists() and not force:
        die(f"Target exists: {target_dir} (use --force to overwrite)")

    with tempfile.TemporaryDirectory(prefix="skills-store-cli-") as tmp:
        zip_path = Path(tmp) / f"{slug}.zip"
        stage_dir = Path(tmp) / "stage"
        stage_dir.mkdir(parents=True, exist_ok=True)
        print(f"Downloading: {zip_uri}")
        download_file(zip_uri, zip_path)

        if expected_sha256:
            actual_sha256 = sha256_file(zip_path).lower()
            if actual_sha256 != expected_sha256:
                die(
                    f"SHA256 mismatch for {slug}: expected {expected_sha256}, got {actual_sha256}"
                )
        try:
            safe_extract_zip(zip_path, stage_dir)
        except zipfile.BadZipFile:
            die(f"Downloaded file is not a valid zip archive: {zip_uri}")

        if target_dir.exists():
            if not force:
                die(f"Target exists: {target_dir} (use --force to overwrite)")
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(stage_dir), str(target_dir))


def install_zip_to_target_with_fallback(
    slug: str,
    zip_uris: List[str],
    target_dir: Path,
    force: bool,
    expected_sha256: str = "",
) -> None:
    candidates = [str(x).strip() for x in zip_uris if str(x).strip()]
    seen = set()
    ordered: List[str] = []
    for x in candidates:
        if x in seen:
            continue
        seen.add(x)
        ordered.append(x)
    if not ordered:
        die(f'No download URL candidates for "{slug}"')

    if target_dir.exists() and not force:
        die(f"Target exists: {target_dir} (use --force to overwrite)")

    with tempfile.TemporaryDirectory(prefix="skills-store-cli-") as tmp:
        zip_path = Path(tmp) / f"{slug}.zip"
        stage_dir = Path(tmp) / "stage"
        stage_dir.mkdir(parents=True, exist_ok=True)
        last_err = ""
        used_uri = ""
        for idx, zip_uri in enumerate(ordered):
            try:
                print(f"Downloading: {zip_uri}")
                download_file_or_raise(zip_uri, zip_path)
                used_uri = zip_uri
                last_err = ""
                break
            except Exception as exc:
                last_err = str(exc)
                if idx + 1 < len(ordered):
                    print(f"Download failed, fallback next source: {exc}", file=sys.stderr)
                    continue
        if last_err:
            die(last_err)

        if expected_sha256:
            actual_sha256 = sha256_file(zip_path).lower()
            if actual_sha256 != expected_sha256:
                die(
                    f"SHA256 mismatch for {slug}: expected {expected_sha256}, got {actual_sha256}"
                )
        try:
            safe_extract_zip(zip_path, stage_dir)
        except zipfile.BadZipFile:
            die(f"Downloaded file is not a valid zip archive: {used_uri or ordered[0]}")

        if target_dir.exists():
            if not force:
                die(f"Target exists: {target_dir} (use --force to overwrite)")
            shutil.rmtree(target_dir)
        target_dir.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(stage_dir), str(target_dir))


def normalize_skills_payload(data: Any) -> Dict[str, Any]:
    if isinstance(data, dict):
        skills = data.get("skills")
        if isinstance(skills, list):
            return data
        die('Index JSON must include a "skills" array.')
    if isinstance(data, list):
        return {"skills": data}
    die("Index JSON must be an object or array.")
    return {"skills": []}


def load_index(index_uri: str) -> Dict[str, Any]:
    try:
        data = read_json_from_uri(index_uri, timeout=20)
    except Exception as exc:
        die(str(exc))
    return normalize_skills_payload(data)


def index_local_path_or_none(index_uri: str) -> Optional[Path]:
    parsed = urllib.parse.urlparse(index_uri)
    if parsed.scheme in ("", "file"):
        return parse_path_like_uri(index_uri)
    return None


def skill_zip_uri(
    skill: Dict[str, Any],
    slug: str,
    index_path: Optional[Path],
    files_base_uri: str,
    download_url_template: str,
) -> str:
    if files_base_uri.strip():
        from_base = append_slug_zip(files_base_uri, slug)
        if from_base:
            return from_base

    if index_path is not None:
        sibling_files = (index_path.parent / "files" / f"{slug}.zip").resolve()
        if sibling_files.exists():
            return sibling_files.as_uri()

    for key in ("zip_url", "zipUrl", "archive_url", "archiveUrl", "file_url", "fileUrl"):
        raw = str(skill.get(key, "")).strip()
        if raw:
            if urllib.parse.urlparse(raw).scheme:
                return raw
            return Path(raw).expanduser().resolve().as_uri()

    if download_url_template.strip():
        return append_slug_zip(download_url_template, slug)

    die(
        f'Skill "{slug}" has no zip_url and no local archive found. '
        "Use --files-base-uri or --download-url-template."
    )
    return ""


def load_lockfile(install_root: Path) -> Dict[str, Any]:
    lock_path = install_root / LOCKFILE_NAME
    if not lock_path.exists():
        return {"version": 1, "skills": {}}
    try:
        raw = json.loads(lock_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return {"version": 1, "skills": {}}
    if not isinstance(raw, dict):
        return {"version": 1, "skills": {}}
    if not isinstance(raw.get("skills"), dict):
        raw["skills"] = {}
    return raw


def save_lockfile(install_root: Path, lock: Dict[str, Any]) -> None:
    install_root.mkdir(parents=True, exist_ok=True)
    lock_path = install_root / LOCKFILE_NAME
    lock_path.write_text(json.dumps(lock, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")


def resolve_clawhub_lock_path() -> Path:
    override = os.environ.get("SKILLHUB_CLAWHUB_LOCK_PATH", "").strip()
    if override:
        return Path(override).expanduser().resolve()
    return Path("~/.openclaw/workspace/.clawhub/lock.json").expanduser().resolve()


def update_clawhub_lock_v1(slug: str, version: str) -> None:
    lock_path = resolve_clawhub_lock_path()
    if not lock_path.exists():
        verbose_log(f"clawhub lock not found, skip sync: {lock_path}")
        return
    try:
        raw = json.loads(lock_path.read_text(encoding="utf-8"))
    except Exception:
        verbose_log(f"clawhub lock invalid JSON, skip sync: {lock_path}")
        return
    if not isinstance(raw, dict) or raw.get("version") != 1:
        verbose_log(f"clawhub lock version is not 1, skip sync: {lock_path}")
        return
    skills = raw.get("skills")
    if not isinstance(skills, dict):
        skills = {}
        raw["skills"] = skills
    skills[slug] = {
        "version": version,
        "installedAt": int(time.time() * 1000),
    }
    try:
        lock_path.parent.mkdir(parents=True, exist_ok=True)
        lock_path.write_text(json.dumps(raw, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        verbose_log(f"synced clawhub lock entry: {slug} -> {lock_path}")
    except Exception:
        verbose_log(f"failed to write clawhub lock, skip: {lock_path}")


def skill_text(skill: Dict[str, Any]) -> str:
    tags = skill.get("tags") or []
    if not isinstance(tags, list):
        tags = []
    categories = skill.get("categories") or []
    if not isinstance(categories, list):
        categories = []
    text = " ".join(
        [
            str(skill.get("slug", "")),
            str(skill.get("name", "")),
            str(skill.get("description", "")),
            str(skill.get("summary", "")),
            str(skill.get("version", "")),
            " ".join(str(tag) for tag in tags),
            " ".join(str(category) for category in categories),
        ]
    )
    return text.lower()



# ============================================================
# Enterprise Credentials Management
# ============================================================

CREDENTIALS_FILE_NAME = "credentials.json"
DEFAULT_ENTERPRISE_HOST = "https://api.skillhub.cn"
ENTERPRISE_VERIFY_TIMEOUT = 10
ENTERPRISE_SEARCH_TIMEOUT = 3


def get_credentials_path() -> Path:
    """返回凭证文件路径: ~/.skillhub/credentials.json"""
    return Path(DEFAULT_CLI_HOME).expanduser() / CREDENTIALS_FILE_NAME


def load_credentials() -> Dict[str, Any]:
    """加载凭证文件，返回完整 JSON 对象。不存在则返回空结构。"""
    cred_path = get_credentials_path()
    if not cred_path.exists():
        return {"version": 1, "orgs": {}}
    try:
        raw = json.loads(cred_path.read_text(encoding="utf-8"))
        if not isinstance(raw, dict):
            return {"version": 1, "orgs": {}}
        if "orgs" not in raw or not isinstance(raw["orgs"], dict):
            raw["orgs"] = {}
        return raw
    except (json.JSONDecodeError, OSError):
        return {"version": 1, "orgs": {}}


def save_credentials(creds: Dict[str, Any]) -> None:
    """原子写入凭证文件（先写临时文件再 rename），权限 0600。"""
    cred_path = get_credentials_path()
    cred_path.parent.mkdir(parents=True, exist_ok=True)
    # 原子写入
    tmp_path = cred_path.with_suffix(".tmp")
    try:
        tmp_path.write_text(json.dumps(creds, indent=2, ensure_ascii=False), encoding="utf-8")
        os.chmod(str(tmp_path), 0o600)
        tmp_path.replace(cred_path)
    except OSError:
        # fallback: 直接写
        cred_path.write_text(json.dumps(creds, indent=2, ensure_ascii=False), encoding="utf-8")
        try:
            os.chmod(str(cred_path), 0o600)
        except OSError:
            pass


def get_org_credential(org_slug: str) -> Optional[Dict[str, Any]]:
    """获取指定 org 的凭证信息。

    支持按团队 ID（orgOrgId，不可变）或英文简称（orgSlug，可变）匹配。
    优先精确匹配 key（团队 ID），失败后 fallback 按 orgSlug 或 orgOrgId 字段遍历匹配。
    """
    creds = load_credentials()
    orgs = creds.get("orgs", {})
    # 1. 精确匹配 key（团队 ID）
    if org_slug in orgs:
        return orgs[org_slug]
    # 2. Fallback: 遍历所有凭证，按 orgOrgId 或 orgSlug 字段匹配
    for _key, info in orgs.items():
        if info.get("orgOrgId") == org_slug or info.get("orgSlug") == org_slug:
            return info
    return None


def get_all_org_credentials() -> Dict[str, Dict[str, Any]]:
    """获取所有已登录的 org 凭证，按 loggedInAt 倒序排列。"""
    creds = load_credentials()
    orgs = creds.get("orgs", {})
    # 按 loggedInAt 倒序排列
    sorted_orgs = dict(
        sorted(orgs.items(), key=lambda x: x[1].get("loggedInAt", ""), reverse=True)
    )
    return sorted_orgs


def resolve_org_credential_from_env() -> Optional[Dict[str, Any]]:
    """从环境变量解析企业凭证（CI/CD 场景），优先级高于 credentials.json。"""
    org_slug = os.environ.get("SKILLHUB_ORG", "").strip()
    api_key = os.environ.get("SKILLHUB_API_KEY", "").strip()
    if not org_slug or not api_key:
        return None
    host = os.environ.get("SKILLHUB_HOST", "").strip() or DEFAULT_ENTERPRISE_HOST
    return {
        "orgOrgId": org_slug,
        "orgSlug": org_slug,
        "host": host,
        "apiKey": api_key,
        "fromEnv": True,
    }


def mask_api_key(key: str) -> str:
    """脱敏展示 API Key: sk-ent-b0df...cec0"""
    if len(key) <= 15:
        return key[:4] + "..." + key[-4:] if len(key) > 8 else "***"
    return key[:11] + "..." + key[-4:]


def parse_skill_ref(ref: str) -> Tuple[Optional[str], str, Optional[str]]:
    """Parse a skill reference like '@org/slug@version' into (org, slug, version).

    Examples:
        'my-skill'           -> (None, 'my-skill', None)
        '@tencent/my-skill'  -> ('tencent', 'my-skill', None)
        '@tencent/my-skill@1.0.0' -> ('tencent', 'my-skill', '1.0.0')
    """
    org: Optional[str] = None
    version: Optional[str] = None
    if ref.startswith("@"):
        parts = ref[1:].split("/", 1)
        if len(parts) != 2 or not parts[0] or not parts[1]:
            raise ValueError(f"Invalid skill reference: {ref}. Expected format: @org/slug")
        org = parts[0]
        ref = parts[1]
    if "@" in ref:
        ref, version = ref.rsplit("@", 1)
    if not ref:
        raise ValueError(f"Invalid skill reference: slug cannot be empty")
    return org, ref, version


def verify_api_key(host: str, api_key: str) -> Dict[str, Any]:
    """调用 POST {host}/api/v1/registry/verify 验证 API Key，返回 org 信息。

    Returns: {"orgId": int, "orgOrgId": str, "orgSlug": str, "orgName": str}
    Raises: RuntimeError on failure.
    """
    url = f"{host.rstrip('/')}/api/v1/registry/verify"
    req = urllib.request.Request(
        url,
        method="POST",
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": CLI_USER_AGENT,
            "Content-Type": "application/json",
        },
        data=b"",
    )
    try:
        with urllib.request.urlopen(req, timeout=ENTERPRISE_VERIFY_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if not isinstance(body, dict) or "orgId" not in body:
                raise RuntimeError("Unexpected response from verify endpoint")
            return body
    except urllib.error.HTTPError as exc:
        if exc.code == 401:
            try:
                err_body = json.loads(exc.read().decode("utf-8"))
                msg = err_body.get("error", "invalid or expired API key")
            except Exception:
                msg = "invalid or expired API key"
            raise RuntimeError(msg)
        raise RuntimeError(f"Verify request failed (HTTP {exc.code})")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot connect to {host}: {exc.reason}")
    except Exception as exc:
        raise RuntimeError(f"Verify request failed: {exc}")


def fetch_enterprise_search_results(
    host: str,
    org_id: int,
    api_key: str,
    query: str,
    limit: int = 20,
) -> Optional[List[Dict[str, Any]]]:
    """搜索企业源技能，返回结果列表。超时或失败返回 None。"""
    url = f"{host.rstrip('/')}/api/v1/orgs/{org_id}/registry/search"
    params = urllib.parse.urlencode({"q": query, "pageSize": limit})
    full_url = f"{url}?{params}"
    req = urllib.request.Request(
        full_url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": CLI_USER_AGENT,
            "Accept": "application/json",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=ENTERPRISE_SEARCH_TIMEOUT) as resp:
            body = json.loads(resp.read().decode("utf-8"))
            if not isinstance(body, dict):
                return None
            skills = body.get("skills", [])
            if not isinstance(skills, list):
                return None
            return skills
    except Exception:
        return None


def download_enterprise_skill(
    host: str,
    org_id: int,
    api_key: str,
    slug: str,
    version: Optional[str],
    target_dir: Path,
    force: bool = False,
) -> Optional[str]:
    """下载企业技能 ZIP 并解压到 target_dir。返回版本号或 None（失败）。"""
    url = f"{host.rstrip('/')}/api/v1/orgs/{org_id}/registry/skills/{slug}/download"
    if version:
        url += f"?version={urllib.parse.quote(version)}"

    req = urllib.request.Request(
        url,
        headers={
            "Authorization": f"Bearer {api_key}",
            "User-Agent": CLI_USER_AGENT,
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            # 跟随重定向后获取最终内容
            content = resp.read()
            # 从 Content-Disposition 或 URL 提取版本号
            cd = resp.headers.get("Content-Disposition", "")
            detected_version = version or ""
            if not detected_version and cd:
                # filename="slug-1.0.0.zip"
                import re
                m = re.search(r'filename="?([^"]+)"?', cd)
                if m:
                    fname = m.group(1)
                    if fname.startswith(slug + "-") and fname.endswith(".zip"):
                        detected_version = fname[len(slug) + 1:-4]

            # 写入临时文件并解压
            if target_dir.exists() and not force:
                shutil.rmtree(target_dir)
            target_dir.mkdir(parents=True, exist_ok=True)

            with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
                tmp.write(content)
                tmp_path = tmp.name

            try:
                with zipfile.ZipFile(tmp_path, "r") as zf:
                    zf.extractall(target_dir)
            finally:
                os.unlink(tmp_path)

            return detected_version or "latest"
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise RuntimeError(f"Download failed (HTTP {exc.code})")
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Cannot connect to {host}: {exc.reason}")


def normalize_source_label(value: Any) -> str:
    source = str(value or "").strip()
    if not source or source.lower() == "unknown":
        return "skillhub"
    return source


def is_clawhub_url(value: str) -> bool:
    try:
        host = urllib.parse.urlparse(value).netloc.lower()
    except Exception:
        return False
    return host == "clawhub.ai" or host.endswith(".clawhub.ai")


def fetch_remote_search_results(
    search_url: str,
    query: str,
    limit: int,
    timeout: int,
) -> Optional[List[Dict[str, Any]]]:
    base = str(search_url or "").strip()
    q = str(query or "").strip()
    if not base or not q:
        return None
    try:
        parsed = urllib.parse.urlparse(base)
        if parsed.scheme not in ("http", "https"):
            return None
        params = urllib.parse.urlencode({"q": q, "limit": max(1, int(limit))})
        full_url = urllib.parse.urlunparse(
            (parsed.scheme, parsed.netloc, parsed.path, parsed.params, params, parsed.fragment)
        )
        req = urllib.request.Request(
            full_url,
            headers={
                "User-Agent": CLI_USER_AGENT,
                "Accept": "application/json",
            },
        )
        with urllib.request.urlopen(req, timeout=max(1, int(timeout))) as response:
            payload = response.read().decode("utf-8")
        raw = json.loads(payload)
        if not isinstance(raw, dict):
            return None
        results = raw.get("results")
        if not isinstance(results, list):
            return None
        out: List[Dict[str, Any]] = []
        for item in results:
            if not isinstance(item, dict):
                continue
            slug = str(item.get("slug", "")).strip()
            if not slug:
                continue
            out.append(
                {
                    "slug": slug,
                    "name": str(item.get("displayName") or item.get("name") or slug).strip() or slug,
                    "description": str(item.get("summary") or item.get("description") or "").strip(),
                    "summary": str(item.get("summary") or "").strip(),
                    "version": str(item.get("version") or "").strip(),
                }
            )
        return out
    except Exception:
        return None


def cmd_search(args: argparse.Namespace) -> None:
    query_parts = args.query if isinstance(args.query, list) else [args.query]
    query = " ".join(str(part) for part in query_parts).lower().strip()
    json_out = bool(getattr(args, "json_output", False))
    scope_org = getattr(args, "org", None)
    if scope_org:
        scope_org = scope_org.strip()

    if not query:
        # 无查询词时，展示本地 index（保持原有行为）
        _search_local_index(args, query, json_out)
        return

    # 联合搜索: 企业源 + 社区源
    warnings: List[str] = []
    enterprise_results: List[Dict[str, Any]] = []
    community_results: List[Dict[str, Any]] = []

    # 1. 搜索企业源（所有已登录的，或仅指定的 --org）
    if not scope_org or scope_org != "community":
        orgs = get_all_org_credentials()
        if scope_org:
            # 仅搜索指定企业源（支持按 key、orgOrgId 或 orgSlug 匹配）
            if scope_org in orgs:
                orgs = {scope_org: orgs[scope_org]}
            else:
                # Fallback: 按 orgOrgId 或 orgSlug 字段遍历匹配
                matched = {k: v for k, v in orgs.items()
                           if v.get("orgOrgId") == scope_org or v.get("orgSlug") == scope_org}
                if matched:
                    orgs = matched
                else:
                    warnings.append(f"@{scope_org}: not logged in, skipped")
                    orgs = {}

        for org_slug, cred in orgs.items():
            host = cred.get("host", DEFAULT_ENTERPRISE_HOST)
            org_id = cred.get("orgId")
            api_key = cred.get("apiKey", "")
            if not org_id or not api_key:
                continue
            results = fetch_enterprise_search_results(
                host=host,
                org_id=org_id,
                api_key=api_key,
                query=query,
                limit=args.search_limit,
            )
            if results is None:
                warnings.append(f"@{org_slug}: request timed out or failed, results omitted")
            elif results:
                for skill in results:
                    skill["_source"] = f"@{org_slug}"
                    skill["_org"] = org_slug
                enterprise_results.extend(results)

    # 2. 搜索社区源（除非 --org 指定了企业源）
    if not scope_org or scope_org == "community":
        community = fetch_remote_search_results(
            search_url=args.search_url,
            query=query,
            limit=args.search_limit,
            timeout=args.search_timeout,
        )
        if community is not None:
            for skill in community:
                skill["_source"] = "community"
            community_results = community
        elif not scope_org:
            warnings.append("community: search request failed")

    # 3. 合并结果: 企业源优先
    all_results = enterprise_results + community_results

    # 4. 打印警告
    for w in warnings:
        print(f"\u26a0\ufe0f  {w}", file=sys.stderr)

    if not all_results:
        print("No skills found.")
        return

    # 5. 输出
    if json_out:
        output_results = []
        for skill in all_results:
            output_results.append({
                "slug": skill.get("slug", ""),
                "name": skill.get("name") or skill.get("displayName", ""),
                "description": skill.get("description") or skill.get("summary", ""),
                "version": skill.get("version", ""),
                "source": skill.get("_source", "community"),
            })
        print(
            json.dumps(
                {
                    "query": query,
                    "count": len(output_results),
                    "results": output_results,
                    "warnings": warnings,
                },
                ensure_ascii=False,
            )
        )
        return

    print('You can use "skillhub install [skill]" to install.')
    for skill in all_results:
        source = skill.get("_source", "community")
        slug = skill.get("slug", "<unknown>")
        name = skill.get("name") or skill.get("displayName", slug)
        description = skill.get("description") or skill.get("summary", "")
        version = skill.get("version", "")
        # 企业源展示 @org/slug 格式，社区源直接展示 slug
        if source.startswith("@"):
            display_slug = f"@{skill.get('_org', '')}/{slug}"
        else:
            display_slug = slug
        print(f"  {display_slug}  {name}")
        if description:
            print(f"    - {description}")
        if version:
            print(f"    - version: {version}")


def _search_local_index(args: argparse.Namespace, query: str, json_out: bool) -> None:
    """搜索本地 index（无查询词时的 fallback）。"""
    data = load_index(args.index)
    matches: List[Dict[str, Any]] = []
    for item in data["skills"]:
        if not isinstance(item, dict):
            continue
        matches.append(item)

    if not matches:
        print("No skills found.")
        return

    if query:
        def rank(skill: Dict[str, Any]) -> Tuple[int, str]:
            text = skill_text(skill)
            score = text.count(query)
            slug = str(skill.get("slug", ""))
            return (score, slug)

        matches.sort(key=rank, reverse=True)

    if json_out:
        results: List[Dict[str, Any]] = []
        for skill in matches:
            if not isinstance(skill, dict):
                continue
            slug = str(skill.get("slug") or "").strip()
            if not slug:
                continue
            name = str(skill.get("name") or skill.get("displayName") or slug).strip() or slug
            description = str(skill.get("description") or skill.get("summary") or "").strip()
            version = str(skill.get("version") or "").strip()
            results.append(
                {
                    "slug": slug,
                    "name": name,
                    "description": description,
                    "summary": str(skill.get("summary") or "").strip(),
                    "version": version,
                    "source": "community",
                }
            )
        print(
            json.dumps(
                {
                    "query": query,
                    "count": len(results),
                    "results": results,
                },
                ensure_ascii=False,
            )
        )
        return

    print('You can use "skillhub install [skill]" to install.')

    for skill in matches:
        slug = skill.get("slug", "<unknown>")
        name = skill.get("name", slug)
        description = skill.get("description", "")
        if not description:
            description = skill.get("summary", "")
        zip_url = skill.get("zip_url", "")
        homepage = skill.get("homepage", "")
        version = skill.get("version", "")
        print(f"  {slug}  {name}")
        if description:
            print(f"    - {description}")
        if version:
            print(f"    - version: {version}")
        if zip_url:
            print(f"    - {zip_url}")
        if homepage and not is_clawhub_url(homepage):
            print(f"    - {homepage}")


def download_file_or_raise(url: str, dest: Path) -> None:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme == "file":
        source_path = parse_path_like_uri(url)
        if not source_path.exists():
            raise RuntimeError(f"Download failed: local file not found: {source_path}")
        shutil.copyfile(source_path, dest)
        return
    if parsed.scheme == "":
        source_path = Path(url).expanduser().resolve()
        if source_path.exists():
            shutil.copyfile(source_path, dest)
            return

    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": CLI_USER_AGENT,
            "Accept": "application/zip,application/octet-stream,*/*",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            if response.status and response.status >= 400:
                raise RuntimeError(f"Download failed ({response.status}) for {url}")
            with dest.open("wb") as out:
                shutil.copyfileobj(response, out)
    except urllib.error.HTTPError as exc:
        detail = f"HTTP {exc.code}"
        if exc.code == 429:
            detail += " (rate limited)"
        raise RuntimeError(f"Download failed: {detail} for {url}") from exc
    except urllib.error.URLError as exc:
        raise RuntimeError(f"Download failed: {exc.reason} for {url}") from exc


def download_file(url: str, dest: Path) -> None:
    try:
        download_file_or_raise(url, dest)
    except Exception as exc:
        die(str(exc))


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def safe_extract_zip(zip_path: Path, target_dir: Path) -> None:
    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.infolist():
            member_path = Path(member.filename)
            if member_path.is_absolute() or ".." in member_path.parts:
                die(f"Unsafe zip path entry detected: {member.filename}")
        zf.extractall(target_dir)


def safe_extract_tar(tar_path: Path, target_dir: Path) -> None:
    with tarfile.open(tar_path, "r:*") as tf:
        for member in tf.getmembers():
            member_path = Path(member.name)
            if member_path.is_absolute() or ".." in member_path.parts:
                die(f"Unsafe tar path entry detected: {member.name}")
        try:
            tf.extractall(target_dir, filter="data")
        except TypeError:
            tf.extractall(target_dir)


def find_skill(data: Dict[str, Any], slug: str) -> Optional[Dict[str, Any]]:
    for item in data["skills"]:
        if isinstance(item, dict) and str(item.get("slug", "")).strip() == slug:
            return item
    return None


# ============================================================
# Enterprise Commands: login / logout / config
# ============================================================


def cmd_login(args: argparse.Namespace) -> None:
    """登录企业源: skillhub login --key <api-key> [--host <url>]"""
    api_key = args.key.strip()
    if not api_key:
        die("--key is required")

    host = (args.host or "").strip() or DEFAULT_ENTERPRISE_HOST

    # 调用 verify 接口
    try:
        org_info = verify_api_key(host, api_key)
    except RuntimeError as exc:
        die(f"Login failed: {exc}")

    org_id = org_info["orgId"]
    org_org_id = org_info.get("orgOrgId", org_info["orgSlug"])  # 团队 ID（不可变）
    org_slug = org_info["orgSlug"]  # 英文简称（可变）
    org_name = org_info.get("orgName", org_org_id)

    # 加载现有凭证
    creds = load_credentials()
    orgs = creds.setdefault("orgs", {})

    # 迁移旧格式：如果存在以 orgSlug 为 key 的旧凭证，删除它
    if org_slug != org_org_id and org_slug in orgs:
        del orgs[org_slug]
        print(f"Migrating credentials from @{org_slug} to @{org_org_id}", file=sys.stderr)

    # 检查是否已存在（覆盖）
    if org_org_id in orgs:
        print(f"Updating credentials for @{org_org_id}", file=sys.stderr)

    # 写入凭证，key 为团队 ID（不可变）
    orgs[org_org_id] = {
        "orgId": org_id,
        "orgOrgId": org_org_id,
        "orgSlug": org_slug,
        "orgName": org_name,
        "host": host,
        "apiKey": api_key,
        "loggedInAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    creds["version"] = 1

    # 检查是否首次 login（打印安全警告）
    is_first_login = len(orgs) == 1 and org_org_id in orgs
    save_credentials(creds)

    if is_first_login:
        cred_path = get_credentials_path()
        print(
            f"WARNING! Your API key is stored unencrypted in '{cred_path}'.\n"
            f"Configure a credential helper to remove this warning.",
            file=sys.stderr,
        )

    print(f"\u2713 Logged in to {org_name} (@{org_org_id}) at {host}")


def cmd_logout(args: argparse.Namespace) -> None:
    """登出企业源: skillhub logout [--org <orgSlug|orgOrgId>]"""
    creds = load_credentials()
    orgs = creds.get("orgs", {})

    org_input = (args.org or "").strip().lstrip("@")

    if not org_input:
        # 如果只有一个 org，直接登出
        if len(orgs) == 1:
            org_input = next(iter(orgs))
        elif len(orgs) == 0:
            die("No enterprise sources configured. Nothing to logout.")
        else:
            org_list = ", ".join(f"@{s}" for s in orgs.keys())
            die(f"Multiple enterprise sources configured ({org_list}). Please specify --org <orgSlug>.")

    # 精确匹配 key（团队 ID）
    matched_key = None
    if org_input in orgs:
        matched_key = org_input
    else:
        # Fallback: 按 orgOrgId 或 orgSlug 字段遍历匹配
        for key, info in orgs.items():
            if info.get("orgOrgId") == org_input or info.get("orgSlug") == org_input:
                matched_key = key
                break

    if not matched_key:
        die(f"Not logged in to @{org_input}.")

    del orgs[matched_key]
    save_credentials(creds)
    print(f"\u2713 Logged out from @{matched_key}")


def cmd_config_list(args: argparse.Namespace) -> None:
    """查看已配置的企业源: skillhub config list"""
    orgs = get_all_org_credentials()

    if not orgs:
        print("No enterprise sources configured.")
        print('Run "skillhub login --key <api-key>" to add one.')
        return

    print("Enterprise Sources:")
    for key, info in orgs.items():
        host = info.get("host", DEFAULT_ENTERPRISE_HOST)
        org_id = info.get("orgId", "?")
        org_org_id = info.get("orgOrgId", key)
        org_slug = info.get("orgSlug", key)
        org_name = info.get("orgName", "")
        api_key = mask_api_key(info.get("apiKey", ""))
        logged_in = info.get("loggedInAt", "?")
        print(f"  @{key}")
        if org_name:
            print(f"    Name:      {org_name}")
        print(f"    Org ID:    {org_id}")
        print(f"    Team ID:   {org_org_id}")
        if org_slug != org_org_id:
            print(f"    Slug:      {org_slug}")
        print(f"    Host:      {host}")
        print(f"    API Key:   {api_key}")
        print(f"    Logged in: {logged_in}")
        print()


def cmd_install(args: argparse.Namespace) -> None:
    raw_slug = args.slug.strip()

    # 解析 @org/slug@version 格式
    try:
        org, slug, version = parse_skill_ref(raw_slug)
    except ValueError as exc:
        die(str(exc))

    # 企业源安装路径
    if org:
        _install_enterprise_skill(args, org, slug, version)
        return

    # 社区源安装路径（原有逻辑，向后兼容）
    data: Dict[str, Any] = {"skills": []}
    try:
        data = load_index(args.index)
    except SystemExit:
        print(f"warn: failed to load index ({args.index}), continue with remote/direct install", file=sys.stderr)
    skill = find_skill(data, slug)
    if not skill:
        remote = fetch_remote_search_results(
            search_url=args.search_url,
            query=slug,
            limit=args.search_limit,
            timeout=args.search_timeout,
        )
        if remote:
            exact = next((x for x in remote if str(x.get("slug", "")).strip() == slug), None)
            if exact:
                skill = exact
                print(f'info: "{slug}" not in index, using remote registry exact match', file=sys.stderr)
            else:
                print(
                    f'info: "{slug}" not in index, and remote search has no exact slug match; '
                    "try direct download by slug",
                    file=sys.stderr,
                )

    if not skill:
        skill = {"slug": slug, "name": slug, "version": "", "source": "skillhub"}
        print(f'info: "{slug}" not in index/remote search, try direct download by slug', file=sys.stderr)

    primary_zip_url = fill_slug_template(args.primary_download_url_template, slug)
    if not primary_zip_url:
        die("Primary download URL template resolved empty URL")

    install_root = Path(args.dir).expanduser().resolve()
    target_dir = install_root / slug
    expected_sha256 = str(skill.get("sha256", "")).strip().lower()

    # 同名冲突检测：如果已安装的是企业版技能，自动覆盖并提示
    lock = load_lockfile(install_root)
    skills_lock = lock.setdefault("skills", {})
    existing = skills_lock.get(slug)
    force = args.force
    if existing and existing.get("source", "").startswith("@"):
        old_source = existing.get("source", "unknown")
        old_version = existing.get("version", "?")
        print(
            f"\u26a0\ufe0f  Replacing existing skill \"{slug}\" ({old_source} v{old_version}) "
            f"with community {slug}",
            file=sys.stderr,
        )
        force = True

    install_zip_to_target_with_fallback(
        slug=slug,
        zip_uris=[primary_zip_url],
        target_dir=target_dir,
        force=force,
        expected_sha256=expected_sha256,
    )

    skills_lock[slug] = {
        "name": skill.get("name", slug),
        "zip_url": primary_zip_url,
        "source": "community",
        "version": str(skill.get("version", "")).strip(),
        "installedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_lockfile(install_root, lock)
    update_clawhub_lock_v1(slug, str(skill.get("version", "")).strip())
    print(f"\u2713 Installed: {slug} -> {target_dir}")

def _install_enterprise_skill(
    args: argparse.Namespace, org_slug: str, slug: str, version: Optional[str]
) -> None:
    """安装企业技能: @org/slug[@version]"""
    # 优先从环境变量获取凭证
    env_cred = resolve_org_credential_from_env()
    if env_cred and (env_cred.get("orgOrgId") == org_slug or env_cred.get("orgSlug") == org_slug):
        cred = env_cred
    else:
        cred = get_org_credential(org_slug)

    if not cred:
        die(
            f"Not logged in to @{org_slug}.\n"
            f"  Run: skillhub login --key <your-api-key>"
        )

    host = cred.get("host", DEFAULT_ENTERPRISE_HOST)
    org_id = cred.get("orgId")
    api_key = cred.get("apiKey", "")

    if not org_id or not api_key:
        die(
            f"Invalid credentials for @{org_slug}.\n"
            f"  Run: skillhub login --key <your-api-key>"
        )

    install_root = Path(args.dir).expanduser().resolve()
    target_dir = install_root / slug

    # 同名冲突检测：如果已安装的是不同来源的技能，自动覆盖并提示
    lock = load_lockfile(install_root)
    skills_lock = lock.setdefault("skills", {})
    existing = skills_lock.get(slug)
    force = args.force
    if existing:
        old_source = existing.get("source", "community")
        if old_source != f"@{org_slug}":
            old_version = existing.get("version", "?")
            print(
                f"\u26a0\ufe0f  Replacing existing skill \"{slug}\" ({old_source} v{old_version}) "
                f"with @{org_slug}/{slug}",
                file=sys.stderr,
            )
            force = True

    # 下载企业技能
    try:
        installed_version = download_enterprise_skill(
            host=host,
            org_id=org_id,
            api_key=api_key,
            slug=slug,
            version=version,
            target_dir=target_dir,
            force=force,
        )
    except RuntimeError as exc:
        die(f"Failed to install @{org_slug}/{slug}: {exc}")

    if installed_version is None:
        if version:
            die(f'Skill "{slug}" version "{version}" not found in @{org_slug}.')
        else:
            die(f'Skill "{slug}" not found in @{org_slug}.\n  Run: skillhub search "{slug}" to find available skills.')

    # 更新 lockfile
    skills_lock[slug] = {
        "name": slug,
        "source": f"@{org_slug}",
        "org": org_slug,
        "host": host,
        "version": installed_version,
        "installedAt": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
    }
    save_lockfile(install_root, lock)
    update_clawhub_lock_v1(slug, installed_version)

    version_display = f"@{installed_version}" if installed_version != "latest" else ""
    print(f"\u2713 Installed: @{org_slug}/{slug}{version_display} -> {target_dir}")


def cmd_upgrade(args: argparse.Namespace) -> None:
    code = run_skills_upgrade(
        args,
        {
            "load_lockfile": load_lockfile,
            "save_lockfile": save_lockfile,
            "read_json_from_uri": read_json_from_uri,
            "extract_update_manifest_info": extract_update_manifest_info,
            "resolve_uri_with_base": resolve_uri_with_base,
            "version_is_newer": version_is_newer,
            "install_zip_to_target": install_zip_to_target,
            "skill_config_name": SKILL_CONFIG_NAME,
            "skill_meta_name": SKILL_META_NAME,
        },
    )
    if code != 0:
        raise SystemExit(code)


def cmd_self_upgrade(args: argparse.Namespace) -> None:
    config_path = Path(args.config).expanduser().resolve()
    target_path = Path(args.target).expanduser().resolve() if args.target else Path(__file__).resolve()
    try:
        upgraded, current_version, latest_version = run_self_upgrade_flow(
            config_path=config_path,
            target_path=target_path,
            current_version=args.current_version or CLI_VERSION,
            timeout=args.timeout,
            check_only=args.check_only,
            quiet=False,
        )
    except Exception as exc:
        die(str(exc))

    if not upgraded and not args.check_only:
        print(f"CLI is up-to-date: current={current_version} latest={latest_version}")


def run_self_upgrade_flow(
    config_path: Path,
    target_path: Path,
    current_version: str,
    timeout: int,
    check_only: bool,
    quiet: bool,
) -> Tuple[bool, str, str]:
    manifest_url = resolve_self_update_manifest_url(config_path)
    verbose_log(f"fetching manifest: {manifest_url} (timeout={timeout}s)")
    manifest = read_json_from_uri(manifest_url, timeout=timeout)
    latest_version, package_uri_raw, expected_sha = extract_update_manifest_info(manifest)
    if not latest_version:
        raise RuntimeError(f"Self-update manifest missing version: {manifest_url}")
    if not package_uri_raw:
        raise RuntimeError(f"Self-update manifest missing package URL: {manifest_url}")

    current = normalize_version_text(current_version or CLI_VERSION)
    latest = normalize_version_text(latest_version)
    verbose_log(f"version compare: current={current} latest={latest}")
    if not version_is_newer(latest, current):
        verbose_log("no upgrade needed")
        return False, current, latest

    package_uri = resolve_uri_with_base(package_uri_raw, config_path.parent)
    verbose_log(f"resolved package URI: {package_uri}")
    if not quiet:
        print(
            f"Self-upgrade available: current={current} latest={latest}\n"
            f"Manifest: {manifest_url}\n"
            f"Package:  {package_uri}\n"
            f"Target:   {target_path}"
        )
    if check_only:
        verbose_log("check-only mode; skip install")
        return False, current, latest

    with tempfile.TemporaryDirectory(prefix="skillhub-self-upgrade-") as tmp:
        package_path = Path(tmp) / "package.bin"
        verbose_log(f"downloading package to temp: {package_path}")
        download_file_or_raise(package_uri, package_path)

        if expected_sha:
            verbose_log("sha256 present; verifying package checksum")
            actual_sha = sha256_file(package_path).lower()
            if actual_sha != expected_sha:
                raise RuntimeError(f"Self-upgrade SHA256 mismatch: expected {expected_sha}, got {actual_sha}")
        else:
            verbose_log("sha256 empty/missing; skip checksum verification")

        source_script: Path
        source_upgrade_module = None  # type: Optional[Path]
        source_version_file = None  # type: Optional[Path]
        source_metadata_file = None  # type: Optional[Path]
        source_find_skill_template = None  # type: Optional[Path]
        source_preference_skill_template = None  # type: Optional[Path]
        if zipfile.is_zipfile(package_path):
            extract_dir = Path(tmp) / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            safe_extract_zip(package_path, extract_dir)
            found = find_cli_script_in_extracted(extract_dir)
            if not found:
                raise RuntimeError("Self-upgrade zip does not contain skills_store_cli.py")
            source_script = found
            source_upgrade_module = find_peer_file_in_extracted(extract_dir, "skills_upgrade.py")
            source_version_file = find_peer_file_in_extracted(extract_dir, CLI_VERSION_FILE_NAME)
            source_metadata_file = find_peer_file_in_extracted(extract_dir, CLI_METADATA_FILE_NAME)
            source_find_skill_template = find_skill_file_in_extracted(extract_dir, "SKILL.md")
            source_preference_skill_template = find_skill_file_in_extracted(
                extract_dir,
                "SKILL.skillhub-preference.md",
            )
        elif tarfile.is_tarfile(package_path):
            extract_dir = Path(tmp) / "extract"
            extract_dir.mkdir(parents=True, exist_ok=True)
            safe_extract_tar(package_path, extract_dir)
            found = find_cli_script_in_extracted(extract_dir)
            if not found:
                raise RuntimeError("Self-upgrade tar package does not contain skills_store_cli.py")
            source_script = found
            source_upgrade_module = find_peer_file_in_extracted(extract_dir, "skills_upgrade.py")
            source_version_file = find_peer_file_in_extracted(extract_dir, CLI_VERSION_FILE_NAME)
            source_metadata_file = find_peer_file_in_extracted(extract_dir, CLI_METADATA_FILE_NAME)
            source_find_skill_template = find_skill_file_in_extracted(extract_dir, "SKILL.md")
            source_preference_skill_template = find_skill_file_in_extracted(
                extract_dir,
                "SKILL.skillhub-preference.md",
            )
        else:
            source_script = package_path

        try:
            raw = source_script.read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            raise RuntimeError(f"Self-upgrade package is not a text python script: {exc}") from exc
        if "def main()" not in raw:
            raise RuntimeError("Self-upgrade package content check failed (missing def main())")

        backup_path = target_path.with_suffix(target_path.suffix + ".bak")
        if target_path.exists():
            verbose_log(f"writing backup: {backup_path}")
            shutil.copyfile(target_path, backup_path)
        verbose_log(f"replacing target script: {target_path}")
        shutil.copyfile(source_script, target_path)
        target_path.chmod(0o755)

        target_upgrade_module = target_path.parent / "skills_upgrade.py"
        if source_upgrade_module and source_upgrade_module.exists():
            verbose_log(f"updating companion module: {target_upgrade_module}")
            shutil.copyfile(source_upgrade_module, target_upgrade_module)

        target_metadata_file = target_path.parent / CLI_METADATA_FILE_NAME
        if source_metadata_file and source_metadata_file.exists():
            verbose_log(f"updating metadata file from package: {target_metadata_file}")
            shutil.copyfile(source_metadata_file, target_metadata_file)

        version_file_path = target_path.parent / CLI_VERSION_FILE_NAME
        if source_version_file and source_version_file.exists():
            verbose_log(f"updating version file from package: {version_file_path}")
            shutil.copyfile(source_version_file, version_file_path)
        else:
            verbose_log(f"updating version file: {version_file_path} -> {latest}")
            version_file_path.write_text(
                json.dumps({"version": latest}, ensure_ascii=False, indent=2) + "\n",
                encoding="utf-8",
            )

        try:
            run_post_upgrade_plugin_migration(
                latest_version=latest,
                find_skill_template=source_find_skill_template,
                preference_skill_template=source_preference_skill_template,
            )
        except Exception as exc:
            verbose_log(f"post-upgrade migration failed; continue: {exc}")
        if not quiet:
            print(f"Self-upgrade complete: {target_path} -> version {latest}")
            print(f"Backup saved at: {backup_path}")
    return True, current, latest


def startup_self_upgrade_check(config_path: Optional[Path] = None) -> bool:
    if config_path is None:
        config_path = Path(f"{DEFAULT_CLI_HOME}/{CLI_CONFIG_NAME}").expanduser().resolve()
    if not config_path.exists():
        verbose_log(f"startup check: config not found at {config_path}; will use default manifest")
    try:
        upgraded, _, _ = run_self_upgrade_flow(
            config_path=config_path,
            target_path=Path(__file__).resolve(),
            current_version=CLI_VERSION,
            timeout=SELF_UPGRADE_CHECK_TIMEOUT_SECONDS,
            check_only=False,
            quiet=True,
        )
        verbose_log(f"startup check result: upgraded={upgraded}")
        return upgraded
    except BaseException:
        verbose_log("startup check failed; continue without upgrade")
        return False


def cmd_list(args: argparse.Namespace) -> None:
    install_root = Path(args.dir).expanduser().resolve()
    lock = load_lockfile(install_root)
    skills = lock.get("skills", {})
    if not skills:
        print("No installed skills.")
        return
    for slug, meta in sorted(skills.items()):
        if isinstance(meta, dict):
            version = str(meta.get("version", "")).strip()
            print(f"{slug}  {version}")
        else:
            print(f"{slug}  ")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Minimal local skills store CLI")
    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"skillhub {CLI_VERSION}",
        help="Show skillhub CLI version and exit",
    )
    parser.add_argument(
        "--index",
        default=DEFAULT_INDEX_URI,
        help=(
            "Skills index JSON path/URI. Supports http://, https://, file://, or local paths "
            '(default from metadata.json, e.g. "https://.../skills.json").'
        ),
    )
    parser.add_argument(
        "--dir",
        default=DEFAULT_INSTALL_ROOT,
        help='Install root directory (default: "./skills")',
    )
    parser.add_argument(
        "--skip-self-upgrade",
        action="store_true",
        help="Skip startup self-upgrade check for this run",
    )

    subparsers = parser.add_subparsers(dest="command", required=True)

    search = subparsers.add_parser("search", help="Search skills")
    search.add_argument("query", nargs="*", help="Search query words")
    search.add_argument(
        "--search-url",
        default=DEFAULT_SEARCH_URL,
        help=(
            "Remote search API URL (default from SKILLHUB_SEARCH_URL / metadata / built-in). "
            'Example: "http://.../api/v1/search".'
        ),
    )
    search.add_argument(
        "--search-limit",
        type=int,
        default=20,
        help="Remote search limit (default: 20)",
    )
    search.add_argument(
        "--search-timeout",
        type=int,
        default=6,
        help="Remote search timeout seconds (default: 6)",
    )
    search.add_argument(
        "--json",
        dest="json_output",
        action="store_true",
        help="Print search results as JSON",
    )
    search.add_argument(
        "--org",
        default="",
        help="Only search specified enterprise source (org slug)",
    )
    search.set_defaults(func=cmd_search)

    install = subparsers.add_parser("install", help="Install a skill by slug")
    install.add_argument("slug", help="Skill slug")
    install.add_argument(
        "--files-base-uri",
        default="",
        help=(
            "Base URI/path for local archives. Supports file://, local paths, or "
            "URL template with {slug} (examples: file://./cli/files, ./cli/files, "
            "https://example.com/files/{slug}.zip)."
        ),
    )
    install.add_argument(
        "--download-url-template",
        default=DEFAULT_SKILLS_DOWNLOAD_URL_TEMPLATE,
        help=(
            "Fallback download URL template when zip_url/local file is missing "
            '(default from metadata.json, e.g. "https://.../skills/{slug}.zip").'
        ),
    )
    install.add_argument(
        "--primary-download-url-template",
        default=DEFAULT_PRIMARY_DOWNLOAD_URL_TEMPLATE,
        help=(
            "Primary download URL template for install (supports {slug}). "
            "This is the only remote source used by install."
        ),
    )
    install.add_argument(
        "--search-url",
        default=DEFAULT_SEARCH_URL,
        help="Remote search API URL used when slug is not found in index.",
    )
    install.add_argument(
        "--search-limit",
        type=int,
        default=20,
        help="Remote search limit for install fallback (default: 20)",
    )
    install.add_argument(
        "--search-timeout",
        type=int,
        default=6,
        help="Remote search timeout for install fallback in seconds (default: 6)",
    )
    install.add_argument("--force", action="store_true", help="Overwrite existing target directory")
    install.add_argument(
        "--dir",
        default=argparse.SUPPRESS,
        help='Install root directory (default: "./skills")',
    )
    install.set_defaults(func=cmd_install)

    upgrade = subparsers.add_parser(
        "upgrade",
        help="Upgrade installed skills based on each skill's config.json update URL",
    )
    upgrade.add_argument(
        "slug",
        nargs="?",
        default="",
        help="Optional skill slug. If omitted, upgrade all skills in lockfile.",
    )
    upgrade.add_argument(
        "--check-only",
        action="store_true",
        help="Only check and print available upgrades without installing",
    )
    upgrade.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="Timeout in seconds for manifest fetch (default: 20)",
    )
    upgrade.add_argument(
        "--dir",
        default=argparse.SUPPRESS,
        help='Install root directory (default: "./skills")',
    )
    upgrade.set_defaults(func=cmd_upgrade)

    list_cmd = subparsers.add_parser("list", help="List locally installed skills")
    list_cmd.add_argument(
        "--dir",
        default=argparse.SUPPRESS,
        help='Install root directory (default: "./skills")',
    )
    list_cmd.set_defaults(func=cmd_list)

    self_upgrade = subparsers.add_parser(
        "self-upgrade",
        help="Self-upgrade this CLI from update manifest URL in config.json",
    )
    self_upgrade.add_argument(
        "--config",
        default=f"{DEFAULT_CLI_HOME}/config.json",
        help=(
            'Self-upgrade config path (default: "~/.skillhub/config.json"). '
            "If missing or no URL configured, falls back to the built-in manifest URL."
        ),
    )
    self_upgrade.add_argument(
        "--target",
        default="",
        help="CLI script target path to replace (default: current running script path)",
    )
    self_upgrade.add_argument(
        "--current-version",
        default=CLI_VERSION,
        help=f'Current CLI version for comparison (default: "{CLI_VERSION}")',
    )
    self_upgrade.add_argument(
        "--timeout",
        type=int,
        default=20,
        help="Timeout in seconds for manifest fetch/download requests (default: 20)",
    )
    self_upgrade.add_argument(
        "--check-only",
        action="store_true",
        help="Only check and print available CLI upgrade without replacing files",
    )
    self_upgrade.set_defaults(func=cmd_self_upgrade)

    # Enterprise commands: login / logout / config
    login_cmd = subparsers.add_parser(
        "login",
        help="Login to an enterprise source using API key",
    )
    login_cmd.add_argument(
        "--key",
        required=True,
        help="Enterprise API key (e.g. sk-ent-xxx)",
    )
    login_cmd.add_argument(
        "--host",
        default="",
        help=f"Enterprise host URL (default: {DEFAULT_ENTERPRISE_HOST})",
    )
    login_cmd.set_defaults(func=cmd_login)

    logout_cmd = subparsers.add_parser(
        "logout",
        help="Logout from an enterprise source",
    )
    logout_cmd.add_argument(
        "--org",
        default="",
        help="Organization slug to logout from (required if multiple orgs configured)",
    )
    logout_cmd.set_defaults(func=cmd_logout)

    config_cmd = subparsers.add_parser(
        "config",
        help="Manage CLI configuration",
    )
    config_subparsers = config_cmd.add_subparsers(dest="config_action")
    config_list_cmd = config_subparsers.add_parser(
        "list",
        help="List configured enterprise sources",
    )
    config_list_cmd.set_defaults(func=cmd_config_list)
    # config 命令默认行为也是 list
    config_cmd.set_defaults(func=cmd_config_list)

    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    config_path = Path(f"{DEFAULT_CLI_HOME}/{CLI_CONFIG_NAME}").expanduser().resolve()
    command = str(getattr(args, "command", "")).strip()
    # Automatic OTA check runs for all commands except explicit self-upgrade.
    should_check_startup_upgrade = (
        command != "self-upgrade"
        and os.environ.get(SELF_UPGRADE_REEXEC_ENV, "") != "1"
        and not bool(getattr(args, "skip_self_upgrade", False))
        and should_run_startup_self_upgrade(config_path)
    )
    if should_check_startup_upgrade:
        upgraded = startup_self_upgrade_check(config_path=config_path)
        if upgraded:
            env = os.environ.copy()
            env[SELF_UPGRADE_REEXEC_ENV] = "1"
            os.execve(sys.executable, [sys.executable, *sys.argv], env)
    args.func(args)


if __name__ == "__main__":
    main()
