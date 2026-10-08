"""跑 decompose 评估并把**逐步时程**（速度 / 车钩力 / 列距）落盘，供画曲线复用。

背景：`src/evaluation/evaluate_decompose.py` 只落 JSON 指标、**不存时程轨迹**
⇒ 画速度带 / 车钩力 / 列距曲线必须重跑一次评估。

约束：长训期间禁止改 `src/**`（铁律）。故本脚本**不改 src**，改为在运行时包装
`TrainFleetEnv.step` 记录时程；物理与控制逻辑完全走原实现，不复制、不近似。

落盘（时间戳归档，不覆盖）：`outputs/results_decompose/traj_<tag>_<时间戳>/`
  - `traj_<tag>.npz`   原始时程数组
  - `traj_<tag>.csv`   同一数据的可读表
  - `metrics.json`     本次指标 + 内嵌 metadata（git_commit / 物理口径 / seed）

用法（WSL，traffic_rl 环境）：
    python scripts/dump_eval_traj.py --mode decompose_m0 --out_tag m0_rule_53km
    python scripts/dump_eval_traj.py --mode decompose_m1 --out_tag m1_rl_53km \
        --checkpoint outputs/checkpoints_formation/adr024_1400ep_seed0/mappo_fleet_last_ep80_dec_ad2_cp_seed0.pt
"""
import argparse
import json
import os
import sys
import types
from datetime import datetime
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from src.environments.train_fleet_env import TrainFleetEnv
import src.evaluation.evaluate_decompose as ed


REC = {
    't_s': [], 'speed_kmh': [], 'coupler_peak_kN': [],
    'gap_err_mean_m': [], 'gap_min_m': [], 'ab_count': [], 'ed_cmd': [],
}


def _install_recorder():
    orig_step = TrainFleetEnv.step

    def rec_step(self, actions):
        out = orig_step(self, actions)
        info = out[4]
        REC['t_s'].append(len(REC['t_s']) * float(getattr(self, 'dt', 0.1)))
        REC['speed_kmh'].append([float(tr.dynamics.vel[0]) * 3.6 for tr in self.trains])
        REC['coupler_peak_kN'].append([
            float(np.max(tr.dynamics.coupler_interface_forces_per_vehicle())) / 1e3
            for tr in self.trains])
        REC['gap_err_mean_m'].append(float(info.get('gap_err_mean', np.nan)))
        REC['gap_min_m'].append(float(info.get('gap_min_m', np.nan)))
        REC['ab_count'].append(int(info.get('ab_source_count', 0)))
        ea = info.get('executed_actions')
        REC['ed_cmd'].append(float(np.mean(np.asarray(ea)[:, 0])) if ea is not None else np.nan)
        return out

    TrainFleetEnv.step = rec_step


def _build_args(a):
    """构造 evaluate_decompose.make_env / rollout 需要的参数命名空间（同 CLI 默认口径）。"""
    return types.SimpleNamespace(
        num_trains=a.num_trains, grade=a.grade, max_steps=a.max_steps,
        mask_lever='none', hetero=False, hetero_seed=0,
        n_seed=a.n_seed, eval_seed=a.eval_seed,
        init_speed_kmh=a.init_speed_kmh, random_init_speed=False,
        enable_mpc=(a.mode == 'mpc'), mpc_type='nmpc', mpc_gap_min=20.0,
        mpc_inner_rule_cyclic=bool(getattr(a, 'mpc_inner_rule_cyclic', False)),
        decision_interval=a.decision_interval, checkpoint=a.checkpoint,
    )


def _make_act_fn(mode, args, ns):
    if mode == 'decompose_m0':
        return (lambda env: np.zeros((env.num_agents, 2))), 1, 'D-Rule(规则基线)'
    if mode == 'mpc':
        return ed.mpc_act, 1, 'MPC(NMPC 集中质量多体+MT-2+IPOPT)'
    import torch
    from src.algorithms.mappo_agent import MAPPOAgent
    env0 = ed.make_env('decompose', ns)
    critic = ed.probe_critic_mode(args.checkpoint)
    agent = MAPPOAgent(num_drones=env0.num_agents, obs_per_drone=env0.obs_dim,
                       act_per_drone=env0.act_dim, device='cpu', critic=critic,
                       decision_interval=args.decision_interval,
                       physics_dt=float(getattr(env0, 'dt', 0.1)))
    agent.load(args.checkpoint)
    env0.close()

    def policy_act(env):
        flat = env._get_obs_decomposed().flatten()
        act, _ = agent.select_actions(flat, deterministic=True)
        return act.reshape(env.num_agents, 2)

    return policy_act, args.decision_interval, f'D-RL({os.path.basename(args.checkpoint)})'


