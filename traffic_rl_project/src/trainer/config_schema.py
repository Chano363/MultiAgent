"""统一训练框架：ExperimentConfig + YAML 载入/校验。

配置承载 = YAML 实验文件（configs/experiments/*.yaml）+ run_training.py 命令行覆盖。
注意项目规则：YAML 用十进制（禁科学计数法）；.get() 路径与字段精确匹配。
"""
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional, List

import yaml


@dataclass
class CkptDirs:
    """checkpoint / 结果目录（允许各产线写不同子目录以镜像旧路径）。"""
    checkpoint_dir: str = "outputs/checkpoints"
    results_dir: str = "outputs/results"
    figures_dir: str = "outputs/figures"


@dataclass
class ExperimentConfig:
    """一次训练的完整规格。后续新增实验线 = 新增/改一个 YAML，不写代码。"""

    # 身份
    name: str = "experiment"                # 实验线名（checkpoint/history tag 来源之一）
    seed: int = 0
    device: Optional[str] = None            # None -> 自动 cuda/cpu
    omp_num_threads: Optional[int] = 2      # 多进程防线程超订阅

    # 算法
    algorithm: str = "mappo"                # 'mappo'|'dqn'|'coor_dqn'
    algo_params: dict = field(default_factory=dict)

    # 环境
    env_type: str = "fleet"                 # 'single'(TrainFormationEnv)|'fleet'(TrainFleetEnv)
    env_cfg: dict = field(default_factory=dict)

    # obs/action/reward
    obs: str = "env"                        # 'env'|'cyclic'
    action: str = "continuous"              # 'continuous'|'notch'|'coor_adj'
    reward: str = "env_default"             # 'env_default'|'cyclic'
    reward_params: dict = field(default_factory=dict)

    # 交互策略选择器（决定内层逐步契约）
    interaction: str = "mappo_fleet"        # 'mappo_single'|'mappo_fleet'|'dqn_single'|'coor_dqn_fleet'

    num_trains: int = 3
    decision_interval: int = 1

    # 训练调度
    episodes: int = 200
    curriculum: Optional[str] = None        # '300-1000-15000' 或 '1000:66,3000:132'
    start_ep: int = -1                      # 全局起始回合号（分块续训）
    init_speed_kmh: float = 65.0
    random_init_speed: bool = False
    init_speed_min: float = 55.0
    init_speed_max: float = 75.0
    warm_start: bool = False                # L1 BC 预训练
    bc_episodes: int = 3
    bc_epochs: int = 5
    brake_notch: float = -0.8
    resume: str = ""                        # 续训 checkpoint 路径（空=None；支持 'latest'）
    resume_weights_only: bool = False       # 续训只加载网络权重并重置优化器/value_norm
                                            # （跨物理版本迁移用；见 src/trainer/resume.py）
    mask_lever: str = "none"                # 消融：'ab'|'ed'|'none'（进 cp_tag 'g'）
    group_obs: bool = False                 # 全局一致性观测（进 cp_tag 'g'）
    # 【2026-09-10 并行多环境】治 on-policy 单条长轨迹 advantage/value 失稳。
    # n_env>1 时每个 ep 并行跑 n_env 条独立短轨迹（不同 init_speed），同一 agent 共享
    # buffer 一次 update → advantage 信噪比×n_env，且 value 不被单条 2500+ 步轨迹绑架。
    n_env: int = 1                          # 并行 rollout 环境数（1=原单轨迹）
    # 【2026-10-07 进程级并行】n_env>1 时原本串行跑（单核），本开关改走进程池并行
    # （见 src/trainer/parallel_rollout.py），用满多核；默认关（零回归）。
    # 仅 interaction='mappo_fleet' + obs='env' + reward!='cyclic' + 非异构时生效。
    # ⚠️ 与串行版数值不逐位相同（每轨迹独立 RNG 种子），但同 seed 可复现。
    n_env_parallel: bool = False
    parallel_traj_len: int = 0              # 并行轨迹长度；0=沿用 curriculum horizon
    env_gap: float = 0.0                    # 并行各 env 的初始列间距偏移（米），增加多样性
    # 【2026-09-22 长程评估选优】诊断-2026-09-22：训练窗口(1200步≈2.4km)reward 最优
    # ≠ 完整剖面评估最优，best 按训练 reward 选会选出"短视激进"长程崩的权重。
    # 启用后 best 文件改由"周期性完整剖面确定性评估"驱动（按 viol/车钩力/末速 选优），
    # 训练 reward 不再直接写 best。0=关闭（默认，完全兼容旧行为）。
    long_eval_interval: int = 0             # 每 N ep 跑一次完整剖面评估（0=关闭）
    long_eval_steps: int = 36000            # 评估时域（36000=53km 全程；跨线目标按其剖面长度）
    long_eval_grade: str = ""               # 评估剖面（空=沿用训练 grade_profile）
    long_eval_init_speed_kmh: float = 80.0  # 评估初始速度（对齐评估脚本默认 80km/h）
    # 【YOLO 式日志】tensorboard/tqdm/每集 CSV/last.pt。缺依赖自动降级，不中断训练。
    yolo_logging: bool = True               # 总开关
    yolo_tb: bool = True                    # TensorBoard scalars（false 只留 CSV+tqdm）

    # checkpoint / 治理
    ckpt_policy: str = "fleet"              # 'l1'|'fleet'|'coor_dqn'|'dqn_cyclic'
    simcase: str = "official"
    log_interval: int = 10
    dirs: CkptDirs = field(default_factory=CkptDirs)

    # 便捷访问
    @property
    def results_dir(self) -> str:
        return self.dirs.results_dir

    @results_dir.setter
    def results_dir(self, v: str):
        self.dirs.results_dir = v

    @property
    def checkpoint_dir(self) -> str:
        return self.dirs.checkpoint_dir

    @checkpoint_dir.setter
    def checkpoint_dir(self, v: str):
        self.dirs.checkpoint_dir = v

    @property
    def figures_dir(self) -> str:
        return self.dirs.figures_dir


