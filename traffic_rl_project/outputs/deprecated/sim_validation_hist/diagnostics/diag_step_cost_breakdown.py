"""定位 env.step 耗时分布：各力函数 + 子步 + Picard 迭代。"""
import sys
import time
from pathlib import Path
sys.path.append(str(Path(__file__).parent.parent.parent))

import numpy as np
from src.environments.train_fleet_env import TrainFleetEnv

env = TrainFleetEnv({
    'num_trains': 3, 'consist_preset': '10kt_1plus0',
    'grade_profile': 'shuozhou_23800',
    'v_max': 80.0 / 3.6, 'v_min': 40.0 / 3.6,
    'target_gap': 100.0, 'headway_s': 5.0,
    'max_steps': 100, 'max_accel': 1.0,
    'use_coupler_constraint': True, 'hierarchical': False,
    'adj_coef': 0.0, 'eval_mode': True,
})
obs, _ = env.reset()
rng = np.random.default_rng(0)

# 预热
for _ in range(5):
    obs, r, term, trunc, info = env.step(rng.uniform(-0.2, 0.2, 3))

td = env.trains[0].dynamics
n = td.num_vehicles
t_nm = 0.0
t_air = 0.0
t_res = 0.0
t_grade = 0.0
t_coup = 0.0
N = 100
for i in range(N):
    obs, r, term, trunc, info = env.step(rng.uniform(-0.2, 0.2, 3))
    # 单列耗时统计（近似：主列车）
    t0 = time.perf_counter(); td._coupler_forces(); t_coup += time.perf_counter() - t0
    t0 = time.perf_counter(); td._air_braking_forces(); t_air += time.perf_counter() - t0
    t0 = time.perf_counter(); td._resistance_forces(); t_res += time.perf_counter() - t0
    t0 = time.perf_counter(); td._grade_forces(); t_grade += time.perf_counter() - t0

print(f"单列车 100 次调用耗时（每次调用都是完整的每节车计算）:")
print(f"  _coupler_forces   : {t_coup/N*1e6:8.1f} µs")
print(f"  _air_braking      : {t_air/N*1e6:8.1f} µs")
print(f"  _resistance       : {t_res/N*1e6:8.1f} µs")
print(f"  _grade_forces     : {t_grade/N*1e6:8.1f} µs")
print(f"env.step 总耗时 (3列): 测量中...")
t0 = time.perf_counter()
for i in range(N):
    obs, r, term, trunc, info = env.step(rng.uniform(-0.2, 0.2, 3))
print(f"  env.step 平均     : {(time.perf_counter()-t0)/N*1e3:6.1f} ms")
