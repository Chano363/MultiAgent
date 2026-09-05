"""实验元数据自动落盘：与权重/日志同目录生成 metadata.json。

【重构 2026-09-05】所有实验数值必须来自 metadata.json / 评估 JSON，
禁止从代码注释复制实验数值当结论。
"""
import os
import sys
import json
import hashlib
import subprocess


def git_commit(project_root: str) -> str:
    try:
        r = subprocess.run(["git", "-C", project_root, "rev-parse", "HEAD"],
                          capture_output=True, text=True)
        return r.stdout.strip() if r.returncode == 0 else ""
    except Exception:
        return ""


def physics_version(world_cfg: dict) -> str:
    """物理配置版本 = 配置内容哈希（前 12 位），供历史资产比对。"""
    h = hashlib.sha1(json.dumps(world_cfg, sort_keys=True, default=str).encode())
    return h.hexdigest()[:12]


def build_metadata(project_root: str, case: str, world_cfg: dict, seed, entry: str,
                   extra: dict = None) -> dict:
    """构造元数据字典（供 save_metadata 落盘，或评估脚本内嵌进结果 JSON）。"""
    meta = {
        "git_commit": git_commit(project_root),
        "physics_version": physics_version(world_cfg),
        "simcase": case,
        "seed": seed,
        "entry": os.path.basename(entry),
        "physics": world_cfg,
        "python": sys.version,
    }
    if extra:
        meta.update(extra)
    return meta


def save_metadata(exp_dir: str, *, project_root: str, case: str,
                  world_cfg: dict, seed, entry: str,
                  extra: dict = None) -> str:
    """写 metadata.json 到 exp_dir（不存在则创建），返回写入路径。"""
    os.makedirs(exp_dir, exist_ok=True)
    meta = build_metadata(project_root=project_root, case=case, world_cfg=world_cfg,
                          seed=seed, entry=entry, extra=extra)
    path = os.path.join(exp_dir, "metadata.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2)
    return path