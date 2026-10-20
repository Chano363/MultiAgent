def _advance_control_once(
    self,
    throttle: np.ndarray,
    ed_throttle: np.ndarray,
    ab_command: AirBrakeNotch,
    brake_origin: int,
    ab_sources: list,
    eot: bool,
    h: float,
    apply_command: bool,
    reduction_kpa: float = None,
):
    """推进一个物理子步（步长 h，≤0.01s）。"""
    if apply_command:
        # 【2026-09-02 P0-3】连续减压量覆盖：每控制步更新（验证专用，None=档位默认）
        self._brake_reduction_override_kpa = reduction_kpa
        # 【2026-09-03 B3】段切换检测：上一步无制动 → 这一步有制动指令 → 段号+1。
        # 段号仅在有新制动段发出时递增（持续制动中不递增，缓解后再制动才 +1）。
        cmd_now = (ab_sources[0][1] if ab_sources
                   else (None if ab_command is None else ab_command))
        is_braking_cmd = (cmd_now is not None
                          and cmd_now != AirBrakeNotch.RELEASE)
        # None means HOLD, not RELEASE. Keep the same braking episode
        # through vetoed new-source requests or a later emergency upgrade.
        if cmd_now is not None:
            if self.enable_cyclic_degrade and is_braking_cmd and not self._brake_was_active:
                self._brake_segment += 1
            self._brake_was_active = is_braking_cmd
        if ab_sources:
            # 多源制动：多个位置同时发出空气制动指令（分布式动力）
            # 尾部/中部动力源需要双向传播以提升制动同步
            cmd = ab_sources[0][1]
            if cmd != AirBrakeNotch.RELEASE:
                for idx, notch in ab_sources:
                    if (self.mid_source_delay_s > 0.0 and idx != 0):
                        # 【AD 组】非队首源延时发波：入待发队列（仅首子步处理），
                        # 头源(idx=0)仍立即 → 错开双源波在中机车后方对撞。
                        # 已在队列 / 已激活未缓解 → 不重复入队（否则发波后
                        # 每个控制步都会重新入队，队列永不为空）。
                        already = any(qi == idx for _r, qi, _n in self._ab_delay_queue)
                        fired = (self._air_brake_active[idx]
                                 and not self._air_brake_releasing[idx])
                        if not already and not fired:
                            self._ab_delay_queue.append(
                                [float(self.mid_source_delay_s), idx, notch])
                    else:
                        self._apply_air_brake_command(
                            notch, idx, bidirectional=True)
            else:
                if np.any(self._air_brake_active):
                    self._reset_air_brake_command(0, eot=eot)
                self._ab_delay_queue = []   # 【AD】缓解清空待发中源
        elif ab_command is None:
            # 【2026-09-02 bug修复】ab_command=None 表示"不使用空气制动"，
            # 不得触发任何制动/缓解逻辑。此前 None != RELEASE 为真 → 头车被
            # 错误 _apply_air_brake_command(None) → _air_brake_active[0]=True，
            # 导致平坡静止列车蠕动、惰行能量不守恒（第一锚物理硬约束测试发现）。
            pass
        elif ab_command != AirBrakeNotch.RELEASE:
            # 单源制动（向后兼容）
            self._apply_air_brake_command(ab_command, brake_origin)
        else:
            # 缓解：仅在确实处于制动状态时释放
            # 【bug修复】缓解波传播中（车头 _air_brake_releasing[0] 已触发）不重复
            # _reset_air_brake_command，否则每次 step 都重置缓解波 delay → 缓解波
            # 永远传播不完 → 尾部持续制动 → 掉速 + active 反而增加（8/18 诊断：
            # 缓解后 active 4→14、delay 恒定6.0）。首次缓解才触发缓解波。
            if (np.any(self._air_brake_active)
                    and not self._air_brake_releasing[brake_origin]):
                self._reset_air_brake_command(brake_origin, eot=eot)

    # 【AD 组】延时中源倒计时：**每个物理子步**减 h（每控制步累计 dt = 真实时钟；
    # 若只在首子步减 h 会慢 n_sub=10 倍）。归零即发波；缓解（abort）时清空。
    if self._ab_delay_queue:
        still = []
        for rem, qi, qn in self._ab_delay_queue:
            rem -= h
            if rem <= 0.0:
                self._apply_air_brake_command(qn, qi, bidirectional=True)
            else:
                still.append([rem, qi, qn])
        self._ab_delay_queue = still

    # 推进空气制动波速传播
    self._advance_air_brake_propagation(h)

    # 【2026-08-30 缺失物理补全】制动缸升压：波到达后压力渐入
    # （真实制动缸充风升压，阶跃施加会产生远超真实的纵向冲击）。
    # 升压时间按档位区分（常用 ~18-20s 发散式，紧急 ~10s，李蔚2023）。
    # Pressure integrated by advance_fractional_air.
    # 【2026-08-30 标准 LTD 重构】Newmark-β 隐式积分（替代半隐式 Euler）
    # 控制力 = 牵引 + 电制动 + 空气制动（不依赖位置/速度，迭代外固定）
    control_forces = (
        self._tractive_forces_per_vehicle(throttle)
        + self._electric_braking_forces(ed_throttle)
        + self._air_braking_forces()
    )
    self._step_newmark(control_forces, h)
    self._update_grade_from_profile()
