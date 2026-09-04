"""
规则式 ATP（自动列车防护）安全层。

在 RL 智能体输出动作、喂给列车动力学之前，做规则式安全拦截与修正。
**升级**：ETCS 目标距离超速防护曲线（"真 ATP"）——前瞻式 EBD/EBI 监督，
取代原反应式"vel≥限速→强制制动"软修正，回应"ATP 是假的"质疑。

约束集：
1. **ETCS 目标距离限速防护**（前瞻，"真 ATP"）：
   - 若 obs_state 提供 `etcs_targets` 和 `etcs_curve`，则对每个前方目标点（降速/停车/间距）
     计算 EBD/EBI 监督限位，当前速度超过 EBI 强制紧急制动，超过 P 强制 service 制动。
2. 简单反应式限速防护（向后兼容，默认/无目标时保留）：
   - 每节车速度不得超过最大运行速度，超过时强制施加 service 制动。
3. 车钩力上限（coupler force limit）
   - 每节车受到的 |车钩力| 不得超过车钩力上限（默认 1000 kN）
   - 超限时，抑制进一步加剧车钩力的牵引动作
4. 列车间距下限（gap protection）
   - 相邻车钩间距不得小于安全下限，防止挤压
   - 间距过小（后车逼近前车）时，禁止后车继续加速

诚实边界：本模块只做车载超速/限速监督，不做闭塞/信号层的进场授权；
"防追尾属信号级 ATP 职权，我们补充车钩力 + 缩短安全间隔"的叙事据此成立。

设计原则：
- 纯规则、无学习参数，训练/推理都可用，作为硬性安全兜底
- 动作修正采用"逐规则最小干预"：命中某条规则就把对应动作钳制到安全值
- 所有被触发/修正的事件写入 last_events，供指标统计
- 无 ETCS 配置时完全回退原逻辑，保持向后兼容

后续可在此基础上叠加 CBF（控制障碍函数，QP 求解）做理论对标。
"""

import numpy as np

# 导入 ETCS 曲线模块（真 ATP）
from .train_dynamics.etcs_braking import EtcsBrakingCurve, EbdTarget

# 默认车钩力上限（牛顿）= 1000 kN（用户指定的最终硬指标）
DEFAULT_COUPLER_FORCE_LIMIT_N = 1.0e6
FULL_SERVICE_BRAKE = -0.75  # 强制 full service 制动（AirBrakeNotch.SERVICE 对应 ~0.75）
MIN_BRAKE = -0.3           # MIN 制动（AirBrakeNotch.MIN 对应 ~0.3）
EMERGENCY_BRAKE = -1.0    # 紧急制动（AirBrakeNotch.EMERGENCY 对应 1.0 系数）


