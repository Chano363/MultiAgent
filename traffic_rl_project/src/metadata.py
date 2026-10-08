"""实验元数据自动落盘：与权重/日志同目录生成 metadata.json。

【重构 2026-09-05】所有实验数值必须来自 metadata.json / 评估 JSON，
禁止从代码注释复制实验数值当结论。

【2026-09-06 防漏守卫】任何训练入口都应调用 save_metadata() 生成权威
元数据，并在训练结束用 assert_training_metadata() 强制校验；或直接包
training_metadata_guard() 一次到位——自动生成且不可被遗忘（替代逐个脚本手补）。
"""
import os
import sys
import json
import hashlib
import subprocess
from contextlib import contextmanager


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


# ---------------------------------------------------------------------------
# 仿真器/物理模型「型号」语义标签（可复现关键字段之一）。
# 当前物理锚定（2026-09-08，ADR-011）：统一的 MT-2 摩擦式缓冲器 + 空气制动缓解波
# 传播（官方基线）。若耦合器型号 / 制动缓解模型 / 动力学实现发生替换，必须同步
# 更新下面 _SIM_MODEL_FIXED（否则 physics_version 哈希不感知模型替换）。
# 该串与 simcase + 配置派生项共同构成 metadata.simulator_model。
_SIM_MODEL_FIXED = "NeTrainSim-multibody|coupler=MT-2|braking=ED+AB-relief-wave"


def simulator_model(simcase: str, world_cfg: dict) -> str:
    """返回人类可读的仿真器型号串：固定物理 + simcase + 配置派生项。

    world_cfg = official_world_config() 形态：顶层放治理开关，physics 字典放
    PhysicsConfig 全部字段。取值容错，缺省用 None 兜底，不抛错。
    """
    ph = world_cfg.get("physics", {}) if isinstance(world_cfg, dict) else {}
    if not isinstance(ph, dict):
        ph = {}

    def g(key, default="-"):
        for src in (world_cfg, ph):
            if isinstance(src, dict) and key in src and src[key] is not None:
                return src[key]
        return default

    parts = [
        _SIM_MODEL_FIXED,
        f"simcase={simcase}",
        f"cyclic_degrade={bool(g('enable_cyclic_degrade', False))}",
        f"consist={g('consist_preset')}",
        f"grade={g('grade_profile')}",
    ]
    return "|".join(parts)


def simulator_model_version(simcase: str, world_cfg: dict) -> str:
    """仿真器型号的稳定哈希（前 12 位），供机器比对：型号串不变→哈希不变。"""
    return hashlib.sha1(simulator_model(simcase, world_cfg).encode()).hexdigest()[:12]


def _resolve_critic(extra: dict) -> str:
    """提取本次运行的 critic 价值头模式（ADR-021 方向 B）。

    来源说明：build_metadata 无 cfg 入参，训练入口（train_runner）已把整份
    cfg_to_dict(cfg) 放进 extra['hyperparameters']，故从 algo_params.critic 取。
    任何缺失/异常都回退 'centralized_scalar'，保证 metadata 生成不失败。
    """
    try:
        hp = (extra or {}).get("hyperparameters") or {}
        algo_params = hp.get("algo_params") or {}
        return algo_params.get("critic", "centralized_scalar")
    except Exception:
        return "centralized_scalar"


def _resolve_reward_schema() -> str:
    """读取环境模块级常量 REWARD_SCHEMA（由并行改造的 train_fleet_env 提供）。

    导入失败或常量不存在时用 getattr 兜底为 'unknown'，绝不让 metadata 生成失败。
    """
    try:
        import importlib
        mod = importlib.import_module("src.environments.train_fleet_env")
        return getattr(mod, "REWARD_SCHEMA", "unknown")
    except Exception:
        return "unknown"


def _resolve_ed_mod_coef() -> float:
    """ED 调制带宽（动作通道语义，ADR-024）：从**权威实现**读默认值，禁止手抄。

    该系数是"策略动作 ed_mod → 实际 ED 变化量"的换算（final_ed = baseline_ed +
    ed_mod_coef · ed_mod），属**动作空间语义** —— 换值即换策略含义（同一 ckpt 行为不同），
    故必须进 metadata 才能比对历史运行。读取失败回退 -1.0（哨兵值，不抛错）。
    """
    try:
        import inspect
        from src.controllers.multi_loco_controller import MultiLocoController
        return float(inspect.signature(
            MultiLocoController.get_action_decomposed).parameters['ed_mod_coef'].default)
    except Exception:
        return -1.0


def build_metadata(project_root: str, case: str, world_cfg: dict, seed, entry: str,
                   extra: dict = None) -> dict:
    """构造元数据字典（供 save_metadata 落盘，或评估脚本内嵌进结果 JSON）。"""
    meta = {
        "git_commit": git_commit(project_root),
        "physics_version": physics_version(world_cfg),
        "simulator_model": simulator_model(case, world_cfg),
        "simulator_model_version": simulator_model_version(case, world_cfg),
        "simcase": case,
        "seed": seed,
        "entry": os.path.basename(entry),
        "physics": world_cfg,
        "python": sys.version,
    }
    if extra:
        meta.update(extra)
    # 【ADR-021 方向 B】新增两项溯源键（不改动既有任何键；γ/λ 仍随 hyperparameters.algo_params 落盘）
    meta["critic"] = _resolve_critic(extra)
    meta["reward_schema"] = _resolve_reward_schema()
    # 【ADR-023】动作通道带宽（动作空间语义，换值即换策略含义）
    meta["ed_mod_coef"] = _resolve_ed_mod_coef()
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


def assert_training_metadata(results_dir: str) -> str:
    """训练结束强制校验权威 metadata.json 已生成；缺失 → 抛错（防悄悄丢元数据）。"""
    path = os.path.join(results_dir, "metadata.json")
    if not os.path.isfile(path):
        raise RuntimeError(
            f"[metadata-guard] 训练结束仍缺 metadata.json：{path}\n"
            "训练入口必须落权威元数据（save_metadata/guard），禁止静默通过")
    return path


@contextmanager
def training_metadata_guard(results_dir: str, *, world_cfg: dict, seed,
                            project_root: str = None, simcase: str = "official",
                            entry: str = None, extra: dict = None):
    """训练元数据守卫：进入自动写 metadata.json，训练结束强制校验存在。

    用法：把训练主体放进 with 里即可，自动生成、且结束时若缺失会抛错。
         with training_metadata_guard(results_dir, world_cfg=world_cfg, seed=seed,
                                      simcase='official', entry=__file__,
                                      extra={"hyperparameters": ...}):
             ...训练循环...
    """
    path = save_metadata(results_dir, project_root=project_root or os.getcwd(),
                         case=simcase, world_cfg=world_cfg, seed=seed,
                         entry=entry or "training", extra=extra)
    try:
        yield path
    finally:
        assert_training_metadata(results_dir)