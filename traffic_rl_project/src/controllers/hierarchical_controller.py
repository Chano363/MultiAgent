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


class HierarchicalController:
    """每列的分层控制器：RL 第1层策略控速 + 协同调整叠加。"""

    def __init__(
        self,
        layer1_checkpoint: str,
        num_vehicles: int,
        coupler_force_limit_n: float,
        target_speed: float,
        device: str = 'cuda',
        adj_coef: float = 0.3,
        layer1_target_speed: float = 20.0,
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
        """RL 第1层策略的基础 throttle（列内控速，deterministic/随机）。"""
        obs = self.layer1_obs(train_env)
        action, _ = self.layer1.select_actions(obs.flatten(), deterministic=False)
        return float(np.clip(action[0], -1.0, 1.0))

    def get_action(self, train_env, coor_adj: float) -> np.ndarray:
        """最终列级动作：第1层策略 throttle + adj_coef*协同调整，广播到所有车厢。"""
        base = self.base_throttle(train_env)
        throttle = float(np.clip(base + self.adj_coef * coor_adj, -1.0, 1.0))
        return np.full(self.num_vehicles, throttle)
