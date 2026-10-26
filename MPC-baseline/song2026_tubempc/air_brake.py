# -*- coding: utf-8 -*-
"""
空气制动模型
- 制动缸压强建立/缓解：文献[22] 式(3-9)(3-10)（与论文式1/2 同源，但含
  "1-(·)^λ2" 的缓解项与文献[22]表3-1 的 λ_P1=0.8、λ_P2=1.6、tmax1=50 s、
  tmax2=25 s）
- 波传播延迟：式(3-11)(3-12)（论文式3/4），va=220 m/s、vr=180 m/s
- 闸瓦压力/摩擦系数：式(3-7)(3-8)(3-13)（论文式5/6/7），参数取论文表2
"""
import numpy as np
from params import (BRAKE_LOCO, BRAKE_WAGON, NSH_LOCO, NSH_WAGON,
                    TMAX1, TMAX2_LOCO, TMAX2_WAGON, LAMBDA1, LAMBDA2,
                    VA, VR, friction_coef, shoe_pressure)


class AirBrake:
    """单个质量点的空气制动。
    状态：制动缸压强 P (kPa)；阶段：apply（充气）/ release（排气）。
    命令：b in [0,1] -> 目标压强 b*Pmax（b=1 即论文式(1) 的满压）。
    """
    def __init__(self, is_loco, d_hafe):
        self.is_loco = is_loco
        self.br = BRAKE_LOCO if is_loco else BRAKE_WAGON
        self.nsh = NSH_LOCO if is_loco else NSH_WAGON
        self.d_hafe = d_hafe                      # m，与最近机车制动阀的列车管距离
        self.P = 0.0                              # 当前制动缸压强 kPa
        self.t_delay1 = d_hafe / VA               # 式(3-11) 制动波
        self.t_delay2 = d_hafe / VR               # 式(3-12) 缓解波
        self.tmax1 = TMAX1
        self.tmax2 = TMAX2_LOCO if is_loco else TMAX2_WAGON
        self.mode = "release"                     # 初始：已缓解
        self.t_switch = -1e9                      # 本阶段指令生效（到达）时刻
        self.P0 = 0.0                             # 本阶段起点压强
        self.target = 0.0                         # 本阶段目标压强 kPa
        self.b_cmd = 0.0

    def command(self, b, t_now):
        """接收二进制/比例指令；指令变化时按方向选择波速延迟并重置斜坡起点。"""
        b = float(np.clip(b, 0.0, 1.0))
        if abs(b - self.b_cmd) < 1e-9:
            return
        self.b_cmd = b
        target = b * self.br["Pmax"]
        if abs(target - self.target) < 1e-9:
            return
        delay = self.t_delay1 if target > self.P else self.t_delay2
        self.t_switch = t_now + delay
        self.P0 = self.P
        self.target = target
        self.mode = "apply" if target > self.P else "release"

    def step(self, t_now, dt):
        """按文献[22] 式(3-9)(3-10) 更新制动缸压强。
        施加：P = P0 + (P_tgt - P0)·min(1,(τ/tmax1)^λ1)
        缓解：P = P0·[1 - min(1,(τ/tmax2)^λ2)]
        其中 τ = t - t_wave（指令经列车管传播到达本车之后的时间）。
        """
        tau = t_now - self.t_switch
        if tau <= 0.0:
            return self.P
        if self.mode == "apply":
            sh = min(1.0, (tau / self.tmax1) ** LAMBDA1)
            self.P = self.P0 + (self.target - self.P0) * sh
        else:
            sh = min(1.0, (tau / self.tmax2) ** LAMBDA2)
            self.P = self.P0 * (1.0 - sh)
        return self.P

    def brake_force(self, v):
        """式(3-7)(3-8)(3-13)：单质点空气制动力 (kN)。
        货车组质量点：乘以组内等效车辆数。"""
        P_sh = shoe_pressure(self.P, self.br, self.nsh)
        if P_sh <= 0:
            return 0.0
        phi = friction_coef(P_sh, max(v, 0.0))
        return self.nsh * P_sh * phi