def _save(tag, metrics, args, outdir):
    outdir.mkdir(parents=True, exist_ok=True)
    t = np.asarray(REC['t_s'], dtype=float)
    speed = np.asarray(REC['speed_kmh'], dtype=float)          # (T, n_train)
    cpl = np.asarray(REC['coupler_peak_kN'], dtype=float)      # (T, n_train)
    np.savez_compressed(
        outdir / f'traj_{tag}.npz',
        t_s=t, speed_kmh=speed, coupler_peak_kN=cpl,
        gap_err_mean_m=np.asarray(REC['gap_err_mean_m'], dtype=float),
        gap_min_m=np.asarray(REC['gap_min_m'], dtype=float),
        ab_count=np.asarray(REC['ab_count'], dtype=int),
        ed_cmd=np.asarray(REC['ed_cmd'], dtype=float),
    )
    cols = {'t_s': t, 'gap_err_mean_m': REC['gap_err_mean_m'],
            'gap_min_m': REC['gap_min_m'], 'ab_count': REC['ab_count'],
            'ed_cmd': REC['ed_cmd']}
    for i in range(speed.shape[1]):
        cols[f'speed_train{i + 1}_kmh'] = speed[:, i]
    for i in range(cpl.shape[1]):
        cols[f'coupler_train{i + 1}_kN'] = cpl[:, i]
    import pandas as pd
    pd.DataFrame(cols).to_csv(outdir / f'traj_{tag}.csv', index=False)

    meta = ed.build_metadata(
        project_root=str(ROOT), case='official',
        world_cfg=ed.official_world_config(
            ed.PhysicsConfig(), env_cfg={'consist_preset': '10kt_1plus1'}),
        seed=args.eval_seed, entry=__file__, extra={'eval_args': vars(args)})
    (outdir / 'metrics.json').write_text(
        json.dumps({'metadata': meta, 'metrics': metrics}, ensure_ascii=False, indent=2),
        encoding='utf-8')
    return outdir


def main():
    p = argparse.ArgumentParser(description='跑评估并落逐步时程（不改 src，长训期可用）')
    p.add_argument('--mode', choices=['decompose_m0', 'decompose_m1', 'mpc'], default='decompose_m0')
    p.add_argument('--checkpoint', default=ed.DEFAULT_CKPT)
    p.add_argument('--mpc_inner_rule_cyclic', action='store_true', default=False,
                   help='MPC 是否再叠一层规则循环护盾（默认 False = 与 D-RL 各一层，like-for-like）')
    p.add_argument('--grade', default='shuozhou_real_53km')
    p.add_argument('--max_steps', type=int, default=36000)
    p.add_argument('--num_trains', type=int, default=3)
    p.add_argument('--n_seed', type=int, default=1)
    p.add_argument('--eval_seed', type=int, default=0)
    p.add_argument('--init_speed_kmh', type=float, default=80.0)
    p.add_argument('--decision_interval', type=int, default=10)
    p.add_argument('--out_tag', required=True, help='归档语义前缀，如 m0_rule_53km')
    args = p.parse_args()

    ns = _build_args(args)
    act_fn, act_interval, label = _make_act_fn(args.mode, args, ns)

    _install_recorder()
    import torch
    torch.manual_seed(args.eval_seed)
    np.random.seed(args.eval_seed)
    metrics = ed.eval_method(label, 'decompose', act_fn, ns, act_interval=act_interval)

    stamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    outdir = ROOT / 'outputs' / 'results_decompose' / f'traj_{args.out_tag}_{stamp}'
    _save(args.out_tag, metrics, args, outdir)
    print(f'已归档时程: {outdir}（T={len(REC["t_s"])} 步）')


if __name__ == '__main__':
    main()
