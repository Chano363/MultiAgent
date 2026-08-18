"""
规则式 ATP（自动列车防护）安全层。

在 RL 智能体输出动作、喂给列车动力学之前，做规则式安全拦截与修正。
仿照工程上 ATP 的安全防护理念，但以可微分/可插拔的纯规则实现：

约束集（当前版本）：
1. 限速（overspeed protection）
   - 每节车速度不得超过最大运行速度（默认取自机车 max_speed_mps）
   - 超过限速时，禁止继续牵引，必要时强制施加制动（service）
2. 车钩力上限（coupler force limit）
   - 每节车受到的 |车钩力| 不得超过车钩力上限（默认 1000 kN）
   - 超限时，抑制进一步加剧车钩力的牵引动作
3. 列车间距下限（gap protection）
   - 相邻车钩间距不得小于安全下限，防止挤压
   - 间距过小（后车逼近前车）时，禁止后车继续加速

设计原则：
- 纯规则、无学习参数，训练/推理都可用，作为硬性安全兜底
- 动作修正采用"逐规则最小干预"：命中某条规则就把对应动作钳制到安全值
- 所有被触发/修正的事件写入 last_events，供指标统计

后续可在此基础上叠加 CBF（控制障碍函数，QP 求解）做理论对标。
"""

import numpy as np

# 默认车钩力上限（牛顿）= 1000 kN（用户指定的最终硬指标）
DEFAULT_COUPLER_FORCE_LIMIT_N = 1.0e6


class SafetyLayer:
    """
    规则式 ATP 安全层。

    Args:
        num_vehicles: 车辆数
        max_speed_mps: 最大运行速度（米/秒），用于限速防护
        coupler_force_limit_n: 车钩力上限（牛顿），默认 1000 kN
        min_gap_m: 最小安全车钩间距（米），用于间距防护
    """

    def __init__(
        self,
        num_vehicles: int,
        max_speed_mps: float = 30.0,
        coupler_force_limit_n: float = DEFAULT_COUPLER_FORCE_LIMIT_N,
        min_gap_m: float = 0.1,
        coupler_force_limit_emergency_n: float = None,
        coupler_override: str = 'release',
    ):
        self.num_vehicles = num_vehicles
        self.max_speed_mps = max_speed_mps
        self.coupler_force_limit_n = coupler_force_limit_n
        self.min_gap_m = min_gap_m
        # 车钩力超限时的干预策略（8/18 修正，避免 E3 改动破坏第1层）：
        # - 'release'（默认，原行为）：制动完全钳制为 0（释放），保持速度，第1层单列用
        # - 'min_brake'（E3 修复）：制动降到 MIN 档保留制动，避免长大下坡"释放→再制动"死锁，第2层多列用
        self.coupler_override = coupler_override
        # Fu2019 区分正常运行/紧急制动的车钩力上限。
        # 默认紧急制动上限 = 2.25 * 正常运行上限（Fu2019: 1000/2250 kN）
        self.coupler_force_limit_emergency_n = (
            coupler_force_limit_emergency_n
            if coupler_force_limit_emergency_n is not None
            else 2.25 * coupler_force_limit_n
        )
        self.last_events = []

    def reset(self):
        """重置安全事件记录。"""
        self.last_events = []

    def _log(self, vehicle_idx, rule: str, detail: str = ""):
        self.last_events.append({
            'vehicle': int(vehicle_idx),
            'rule': rule,
            'detail': detail,
        })

    def protect(self, actions: np.ndarray, obs_state: dict) -> np.ndarray:
        """
        对智能体输出的动作做安全修正。

        Args:
            actions: 原始动作（长度 = 车辆数），>0 牵引，<0 制动
            obs_state: 当前动力学状态快照，需包含：
                - 'vel': 每节车速度（m/s）
                - 'coupler_forces': 每节车受到的|车钩力|（N）
                - 'gaps': 相邻车钩间距（m），gaps[i] = pos[i-1]-pos[i]

        Returns:
            修正后的动作数组（与 actions 同形状）
        """
        self.last_events = []
        actions = np.asarray(actions, dtype=float).copy()
        if actions.shape[0] != self.num_vehicles:
            raise ValueError(f"动作维度应为 {self.num_vehicles}, 实际 {actions.shape[0]}")

        vel = np.asarray(obs_state.get('vel', np.zeros(self.num_vehicles)), dtype=float)
        coupler_forces = np.asarray(
            obs_state.get('coupler_forces', np.zeros(self.num_vehicles)), dtype=float
        )
        gaps = np.asarray(obs_state.get('gaps', np.full(self.num_vehicles, self.min_gap_m)), dtype=float)
        # 是否紧急制动工况（Fu2019 区分上限：紧急制动允许更大车钩力）
        is_emergency = bool(obs_state.get('emergency', False))
        coupler_limit = (
            self.coupler_force_limit_emergency_n
            if is_emergency else self.coupler_force_limit_n
        )

        # 规则 1：限速防护
        for i in range(self.num_vehicles):
            if vel[i] >= self.max_speed_mps - 1e-6:
                if actions[i] > 0:
                    # 已达限速，禁止继续牵引，强制常用制动
                    self._log(i, 'overspeed', f'v={vel[i]:.2f}')
                    actions[i] = min(actions[i], -0.75)
                elif actions[i] >= 0:
                    actions[i] = 0.0  # 钳制为缓解

        # 规则 2：车钩力上限防护（区分正常运行/紧急制动上限，Fu2019）
        # 车钩力超限干预策略（coupler_override，8/18 修正）：
        # - 'min_brake'：降低制动到 MIN 档（保留制动，避免长大下坡"释放→再制动"死锁，
        #   用于第2层多列协同；E3 修复，实测消除车钩力超限暴涨 625次→0）
        # - 'release'（默认）：制动完全钳制为 0（释放），用于第1层单列循环制动
        #   （E3 改动曾让第1层掉速到0：车钩力超限→仍保持MIN制动→持续减速→掉速，
        #   8/18 恢复第1层为 release，保持速度保持能力）
        MIN_BRAKE = -0.3   # 对应 AirBrakeNotch.MIN（0.2倍制动力，braking.py）
        for i in range(self.num_vehicles):
            if coupler_forces[i] >= coupler_limit:
                mode = 'emergency' if is_emergency else 'normal'
                self._log(i, 'coupler_force_limit', f'|F|={coupler_forces[i]/1e3:.0f}kN({mode})')
                if actions[i] > 0.0:
                    # 牵引加剧冲动 → 完全钳制为 0
                    actions[i] = 0.0
                elif actions[i] < 0.0 and self.coupler_override == 'min_brake':
                    # 制动：降低到 MIN 档（保留必要制动，长大下坡不能完全释放）
                    actions[i] = max(actions[i], MIN_BRAKE)
                elif actions[i] < 0.0:
                    # 'release'：制动完全钳制为 0（释放，保持速度，第1层用）
                    actions[i] = 0.0

        # 规则 3：间距防护（后车逼近前车时禁止继续加速）
        for i in range(1, self.num_vehicles):
            if gaps[i] <= self.min_gap_m + 1e-6:
                if actions[i] > 0:
                    self._log(i, 'min_gap', f'gap={gaps[i]:.3f}m')
                    actions[i] = 0.0

        return actions
