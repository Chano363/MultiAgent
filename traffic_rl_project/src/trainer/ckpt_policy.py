"""统一训练框架：CkptNamer —— 各产线 checkpoint 命名协议（评估入口零改动）。

必须保持 evaluate_l1_long / evaluate_decompose 的 glob 兼容（`evaluate_m1_m3_long` 已按
ADR-022 删除）：
  l1         -> cyclic_mappo_best_seed{s}_v{vmin}-{vmax}_init{init}.pt
  fleet      -> mappo_fleet_best_{cp_tag}_seed{s}.pt (+ ep{gep+1}_...)
  coor_dqn   -> coor_dqn_best_seed{s}_train{i}.pt (i in [0,num_trains))
  dqn_cyclic -> dqn_cyclic_best_seed{s}.pt
"""
import math


class CkptNamer:
    """best_path(seed)->str / periodic_path(gep,seed)->str|None / history_tag(seed)->str."""

    def best_path(self, seed) -> str:
        raise NotImplementedError

    def periodic_path(self, global_ep, seed):
        return None

    def history_tag(self, seed) -> str:
        return f"{self.tag}_seed{seed}"

    def save_every(self) -> int:
        return 0


def make_cp_tag(cfg, act_dim: int) -> str:
    """复刻 train_fleet 的 cp_tag scheme。"""
    decompose = bool(cfg.env_cfg.get('decompose', False))
    part1 = f"{'dec_' if decompose else ''}ad{act_dim}"
    part2 = 'g' if cfg.group_obs else ''
    part3 = f"_{'m' + cfg.mask_lever}" if cfg.mask_lever and cfg.mask_lever != 'none' else ''
    part4 = f"_{'cp' if cfg.env_cfg.get('use_coupler_constraint', True) else 'nocp'}"
    return part1 + part2 + part3 + part4


class L1CkptNamer(CkptNamer):
    def __init__(self, cfg, act_dim=1):
        self.cfg = cfg
        self.tag = "l1"

    def best_path(self, seed):
        return (f"cyclic_mappo_best_seed{seed}_v40-80"
                f"_init{int(self.cfg.init_speed_kmh)}.pt")


class FleetCkptNamer(CkptNamer):
    def __init__(self, cfg, act_dim):
        self.cfg = cfg
        self.act_dim = act_dim
        self.cp_tag = make_cp_tag(cfg, act_dim)
        self.tag = f"{self.cp_tag}"

    def best_path(self, seed):
        return f"mappo_fleet_best_{self.cp_tag}_seed{seed}.pt"

    def periodic_path(self, global_ep, seed):
        return f"mappo_fleet_ep{int(global_ep) + 1}_{self.cp_tag}_seed{seed}.pt"

    def history_tag(self, seed):
        return f"{self.cp_tag}_seed{seed}"


class CoorDqnCkptNamer(CkptNamer):
    def __init__(self, cfg, num_trains):
        self.cfg = cfg
        self.num_trains = num_trains
        self.tag = "coor_dqn"

    def best_path(self, seed):
        return f"coor_dqn_best_seed{seed}_train0.pt"

    def all_best_paths(self, seed):
        return [f"coor_dqn_best_seed{seed}_train{i}.pt" for i in range(self.num_trains)]


class DqnCyclicCkptNamer(CkptNamer):
    def __init__(self, cfg, act_dim=1):
        self.cfg = cfg
        self.tag = "dqn_cyclic"

    def best_path(self, seed):
        return f"dqn_cyclic_best_seed{seed}.pt"


def make_namer(cfg, act_dim=None, num_trains=3) -> CkptNamer:
    policy = cfg.ckpt_policy
    if policy == 'l1':
        return L1CkptNamer(cfg)
    if policy == 'fleet':
        return FleetCkptNamer(cfg, act_dim=act_dim or int(cfg.env_cfg.get('action_dim', 1) or 1))
    if policy == 'coor_dqn':
        return CoorDqnCkptNamer(cfg, num_trains=num_trains)
    if policy == 'dqn_cyclic':
        return DqnCyclicCkptNamer(cfg)
    raise KeyError(f"[ckpt] 未支持 ckpt_policy: {policy}")