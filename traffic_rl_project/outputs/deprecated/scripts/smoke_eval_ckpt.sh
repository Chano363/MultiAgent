#!/usr/bin/env bash
# 确认最新 checkpoint 与评估维度（快速冒烟：建 env 打印 num_agents/obs_dim/act_dim + 加载 ckpt）
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python - <<'PY'
import os
from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent

ckpt = 'outputs/checkpoints_formation/final_seed0/mappo_fleet_last_ep1623_dec_ad2_cp_seed0_seed0.pt'
print('ckpt exists:', os.path.exists(ckpt), os.path.getsize(ckpt) if os.path.exists(ckpt) else '')

cfg = {
    'num_trains': 3, 'consist_preset': '10kt_1plus1',
    'grade_profile': 'shuozhou_real_53km', 'target_speed': 20.0,
    'max_steps': 36000, 'eval_mode': True, 'decompose': 'loco_ed_ab',
}
env = TrainFleetEnv(cfg)
print('num_agents:', env.num_agents, 'obs_dim:', env.obs_dim, 'act_dim:', env.act_dim)
a = MAPPOAgent(num_drones=env.num_agents, obs_per_drone=env.obs_dim,
               act_per_drone=env.act_dim, device='cpu')
a.load(ckpt)
print('ckpt loaded OK')
# 验证 select_actions 输出 shape
obs = env._get_obs_decomposed().flatten()
act, _ = a.select_actions(obs, deterministic=True)
print('select_actions shape:', act.shape, '-> expected (6,2)=', (env.num_agents, 2))
env.close()
print('SMOKE OK')
PY