# -*- coding: utf-8 -*-
"""临时分析：downhill 轨迹"""
import numpy as np
from scenarios import target_speed, gradient_permille

d = np.genfromtxt("outputs/sim_downhill_coupler_on.csv", delimiter=",",
                  names=True)
t = d["t"]
vr = np.array([target_speed(x, "downhill") for x in t])
grad0 = np.array([gradient_permille(d["s00"][k], "downhill")
                  for k in range(len(t))])
k0 = 0
step = max(1, len(t) // 40)
print("  t    v_ref  v1     v2     v3    grad%%  bP_w1_1 fc00   fc10  "
      "intra1 inter21 inter32")
for k in range(0, len(t), step):
    print(f"{t[k]:5.0f} {vr[k]:6.2f} {d['v00'][k]:6.2f} {d['v10'][k]:6.2f} "
          f"{d['v20'][k]:6.2f} {grad0[k]:6.1f} {d['P11'][k]:6.1f} "
          f"{d['fc00'][k]:7.1f} {d['fc10'][k]:7.1f} "
          f"{d['s00'][k]-d['s01'][k]-250:7.2f} "
          f"{d['s00'][k]-d['s10'][k]-2000:7.1f} "
          f"{d['s10'][k]-d['s20'][k]-2000:7.1f}")
for i, key in enumerate(["v00", "v10", "v20"]):
    v = d[key]
    print(f"train{i+1} v range [{v.min():.2f},{v.max():.2f}] "
          f"at t=[{t[v.argmin()]:.0f},{t[v.argmax()]:.0f}]")
