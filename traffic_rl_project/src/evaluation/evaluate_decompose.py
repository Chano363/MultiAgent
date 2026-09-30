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


import numpy as np
import torch

from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent
from src.physics_governance import official_entry_guard, official_world_config
from src.physics_config import PhysicsConfig
from src.metadata import build_metadata
from src.controllers.fair_mpc_controller import FairMPCController
from src.controllers.mpc_controller import MPCController
from src.controllers.nmpc_controller import NMPCController
from src.train_dynamics.params import CouplerParams

DEFAULT_CKPT = 'outputs/checkpoints_formation/seed0/mappo_fleet_best_dec_ad2_cp_seed0.pt'
RESULTS_DIR = 'outputs/results_decompose'


def make_env(mode, args):
    """mode: 'decompose'（多列机车级 ED/AB，decompose 模式）| 'single'（1+0 旧架构单机单控）。"""
    num_trains = getattr(args, 'num_trains', 3)
    # 主训练场景：3列×1+1=6 机车智能体（10kt_1plus1），53km，全程 36000 步
    cfg = {
        'num_trains': 1 if mode == 'single' else num_trains,
        'consist_preset': '10kt_1plus1' if mode == 'decompose' else '10kt_1plus0',
        'grade_profile': args.grade,
        'target_speed': 20.0,
        'max_steps': args.max_steps,
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
    env = TrainFleetEnv(cfg)
    if mode == 'decompose' and getattr(args, 'enable_mpc', False):
        _mount_mpc(env, args)
    return env


def _mount_mpc(env, args):
    """把 MPC 控制器挂到 env 上（供 mpc_act 读取），复用 compute_actions_from_env 接口。

    --mpc_type：fair=FairMPCController（单质点聚合 + SLSQP，历史基线）；
                nmpc=多体 NMPC（casadi+IPOPT，lumped 4 块 + MT-2 车钩约束，成熟基线，
                与 D-RL 同档对冲：规则循环制动内层 + NMPC 调制）。
    """
    if getattr(args, 'mpc_simple', False):
        env._mpc_controller = MPCController(
            num_trains=env.num_trains, dt=0.1, horizon=20,
            target_gap=env._dynamic_gap(), headway_s=5.0,
            target_speed=env.target_speed, lambda_gap=2.0,
            lambda_v=0.2, lambda_u=0.05,
        )
    elif getattr(args, 'mpc_type', 'fair') == 'nmpc':
        # 成熟多体 NMPC：预测模型与评估物理同源（标准 MT-2 CouplerParams），
        # 规则循环制动内层 + NMPC 调制（与 D-RL 同构，唯一差异=决策来源 NMPC vs MAPPO）。
        env._mpc_controller = NMPCController(
            num_trains=env.num_trains, dt=0.1,
            v_max=env.v_max, v_min=env.v_min,
            target_speed=env.target_speed,
            headway_s=getattr(env, 'headway_s', 5.0),
            gap_min=getattr(args, 'mpc_gap_min', 20.0),
            coupler_params=CouplerParams(),
            inner_rule_cyclic=True,
            ipopt_max_iter=300,
        )
        # grade_at 前瞻由 compute_actions_from_env 从 env.grade_profile 自动重建（Regime A）
    else:
        env._mpc_controller = FairMPCController(
            num_trains=env.num_trains, dt=0.1, v_max=env.v_max, v_min=env.v_min,
            target_speed=env.target_speed, headway_s=env.headway_s if hasattr(env, 'headway_s') else 5.0,
            gap_min=getattr(args, 'mpc_gap_min', 20.0),
            enforce_coupler=getattr(args, 'mpc_enforce_coupler', True),
            inner_rule_cyclic=False,
        )
        # 坡度先验由 compute_actions_from_env 从 env.grade_profile 自动重建（grade_at=None）
    env._mpc_controller.reset()


def rollout(env, act_fn, args, rng, act_interval=1):
    if args.random_init_speed:
        init = float(rng.uniform(55.0, 75.0)) / 3.6
    else:
        init = args.init_speed_kmh / 3.6
    obs, _ = env.reset(options={'speed': init})
    ep_r = peak = ab_steps = ed_sum = band = viol = safety = 0.0
    prev_viol = prev_safety = 0.0  # env episode 级累计计数器的上一轮快照，用于取增量
    n = 0
    decompose = bool(env.decompose)
    actions = None
    # MPC 求解耗时/状态（同档对冲主指标）：快照本回合新增段，避免跨 seed 累计混淆
    _mpc = getattr(env, '_mpc_controller', None)
    st0 = len(_mpc.solve_times) if (_mpc is not None and hasattr(_mpc, 'solve_times')) else 0
    for i in range(args.max_steps):
        if actions is None or i % act_interval == 0:
            actions = act_fn(env)   # RL 决策间隔（semi-MDP 动作保持），rule 基线逐步执行
        obs, r, term, trunc, info = env.step(actions)
        ep_r += r
        peak = max(peak, info['coupler_force_peak'])
        # env 的 coupler/safety 计数器是 episode 级单调累计（reset 清零、step 间不清零），
        # 此处必须取其每步增量累加；否则 O(n²) 叠加会把 viol/safety_events 放大到 1e6~1e8（2026-09-25 修复）。
        viol += info['coupler_limit_violations'] - prev_viol
        prev_viol = info['coupler_limit_violations']
        safety += info.get('safety_events', 0) - prev_safety
        prev_safety = info.get('safety_events', 0)
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
    out = {
        'reward': ep_r,
        'peak_coupler_kN': peak / 1e3,
        'viol': int(viol),
        'safety_events': int(safety),
        'ab_steps': int(ab_steps),
        'mean_ed': ed_sum / max(n, 1),
        'band_rate': band / max(n, 1),
        'final_speed_kmh': final_v * 3.6,
    }
    if _mpc is not None and hasattr(_mpc, 'solve_times') and _mpc.solve_times[st0:]:
        st = _mpc.solve_times[st0:]
        sts = _mpc.solve_statuses[st0:]
        out['mpc_solve_mean_ms'] = float(np.mean(st) * 1e3)
        out['mpc_solve_max_ms'] = float(np.max(st) * 1e3)
        out['mpc_solve_fail'] = int(sum(1 for s in sts if s != 'optimal'))
    return out


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
          f"band率 {agg['band_rate']:.2%} | 末速 {agg['final_speed_kmh']:.1f}km/h"
          + (f" | MPC求解 {agg['mpc_solve_mean_ms']:.0f}ms均值/{agg['mpc_solve_max_ms']:.0f}ms峰值"
             f" | fail {agg['mpc_solve_fail']:.0f}" if 'mpc_solve_mean_ms' in agg else ""))
    return agg


