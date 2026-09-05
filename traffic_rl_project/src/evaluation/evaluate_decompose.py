"""
decompose 换架构（ADR-009.1 逐机车电空分工）正式对比评估。

对比三方（同剖面/同时域/同 ETCS，确定性策略）：
  - decompose-M1：训练后逐机车 MAPPO 调制策略（--checkpoint）
  - decompose-M0：规则基线（RL 调制恒 0，MultiLocoController：ED 优先+错峰+AB 兜底）
  - 单机单控    ：旧架构 1+0（TrainFleetEnv hierarchical=True, coor_adj=0，
                  单机车 ED/AB 由 train_env 内部拆分）——P3.5 完成判据的"vs 单机+单控"

指标：reward / 车钩力峰值 / 超限 / ATP 安全事件 / AB 源·步 / meanED / 速度带保持率 / 末速。
输出：控制台表格 + JSON（outputs/results_decompose/eval_decompose.json）。

用法：
  python src/evaluation/evaluate_decompose.py --mode all --checkpoint <pt> --n_seed 3
  python src/evaluation/evaluate_decompose.py --mode decompose --random_init_speed
"""
import os
import sys
import json
import argparse

sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

import numpy as np
import torch

from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent

DEFAULT_CKPT = 'outputs/checkpoints_dec_full/mappo_fleet_best_dec_ad2_cp_seed0.pt'
RESULTS_DIR = 'outputs/results_decompose'


def make_env(mode, args):
    """mode: 'decompose'（1+1 双机车，decompose 模式）| 'single'（1+0 旧架构单机单控）。"""
    cfg = {
        'num_trains': 1,
        'consist_preset': '10kt_1plus1' if mode == 'decompose' else '10kt_1plus0',
        'grade_profile': args.grade,
        'target_speed': 20.0,
        'max_steps': args.max_steps,
        'enable_etcs': True,
        'eval_mode': True,
    }
    if mode == 'decompose':
        cfg['decompose'] = 'loco_ed_ab'
        if args.mask_lever and args.mask_lever != 'none':
            cfg['mask_lever'] = args.mask_lever   # 杠杆隔离消融：须与训练一致
        if args.hetero:
            cfg['hetero'] = True
            cfg['hetero_seed'] = args.hetero_seed  # E4-H held-out：另一组 seed=训练未见
    else:
        cfg['hierarchical'] = True
        cfg['adj_coef'] = 0.3
    return TrainFleetEnv(cfg)


def rollout(env, act_fn, args, rng, act_interval=1):
    if args.random_init_speed:
        init = float(rng.uniform(55.0, 75.0)) / 3.6
    else:
        init = args.init_speed_kmh / 3.6
    obs, _ = env.reset(options={'speed': init})
    ep_r = peak = ab_steps = ed_sum = band = viol = safety = 0.0
    n = 0
    decompose = bool(env.decompose)
    actions = None
    for i in range(args.max_steps):
        if actions is None or i % act_interval == 0:
            actions = act_fn(env)   # RL 决策间隔（semi-MDP 动作保持），rule 基线逐步执行
        obs, r, term, trunc, info = env.step(actions)
        ep_r += r
        peak = max(peak, info['coupler_force_peak'])
        viol += info['coupler_limit_violations']
        safety += info.get('safety_events', 0)
        if decompose:
            ab_steps += int(info['ab_source_count'] > 0)
            ed_sum += float(np.mean(info['executed_actions'][:, 0]))
        else:
            # 旧架构：负 throttle=制动，粗略计"空气制动参与步"（AB/ED 拆分在动力学内部）
            ab_steps += int(float(np.ravel(info['executed_actions'])[0]) < -0.3)
        vel = float(env.trains[0].dynamics.vel[0])
        band += int(env.v_min <= vel <= env.v_max)
        n += 1
        if term or trunc:
            break
    final_v = float(env.trains[0].dynamics.vel[0])
    return {
        'reward': ep_r,
        'peak_coupler_kN': peak / 1e3,
        'viol': int(viol),
        'safety_events': int(safety),
        'ab_steps': int(ab_steps),
        'mean_ed': ed_sum / max(n, 1),
        'band_rate': band / max(n, 1),
        'final_speed_kmh': final_v * 3.6,
    }


