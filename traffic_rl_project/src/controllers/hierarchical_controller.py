"""
分层控制器（层级二）：第1层策略负责列内控速，层级一（第2层）RL 叠加协同调整。

【分层框架（论文核心）】
- 层级一（第2层）：多列 MARL 智能体 = 每列，输出"协同调整量" δ ∈ [-1,1]
  （如：离前列太近 → 额外制动；太远 → 额外牵引）
- 层级二（本文件）：第1层已训练策略（train_cyclic_braking，已验证车钩力150kN/速度71km/h）
  负责单列基础控速（陡坡温和制动 + 缓坡及时牵引），保证速度区间。

最终 throttle = clip(base_throttle + adj_coef * δ, -1, 1)，再经车钩力安全层钳制。
这样第2层 RL 只需学"如何在已能控速的基础上协同"，而非从零学控速。

依据：论文分层框架（层级一生成宏观决策 + 层级二执行），魏咪《考虑车钩力约束的重载列车运行优化分层框架》。
"""

import numpy as np
from pathlib import Path
import sys

sys.path.append(str(Path(__file__).parent.parent.parent))

from src.algorithms.mappo_agent import MAPPOAgent


class HierarchicalController:
    """每列的分层控制器：第1层策略控速 + 协同调整叠加。"""

    def __init__(
        self,
        layer1_checkpoint: str,
        num_vehicles: int,
        coupler_force_limit_n: float,
        target_speed: float,
        device: str = 'cuda',
        adj_coef: float = 0.3,   # 协同调整量缩放系数（避免破坏第1层控速）
        layer1_target_speed: float = 20.0,  # 第1层训练时的 target_speed（train_cyclic_braking 用 20.0）
    ):
        # 第1层策略（单列循环制动，obs=4维, act=1维）
        self.layer1 = MAPPOAgent(
            num_drones=1, obs_per_drone=4, act_per_drone=1, device=device,
        )
        self.layer1.load(layer1_checkpoint)
        self.layer1.policy.eval()

        self.num_vehicles = num_vehicles
        self.coupler_force_limit_n = coupler_force_limit_n
        self.target_speed = target_speed
        # 8/18 bug修复：第1层策略训练时 obs[1]=vel-target_speed(20.0)，
        # 分层控制器必须用第1层训练值(20.0)，不能依赖 TrainFleetEnv 的 target_speed
        # （限速中值60km/h=16.67），否则 obs 分布不匹配→策略输出错误→掉速。
        self.layer1_target_speed = layer1_target_speed
        self.adj_coef = adj_coef

    def layer1_obs(self, train_env) -> np.ndarray:
        """构造第1层策略所需的 4 维 obs（与 train_cyclic_braking 一致）。

        注意：obs[1]=vel-target_speed 必须用第1层训练时的 target_speed(20.0)，
        不能用 TrainFleetEnv 的 target_speed。
        """
        vel = float(train_env.dynamics.vel[0])
        coupler = np.abs(train_env.dynamics._coupler_forces())
        coupler_peak = float(np.max(coupler)) if len(coupler) else 0.0
        return np.array([
            [vel, vel - self.layer1_target_speed, train_env.dynamics.pos[0] * 0.0001,
             coupler_peak / self.coupler_force_limit_n],
        ], dtype=np.float32)

    def base_throttle(self, train_env) -> float:
        """第1层策略输出的基础 throttle（列内控速，deterministic）。"""
        obs = self.layer1_obs(train_env)
        action, _ = self.layer1.select_actions(obs.flatten(), deterministic=True)
        return float(np.clip(action[0], -1.0, 1.0))

    def get_action(self, train_env, coor_adj: float) -> np.ndarray:
        """最终列级动作：base_throttle + adj_coef*协同调整，广播到所有车厢。"""
        base = self.base_throttle(train_env)
        throttle = float(np.clip(base + self.adj_coef * coor_adj, -1.0, 1.0))
        return np.full(self.num_vehicles, throttle)