def mpc_act(env):
    """MPC 公平接入 decompose：每列目标加速度 → 每机车 [ed_throttle, ab=0]。

    FairMPCController.compute_actions_from_env 解出每列目标加速度 U (num_trains,)，
    再对每列车 MultiLocoController.get_action_accel 转成该列机车动作 (n_loco, 2)，
    拼接为 (num_agents=6, 2)，与 decompose env.step 的动作形状直接匹配。
    """
    U = env._mpc_controller.compute_actions_from_env(env)
    acts = []
    for ti, tr in enumerate(env.trains):
        row = env.multi_loco_controllers[ti].get_action_accel(tr, float(U[ti]))
        acts.append(np.asarray(row, dtype=float))
    return np.concatenate(acts, axis=0).astype(np.float32)


def main():
    p = argparse.ArgumentParser(description='decompose 换架构对比评估')
    p.add_argument('--mode', choices=['all', 'decompose_m1', 'decompose_m0', 'mpc', 'single'],
                   default='all')
    p.add_argument('--checkpoint', default=DEFAULT_CKPT)
    p.add_argument('--grade', default='shuozhou_real_53km')
    p.add_argument('--max_steps', type=int, default=36000,
                   help='评估时域（36000=完整 53.2km；15000=23.8km）')
    p.add_argument('--num_trains', type=int, default=3,
                   help='decompose 多列群组列数（主训练=3，6 机车智能体）')
    p.add_argument('--enable_mpc', action='store_true',
                   help='在 decompose env 上挂载 MPC 控制器（供 --mode mpc 使用）')
    p.add_argument('--mpc_simple', action='store_true',
                   help='用普通简化 MPCController 而非 FairMPCController')
    p.add_argument('--mpc_type', choices=['fair', 'nmpc'], default='fair',
                   help='MPC 基线类型：fair=FairMPCController（单质点+SLSQP）；nmpc=多体 NMPC（casadi+IPOPT，成熟基线）')
    p.add_argument('--mpc_gap_min', type=float, default=20.0, help='MPC 最小列间距约束 (m)')
    p.add_argument('--mpc_enforce_coupler', action='store_true', default=True,
                   help='MPC 车钩力硬约束（默认开）')
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
    p.add_argument('--out_suffix', type=str, default='',
                   help='输出文件名后缀（区分 seed/interval/场景，防覆盖），如 "_s0_iv5"')
    args = p.parse_args()

    # 【治理】评估入口工况断言 + 元数据内嵌结果 JSON（评估一律 OFFICIAL，无调试物理）
    official_entry_guard(__file__)
    _PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
    _meta = build_metadata(project_root=_PROJECT_ROOT, case='official',
                           world_cfg=official_world_config(PhysicsConfig()),
                           seed=args.eval_seed, entry=__file__,
                           extra={'eval_args': vars(args)})

    torch.manual_seed(args.eval_seed)
    np.random.seed(args.eval_seed)
    results = {}

    if args.mode in ('all', 'decompose_m0'):
        results['decompose_M0_rule'] = eval_method(
            'decompose-M0 规则基线(RL调制恒0)', 'decompose',
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

    if args.mode in ('all', 'mpc'):
        if getattr(args, 'enable_mpc', False) or args.mode == 'mpc':
            if not getattr(args, 'enable_mpc', False):
                args.enable_mpc = True   # mpc 模式自动挂载 MPC 控制器
            mpc_label = {'fair': 'Fair', 'nmpc': 'NMPC(多体+IPOPT)'}[args.mpc_type]
            results['mpc'] = eval_method(
                f'MPC({("Simple" if args.mpc_simple else mpc_label)}) @ {args.grade}',
                'decompose', mpc_act, args)

    # 单机单控(旧架构1+0)已从主对比中移除：它与 3列1+1 群组非同环境，无对比意义。
    # 仅 --mode single 时保留，供单独回测旧架构。
    if args.mode == 'single':
        results['single_loco_rule'] = eval_method(
            '单机单控(旧架构1+0, coor=0)', 'single',
            lambda env: np.zeros(env.num_trains), args)

    if len(results) >= 3 and 'decompose_M1_rl' in results:
        m1, m0, mp = results['decompose_M1_rl'], results.get('decompose_M0_rule'), results.get('mpc')
        if m0 is not None:
            print('-' * 78)
            print(f"Δ(D-RL - D-Rule): Δreward {m1['reward']-m0['reward']:+.0f} | "
                  f"ΔpeakCoupler {m1['peak_coupler_kN']-m0['peak_coupler_kN']:+.0f}kN | "
                  f"ΔATP事件 {m1['safety_events']-m0['safety_events']:+.0f}")
        if mp is not None:
            print(f"Δ(D-RL - MPC):    Δreward {m1['reward']-mp['reward']:+.0f} | "
                  f"ΔpeakCoupler {m1['peak_coupler_kN']-mp['peak_coupler_kN']:+.0f}kN | "
                  f"ΔATP事件 {m1['safety_events']-mp['safety_events']:+.0f}")
    elif len(results) >= 2 and 'decompose_M1_rl' in results:
        m1, m0 = results['decompose_M1_rl'], results.get('decompose_M0_rule')
        if m0 is not None:
            print('-' * 78)
            print(f"Δ(D-RL - D-Rule): Δreward {m1['reward']-m0['reward']:+.0f} | "
                  f"ΔpeakCoupler {m1['peak_coupler_kN']-m0['peak_coupler_kN']:+.0f}kN | "
                  f"ΔATP事件 {m1['safety_events']-m0['safety_events']:+.0f}")

    os.makedirs(RESULTS_DIR, exist_ok=True)
    out = os.path.join(RESULTS_DIR, f"eval_decompose_{args.mode}_ms{args.max_steps}"
                                    f"{'_rand' if args.random_init_speed else ''}"
                                    f"{args.out_suffix}.json")
    with open(out, 'w', encoding='utf-8') as f:
        json.dump({'metadata': _meta, 'args': vars(args), 'results': results},
                  f, ensure_ascii=False, indent=2)
    print(f"已保存: {out}")


if __name__ == '__main__':
    main()