def eval_method(name, mode, act_fn, args, act_interval=1):
    rng = np.random.default_rng(args.eval_seed)
    env = make_env(mode, args)
    rs = [rollout(env, act_fn, args, rng, act_interval=act_interval) for _ in range(args.n_seed)]
    env.close()
    agg = {k: float(np.mean([r[k] for r in rs])) for k in rs[0]}
    agg['per_seed'] = [{k: float(v) for k, v in r.items()} for r in rs]
    print(f"{name}: reward {agg['reward']:+.0f} | peakCoupler {agg['peak_coupler_kN']:.0f}kN | "
          f"viol {agg['viol']:.0f} | ATP事件 {agg['safety_events']:.0f} | "
          f"AB步 {agg['ab_steps']:.0f} | meanED {agg['mean_ed']:.3f} | "
          f"band率 {agg['band_rate']:.2%} | 末速 {agg['final_speed_kmh']:.1f}km/h")
    return agg


def main():
    p = argparse.ArgumentParser(description='decompose 换架构对比评估')
    p.add_argument('--mode', choices=['all', 'decompose_m1', 'decompose_m0', 'single'], default='all')
    p.add_argument('--checkpoint', default=DEFAULT_CKPT)
    p.add_argument('--grade', default='shuozhou_23800')
    p.add_argument('--max_steps', type=int, default=15000, help='评估时域（15000=完整 23.8km）')
    p.add_argument('--n_seed', type=int, default=3)
    p.add_argument('--eval_seed', type=int, default=0)
    p.add_argument('--init_speed_kmh', type=float, default=80.0)
    p.add_argument('--random_init_speed', action='store_true',
                   help='每回合随机初始速度 [55,75]km/h（鲁棒性协议）')
    p.add_argument('--decision_interval', type=int, default=1,
                   help='RL 决策间隔 N（动作保持，须与训练一致）')
    p.add_argument('--mask_lever', type=str, default='none', choices=['none', 'ed', 'ab'],
                   help='【杠杆隔离消融】ed=禁用 ed_mod(仅AB杠杆)；ab=禁用 ab_mod(仅ED杠杆)。须与训练一致。')
    p.add_argument('--hetero', action='store_true',
                   help='【E4-H】评估在逐车钩异构参数分布上（held-out 用另一组 hetero_seed）')
    p.add_argument('--hetero_seed', type=int, default=0,
                   help='车钩异构抽样 seed（训练固定；held-out 用另一组，如 1000）')
    args = p.parse_args()

    torch.manual_seed(args.eval_seed)
    np.random.seed(args.eval_seed)
    results = {}

    if args.mode in ('all', 'decompose_m0'):
        results['decompose_M0_rule'] = eval_method(
            'decompose-M0 规则基线', 'decompose',
            lambda env: np.zeros((env.num_agents, 2)), args)

    if args.mode in ('all', 'decompose_m1'):
        env0 = make_env('decompose', args)
        agent = MAPPOAgent(num_drones=env0.num_agents, obs_per_drone=env0.obs_dim,
                           act_per_drone=env0.act_dim, device='cpu')
        agent.load(args.checkpoint)
        env0.close()

        def policy_act(env):
            flat = env._get_obs_decomposed().flatten()
            a, _ = agent.select_actions(flat, deterministic=True)
            return a.reshape(env.num_agents, 2)

        results['decompose_M1_rl'] = eval_method(
            f'decompose-M1 RL({os.path.basename(args.checkpoint)}, interval={args.decision_interval})',
            'decompose', policy_act, args, act_interval=args.decision_interval)

    if args.mode in ('all', 'single'):
        results['single_loco_rule'] = eval_method(
            '单机单控(旧架构1+0, coor=0)', 'single',
            lambda env: np.zeros(env.num_trains), args)

    if len(results) >= 2 and 'decompose_M1_rl' in results:
        m1, m0 = results['decompose_M1_rl'], results.get('decompose_M0_rule')
        base = m0 if m0 is not None else results.get('single_loco_rule')
        if base:
            print('-' * 78)
            print(f"Δ vs {('decompose-M0' if m0 else '单机单控')}: "
                  f"Δreward {m1['reward']-base['reward']:+.0f} | "
                  f"ΔpeakCoupler {m1['peak_coupler_kN']-base['peak_coupler_kN']:+.0f}kN | "
                  f"ΔATP事件 {m1['safety_events']-base['safety_events']:+.0f}")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, f"eval_decompose_{args.mode}_ms{args.max_steps}"
                                    f"{'_rand' if args.random_init_speed else ''}.json")
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'args': vars(args), 'results': results}, f, ensure_ascii=False, indent=2)
    print(f"已保存: {out}")


if __name__ == '__main__':
    main()