def _apply_override(cfg: ExperimentConfig, key: str, value):
    """把 'a.b=value' 覆盖写到 cfg（支持 dict 字段 env_cfg/algo_params/reward_params 与 dirs）。"""
    value = _coerce(value)
    parts = key.split('.')
    if parts[0] == "dirs" and len(parts) == 2:
        if parts[1] not in CkptDirs.__dataclass_fields__:
            raise KeyError(f"[config] 未知 dirs 字段：{parts[1]}")
        setattr(cfg.dirs, parts[1], value)
        return
    dict_fields = ("env_cfg", "algo_params", "reward_params")
    if parts[0] in dict_fields:
        if len(parts) != 2:
            raise ValueError(f"[config] {parts[0]} 覆盖需 2 段：{key}")
        getattr(cfg, parts[0])[parts[1]] = value
        return
    if parts[0] not in ExperimentConfig.__dataclass_fields__:
        raise KeyError(f"[config] 未知覆盖字段：{key}")
    if len(parts) != 1:
        raise ValueError(f"[config] 字段 {parts[0]} 不支持多级路径：{key}")
    setattr(cfg, parts[0], value)


def _coerce(value):
    if value in ("true", "True"):
        return True
    if value in ("false", "False"):
        return False
    if value in ("null", "None"):
        return None
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def apply_overrides(cfg: ExperimentConfig, overrides: List[str]) -> ExperimentConfig:
    """--override key=value ... 覆盖。只允许改既有字段（防拼错静默回退默认）。"""
    for ov in overrides or []:
        if "=" not in ov:
            raise ValueError(f"[config] override 需 key=value 形式：{ov}")
        key, val = ov.split("=", 1)
        _apply_override(cfg, key.strip(), val.strip())
    return cfg


def parse_experiment_yaml(path, overrides: Optional[List[str]] = None) -> ExperimentConfig:
    """载入实验 YAML 为 ExperimentConfig（含 CLI 覆盖）。"""
    p = Path(path)
    if not p.exists():
        raise FileNotFoundError(f"[config] 未找到实验配置：{p}")
    with open(p, encoding="utf-8") as f:
        raw = yaml.safe_load(f) or {}
    cfg = ExperimentConfig()
    _merge_into(cfg, raw)
    return apply_overrides(cfg, overrides or [])


def _merge_into(cfg: ExperimentConfig, raw: dict):
    """把 YAML dict 映射到 dataclass；未知顶层字段抛出（杜绝静默回退默认）。"""
    fields = set(ExperimentConfig.__dataclass_fields__)
    nested_map = {
        "algo_params": "algo_params",
        "env_cfg": "env_cfg",
        "reward_params": "reward_params",
    }
    for k, v in raw.items():
        if k in ("dirs", "CkptDirs"):
            d = cfg.dirs if isinstance(cfg.dirs, CkptDirs) else CkptDirs()
            for dk, dv in v.items():
                if dk in CkptDirs.__dataclass_fields__:
                    setattr(d, dk, dv)
            cfg.dirs = d
            continue
        if k in nested_map:
            setattr(cfg, k, dict(v or {}))
            continue
        if k not in fields:
            raise KeyError(f"[config] 未知配置字段：{k}（检查 YAML 与 ExperimentConfig）")
        setattr(cfg, k, v)

    # 支持 YAML 里 dirs.scalar 嵌套与顶层 checkpoint_dir/results_dir 简写
    if isinstance(cfg.dirs, dict):
        cfg.dirs = CkptDirs(**cfg.dirs)
    if not isinstance(cfg.dirs, CkptDirs):
        cfg.dirs = CkptDirs()


def cfg_to_dict(cfg: ExperimentConfig) -> dict:
    return asdict(cfg)