class SafetyLayer:
    """
    规则式 ATP 安全层。支持 ETCS 目标距离超速防护（真 ATP）。

    Args:
        num_vehicles: 车辆数
        max_speed_mps: 最大运行速度（米/秒），用于限速防护
        coupler_force_limit_n: 车钩力上限（牛顿），默认 1000 kN
        min_gap_m: 最小安全车钩间距（米），用于间距防护
        enable_etcs: 是否启用 ETCS 目标距离超速防护（默认 False 向后兼容）。
            启用后仍需提供 etcs_targets 和 etcs_curve 在 obs_state。
    """

    def __init__(
        self,
        num_vehicles: int,
        max_speed_mps: float = 30.0,
        coupler_force_limit_n: float = DEFAULT_COUPLER_FORCE_LIMIT_N,
        min_gap_m: float = 0.1,
        coupler_force_limit_emergency_n: float = None,
        coupler_override: str = 'release',
        enable_etcs: bool = False,
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
        self.enable_etcs = bool(enable_etcs)
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

    def _etcs_check(
        self, head_position_m: float, v_head: float,
        etcs_curve: EtcsBrakingCurve, etcs_targets: list[EbdTarget],
    ) -> tuple[float | None, float | None]:
        """对所有前方目标求最严格的 EBI / SBI 限速（返回 (allowed_ebi, allowed_sbi)）。

        车头位置+车速一次单点计算（ETCS 实时单点，非整条曲线预生成）。
        - allowed_ebi：EBI（紧急制动介入）限速，忍耐极限，超了必须紧急制动。
        - allowed_sbi：SBI（服务制动介入）限速，超了必须 service 制动（提前一个反应 lead）。
        所有目标都已在身后 → 返回 (None, None)（前方无约束，自由运行）。
        """
        ebi = float('inf')
        sbi = float('inf')
        worst = None
        # 【性能优化 2026-09-02】原实现对每个目标调 supervision_levels（内部 5×60 次二分
        # ×4000 步积分，单步 383ms，30km 评估 ETCS 占 ~11h）。改用单趟制动距离表
        # supervise_targets（只算安全层需要的 EBI/SBI 两级），速度提升 ~两个数量级，
        # 语义与 supervision_levels 一致（EBI 无反应提前量、EBI>=SBI）。
        fast = etcs_curve.supervise_targets(list(etcs_targets), v_head, head_position_m)
        if fast['EBI'] is not None:
            return float(fast['EBI']), float(fast['SBI'])
        return None, None

    def protect(self, actions: np.ndarray, obs_state: dict) -> np.ndarray:
        """
        对智能体输出的动作做安全修正。

        升级：若 `enable_etcs=True` 且 obs_state 提供 etcs_curve + etcs_targets + head_position，
        则启用 ETCS 前瞻式监督：

        - EBI 介入前限速：当前速度 > P 限速 → 强制 service 制动
        - EBI 触发：当前速度 > EBI 限速 → 强制紧急制动

        ETCS 仅车头（第一个目标点）计算，每一步单点，符合 ETCS 实时单点规范。

        Args:
            actions: 原始动作（长度 = 车辆数），>0 牵引，<0 制动
            obs_state: 当前动力学状态快照，需包含：
                - 'vel': 每节车速度（m/s）
                - 'coupler_forces': 每节车受到的|车钩力|（N）
                - 'gaps': 相邻车钩间距（m），gaps[i] = pos[i-1]-pos[i]
                - (ETCS 需要)'head_position_m': 车头当前位置（里程，m）
                - (ETCS 需要)'etcs_targets': 前方目标点列表 [EbdTarget(...), ...]
                - (ETCS 需要)'etcs_curve': EtcsBrakingCurve 实例

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

        # 规则 0：ETCS 目标距离超速防护（前瞻真 ATP，若配置）
        # 只对车头（头车）计算，ETCS 限速是全局硬限位（整列车不能超）。
        # EBI 触发 → 全列车强制紧急制动；P 触发 → 全列车强制 service 制动。
        etcs_applied = False
        if self.enable_etcs:
            etcs_curve = obs_state.get('etcs_curve', None)
            etcs_targets = obs_state.get('etcs_targets', None)
            head_pos = obs_state.get('head_position_m', None)
            if etcs_curve is not None and etcs_targets is not None and head_pos is not None:
                etcs_applied = True
                v_head = float(vel[0])
                ebi, sbi = self._etcs_check(head_pos, v_head, etcs_curve, etcs_targets)
                if ebi is not None:
                    if v_head > (ebi + 1e-6):
                        self._log(0, 'etcs_ebi',
                                  f'v={v_head:.2f} > EBI={ebi:.2f} -> emergency brake')
                        actions[:] = np.minimum(actions, EMERGENCY_BRAKE)
                    elif v_head > (sbi + 1e-6):
                        self._log(0, 'etcs_permitted',
                                  f'v={v_head:.2f} > SBI={sbi:.2f} -> service brake')
                        actions[:] = np.minimum(actions, FULL_SERVICE_BRAKE)

        # 规则 1：简单反应式限速防护（**始终启用**，作为 ETCS 的线速兜底，保证超速不漏检）
        # 【2026-09-02 集成修复】原 `if not etcs_applied` 只在 ETCS 未生效时启用反应式限速；
        # 但 ETCS 只监督给定的前方目标点（距目标越近越严格），对"距目标很远时的线路限速"
        # 不生效——若前列很远，后列 ETCS 允许速度很高，会漏掉 80km/h 线速上限。故改为
        # 反应式限速恒在：既挡线速超限，又不与 ETCS 冲突（ETCS 更严格时先钳制）。
        # 【bug修复 2026-08-21】速度>=限速时必须强制制动（保留对抗下坡的制动力）。
        # 原实现把>=0的动作钳为0（缓解），在长大下坡上缓解无法对抗重力→列车持续
        # 加速超速（实测-11.3‰坡上飙到117km/h）。实测 MIN 制动(-0.3)仍不足以对抗
        # -11.3‰坡（平衡速度>80），故用 full service 制动力 -0.75（接近 ATP 常用制动）。
        if True:
            for i in range(self.num_vehicles):
                if vel[i] >= self.max_speed_mps - 1e-6:
                    self._log(i, 'overspeed', f'v={vel[i]:.2f}')
                    actions[i] = min(actions[i], FULL_SERVICE_BRAKE)

        # 规则 2：车钩力上限防护（区分正常运行/紧急制动上限，Fu2019）
        # 车钩力超限干预策略（coupler_override，8/18 修正）：
        # - 'min_brake'：降低制动到 MIN 档（保留制动，避免长大下坡"释放→再制动"死锁，
        #   用于第2层多列协同；E3 修复，实测消除车钩力超限暴涨 625次→0）
        # - 'release'（默认）：制动完全钳制为 0（释放），用于第1层单列循环制动
        #   （E3 改动曾让第1层掉速到0：车钩力超限→仍保持MIN制动→持续减速→掉速，
        #   8/18 恢复第1层为 release，保持速度保持能力）
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
