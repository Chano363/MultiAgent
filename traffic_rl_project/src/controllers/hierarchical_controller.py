"""
分层控制器（层级二）：RL 第1层策略控速（warm start 自规则循环制动）+ 层级一协同调整。

【分层框架（论文核心，2026-08-19 定位确认）】
- 层级一（第2层）：多列 MARL 智能体 = 每列，输出"协同调整量" δ ∈ [-1,1]
- 层级二（本文件）：RL 第1层策略（经 warm start 自规则循环制动初始化，缓解波下
  循环制动稳定）负责单列控速。

定位依据：E16 实测——硬规则循环制动 + RL 调整（叠加throttle或调阈值）训练不稳定
（探索破坏规则边界，avg -78万）；RL 策略（warm start 自规则）控速训练稳定
（avg +2.1万，E9 已验证）。RL 策略既"基于规则循环制动"（warm start 初始化），
又可通过 RL 稳定优化协同。

最终 throttle = clip(layer1_throttle + adj_coef * δ, -1, 1)。
"""

import numpy as np
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.algorithms.mappo_agent import MAPPOAgent
from src.safety_layer import SafetyLayer


class HierarchicalController:
    """每列的分层控制器：RL 第1层策略控速 + 协同调整叠加 + 车钩力安全钳制。

    E25 修复：分层模式原实现直接输出第1层策略 throttle，绕过车钩力安全钳制，
    导致坡段错开（方案A）下缓解不同步→车钩力超1000kN。现补上车钩力安全层
    （与 TrainLowLevelController 一致），保证车钩力 ≤1000kN。
    """

    def __init__(
        self,
        layer1_checkpoint: str,
        num_vehicles: int,
        coupler_force_limit_n: float,
        target_speed: float,
        device: str = 'cuda',
        adj_coef: float = 0.3,
        layer1_target_speed: float = 20.0,
        eval_mode: bool = False,
        line_speed_limit_mps: float = 30.0,
    ):
        # RL 第1层策略（warm start 自规则循环制动，obs=4维, act=1维）
        self.layer1 = MAPPOAgent(
            num_drones=1, obs_per_drone=4, act_per_drone=1, device=device,
        )
        self.layer1.load(layer1_checkpoint)
        self.layer1.policy.eval()

        self.num_vehicles = num_vehicles
        self.coupler_force_limit_n = coupler_force_limit_n
        self.target_speed = target_speed
        # 第1层策略训练时 obs[1]=vel-target_speed(20.0)，必须用训练值
        self.layer1_target_speed = layer1_target_speed
        self.adj_coef = adj_coef
        # 【bug修复 2026-08-20】评估/推理用确定性策略（消除 M1/M3 结果随机性，
        # 原实现 base_throttle 恒 deterministic=False，评估带随机采样，5-seed 中位数
        # 只是掩盖而非解决）。训练时 eval_mode=False 保持探索随机。
        self.eval_mode = eval_mode
        # 【bug修复 2026-08-21】限速安全层必须对齐 80km/h 线路限速。
        # 原实现 SafetyLayer 未传 max_speed_mps → 默认 30m/s=108km/h，导致长陡坡下
        # 速度飙到 117km/h 超80不受控（只保护108）。现传 line_speed_limit_mps（80/3.6）。
        self._safety = SafetyLayer(
            num_vehicles=num_vehicles,
            max_speed_mps=line_speed_limit_mps,
            coupler_force_limit_n=coupler_force_limit_n,
            coupler_override='min_brake',
        )

    def layer1_obs(self, train_env) -> np.ndarray:
        """构造第1层策略所需的 4 维 obs（与 train_cyclic_braking 一致）。"""
        vel = float(train_env.dynamics.vel[0])
        coupler = np.abs(train_env.dynamics._coupler_forces())
        coupler_peak = float(np.max(coupler)) if len(coupler) else 0.0
        return np.array([
            [vel, vel - self.layer1_target_speed, train_env.dynamics.pos[0] * 0.0001,
             coupler_peak / self.coupler_force_limit_n],
        ], dtype=np.float32)

    def base_throttle(self, train_env) -> float:
        """RL 第1层策略的基础 throttle（列内控速）。

        deterministic 由 eval_mode 决定：训练（探索）随机采样，评估/推理取均值。
        """
        obs = self.layer1_obs(train_env)
        action, _ = self.layer1.select_actions(
            obs.flatten(), deterministic=self.eval_mode,
        )
        return float(np.clip(action[0], -1.0, 1.0))

    def _state_snapshot(self, train_env) -> dict:
        """构造安全层需要的状态快照（与 TrainLowLevelController 一致）。

        【bug修复 2026-08-20】原实现 gaps 全 0，导致 SafetyLayer 规则3 恒触发、
        列内正牵引被错误钳制。现正确计算 gaps[i]=pos[i-1]-pos[i]。
        """
        dyn = train_env.dynamics
        n = train_env.num_vehicles
        pos = dyn.pos
        gaps = np.full(n, 0.1)  # min_gap_m 兜底（与 SafetyLayer 默认一致）
        for i in range(1, n):
            gaps[i] = pos[i - 1] - pos[i]
        return {
            'vel': np.array(dyn.vel, dtype=float),
            'coupler_forces': np.array(np.abs(dyn._coupler_forces()), dtype=float),
            'gaps': gaps,
            'emergency': False,
        }

    def get_action(self, train_env, coor_adj: float) -> np.ndarray:
        """最终列级动作：第1层策略 throttle + adj_coef*协同调整，广播到所有车厢。
        叠加 δ 后应用车钩力安全钳制（接近上限预缓和 + SafetyLayer.protect），
        保证车钩力 ≤1000kN（E25 修复）。
        """
        base = self.base_throttle(train_env)
        throttle = float(np.clip(base + self.adj_coef * coor_adj, -1.0, 1.0))

        # 车钩力接近上限预缓和（与 TrainLowLevelController 一致）：车钩力越高，
        # 允许的牵引/制动幅度越小，避免动作冲过上限。
        snapshot = self._state_snapshot(train_env)
        coupler_peak = float(np.max(snapshot['coupler_forces'])) if self.num_vehicles else 0.0
        if coupler_peak > 0:
            ratio = coupler_peak / max(self.coupler_force_limit_n, 1e-6)
            if ratio > 0.8:
                scale = max(1.0 - (ratio - 0.8) / 0.2, 0.0)  # 0.8→1.0 时 scale 1→0
                throttle *= scale

        # 列级动作 + SafetyLayer 车钩力钳制（超限时修正）
        actions = np.full(self.num_vehicles, throttle)
        actions = self._safety.protect(actions, snapshot)
        return actions
