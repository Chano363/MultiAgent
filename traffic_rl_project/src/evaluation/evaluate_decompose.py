"""
decompose 换架构（ADR-009.1 逐机车电空分工）正式对比评估。

对比三方（同剖面/同时域/同 ETCS，确定性策略）：
  - decompose-M1：训练后逐机车 MAPPO 调制策略（--checkpoint）
  - decompose-M0：规则基线（RL 调制恒 0，MultiLocoController：ED 优先+错峰+AB 兜底）
  - 单机单控    ：旧架构 1+0（TrainFleetEnv hierarchical=True, coor_adj=0，
                  单机车 ED/AB 由 train_env 内部拆分）——P3.5 完成判据的"vs 单机+单控"

指标：reward / 车钩力峰值 / 超限 / ATP 安全事件（主表安全指标 = ATP 触发次数）/ AB 源·步 /
      meanED / 速度带保持率 / 末速 / 列距误差（均值/峰值绝对误差、全程最小实际列距；
      编队底线，仅多列编组产出）。追尾（实际列距≤0）**不作指标**——评估入口 assert 守卫，
      非 0 判该行评估无效（既定决策 2026-10：主表报 ATP 触发次数，见 rollout 尾部断言）。
输出：控制台表格 + JSON（outputs/results/decompose/eval_decompose.json）。

用法：
  python src/evaluation/evaluate_decompose.py --mode all --checkpoint <pt> --n_seed 3
  python src/evaluation/evaluate_decompose.py --mode decompose_m1 --random_init_speed

⚠️ `--decision_interval`（RL 动作保持步数）**默认 None = 自 ckpt 内嵌 metadata 自动读取**
（必须与训练一致；2026-10-01 前默认写死 1，与训练的 10 不符 ⇒ 见 resolve_decision_interval）。
"""
import os
import sys
import json
import argparse
import inspect


import numpy as np
import torch

from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent
from src.physics_governance import official_entry_guard, official_world_config
from src.physics_config import PhysicsConfig
from src.metadata import build_metadata
from src.controllers.nmpc_controller import NMPCController
from src.controllers.multi_loco_controller import MultiLocoController
from src.train_dynamics.params import CouplerParams

# 【2026-10-08 日志可见性】强制 stdout/stderr 行缓冲。本脚本常以后台重定向方式运行
# （`python ... > log 2>&1 &`），此时 stdout 非 TTY，Python 默认**块缓冲**（8KB）⇒
# 整轮评估的输出只在进程退出时才落盘，中途被 kill 就"白跑一晚无日志"（历史事故）。
# 行缓冲后每条 print 立即落盘，与是否加 `-u` 无关。
try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

DEFAULT_CKPT = 'outputs/checkpoints/formation/seed0/mappo_fleet_best_dec_ad2_cp_seed0.pt'
RESULTS_DIR = 'outputs/results/decompose'


def probe_critic_mode(ckpt_path):
    """从 checkpoint 判定价值头形态（ADR-021 方向 B），用于正确重建 agent。

    优先读 checkpoint 内嵌权威 metadata 的 `critic`（自包含协议）；
    旧 ckpt 无该字段时**按 value 网络末层输出维度兜底推断**：
    2-D 权重里最小的首维 = 输出维度（隐藏层为 512/256/128）→ 1 = 标量头，
    >1 = per-agent 头。两者都判不出时回退 `centralized_scalar`（旧行为）。
    """
    try:
        ck = torch.load(ckpt_path, map_location='cpu', weights_only=False)
    except Exception as e:  # 读不出就按旧行为，别让评估挂掉
        print(f"[critic-probe] 无法读取 {ckpt_path}（{type(e).__name__}），回退 centralized_scalar")
        return 'centralized_scalar'
    meta_critic = (ck.get('metadata') or {}).get('critic')
    if meta_critic in ('centralized_scalar', 'per_agent'):
        return meta_critic
    vsd = ck.get('value_state_dict') or {}
    out_dims = [int(v.shape[0]) for k, v in vsd.items()
                if k.endswith('.weight') and getattr(v, 'ndim', 0) == 2]
    if out_dims and min(out_dims) > 1:
        return 'per_agent'
    return 'centralized_scalar'


# 训练标准决策间隔（`configs/experiments/formation_ed_ab_3train_1plus1.yaml` 的
# `decision_interval`）。仅在 ckpt 读不出该字段时兜底 —— 不是"随便挑的默认值"。
TRAIN_DEFAULT_DECISION_INTERVAL = 10


def resolve_decision_interval(args) -> int:
    """解析本次评估实际的 RL 决策间隔（semi-MDP 动作保持步数）。

    【2026-10-01 修复｜静默语义漂移】本参数此前 `default=1`，而训练用 10
    （YAML `decision_interval: 10` → metadata `hyperparameters.decision_interval`）。
    `REPRODUCIBILITY.md` §十 的**主对比命令未显式传它** ⇒ M1（D-RL）行会以"每原始步
    都重新决策"跑，与训练的半 MDP（10 步动作保持）**失配**，且与 P0 三行实跑口径
    （显式 `--decision_interval 10`）不同 —— 属"训练/评估必须同参"铁律要禁的失配，
    同类缺陷见 LRN-20261001-011（被 CLI 默认值静默改变的文档语义）。

    修法：默认改 `None` = **自 ckpt 内嵌 metadata 自动读取**（ckpt 自描述协议，与
    `probe_critic_mode` 同源）；读不到再退回训练标准值并**明确打印**，不静默。
    显式传 `--decision_interval N` 时行为与此前完全一致。
    """
    if args.decision_interval is not None:
        return int(args.decision_interval)
    if args.mode in ('all', 'decompose_m1'):   # 仅这两条模式真正用到 ckpt / RL 行
        try:
            ck = torch.load(args.checkpoint, map_location='cpu', weights_only=False)
            hp = (ck.get('metadata') or {}).get('hyperparameters') or {}
            di = hp.get('decision_interval')
            if di is not None:
                print(f"[decision-interval] 自 ckpt metadata 读取 decision_interval={int(di)}"
                      f"（与训练一致）")
                return int(di)
            print(f"[decision-interval] ckpt 内无该字段（旧 ckpt），"
                  f"回退训练标准值 {TRAIN_DEFAULT_DECISION_INTERVAL}")
        except Exception as e:
            print(f"[decision-interval] 读 ckpt 失败（{type(e).__name__}: {e}），"
                  f"回退训练标准值 {TRAIN_DEFAULT_DECISION_INTERVAL}")
    # m0/mpc/single 行不使用 RL（act_interval 恒 1），该值仅作 metadata 记录
    return TRAIN_DEFAULT_DECISION_INTERVAL


def run_consist(mode):
    """本次评估实际使用的编组预设（`make_env` 与 metadata 共用同一表达式）。

    mode='decompose' → 3列×1+1（本脚本主对比）；mode='single' → 旧架构 1+0。
    """
    return '10kt_1plus1' if mode == 'decompose' else '10kt_1plus0'


def make_env(mode, args):
    """mode: 'decompose'（多列机车级 ED/AB，decompose 模式）| 'single'（1+0 旧架构单机单控）。"""
    num_trains = getattr(args, 'num_trains', 3)
    # 主训练场景：3列×1+1=6 机车智能体（10kt_1plus1），53km，全程 36000 步
    cfg = {
        'num_trains': 1 if mode == 'single' else num_trains,
        'consist_preset': run_consist(mode),
        'grade_profile': args.grade,
        'max_steps': args.max_steps,
        'eval_mode': True,
    }
    # 【2026-10-07 修复｜训练-评估不同参】此处原**硬编码 `target_speed: 20.0`**，而训练
    # 的 `env_cfg` **不含该键**（见 run metadata 的 env_cfg）⇒ 训练侧实际用 env 默认
    # `(v_min+v_max)/2 = (11.111+22.222)/2 = 16.67 m/s（60 km/h）`。target_speed 同时
    # 决定 **obs 的速度误差参考**与**动态目标列距** `target_gap + headway_s·target_speed`
    # （100+5·16.67=183.3m vs 100+5·20=200m），故 20.0 = 逼着策略在**偏高的巡航参考**下
    # 跑 —— 已实测：adr023 ep150 在训练期 long_eval 记 956kN/viol 0，用 20.0 离线复评得
    # 1083kN/viol 49，两者本应逐位一致。属"训练/评估必须同参"铁律要禁的失配（同族缺陷
    # 见 LRN-20261001-011 的 decision_interval 静默漂移）。
    # 修法：默认**不传**该键 = 与训练一致地落到 env 默认；仅在显式 `--target_speed` 时覆盖。
    if getattr(args, 'target_speed', None) is not None:
        cfg['target_speed'] = float(args.target_speed)
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

    **唯一 MPC 基线 = `NMPCController`**（`--mpc_type nmpc`，casadi+IPOPT，列内集中质量
    多体 + MT-2 符号化车钩约束，与 D-RL 同档对冲）。【ADR-022，2026-10-01】**已删除**
    旧的 `FairMPCController`（单质点聚合 + SLSQP）与简化 `MPCController`——主表不再留
    "粗糙 MPC" 作靶子（导师口径）；`--mpc_type` 保留为**单值枚举**，只为让既有文档命令
    （显式带 `--mpc_type nmpc`）继续可复现，不再是"默认值静默决定协议"（LRN-20261001-011）。

    `inner_rule_cyclic`（M3，2026-10-01）：MPC 是否在自身输出上**再叠一层**规则循环护盾。
    注意 decompose 通道里 env 的 `get_action_decomposed` **本来就无条件施加**规则基线
    ⇒ **默认 False 才是与 D-RL 的 like-for-like**（双方各有一层同样的规则护盾）；
    置 True 等于 MPC 叠两层护盾（旧脚本 `mpc_rule` 的遗留语义，在非 decompose 通道下
    曾是 like-for-like，在本通道已不对等），仅用于复现历史对照。
    """
    inner_cyclic = bool(getattr(args, 'mpc_inner_rule_cyclic', False))
    # 成熟集中质量多体 NMPC：预测模型与评估物理同源（标准 MT-2 CouplerParams）。
    # 【M3 2026-10-01】原硬编码 inner_rule_cyclic=True 并注释"与 D-RL 同构"——
    # 在该通道下**不成立**（env 已无条件加规则基线 ⇒ True = 双层护盾），故改用
    # 统一开关，默认 False（与 D-RL 各一层 = like-for-like）。
    env._mpc_controller = NMPCController(
        num_trains=env.num_trains, dt=0.1,
        v_max=env.v_max, v_min=env.v_min,
        target_speed=env.target_speed,
        headway_s=getattr(env, 'headway_s', 5.0),
        gap_min=getattr(args, 'mpc_gap_min', 20.0),
        coupler_params=CouplerParams(),
        inner_rule_cyclic=inner_cyclic,
        ipopt_max_iter=300,
    )
    # grade_at 前瞻由 compute_actions_from_env 从 env.grade_profile 自动重建（Regime A）
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
    # 【2026-10-02】列间间距指标（编队底线：安全列距；单列编组无列间距 → 不产出该组键）
    multi_train = int(getattr(env, 'num_trains', 1)) > 1
    gap_err_abs_sum = 0.0
    gap_err_abs_peak = 0.0
    gap_min_over_ep = float('inf')
    rear_end_steps = 0
    actions = None
    # MPC 求解耗时/状态（同档对冲主指标）：快照本回合新增段，避免跨 seed 累计混淆
    _mpc = getattr(env, '_mpc_controller', None)
    # 【2026-10-01 修复｜跨回合状态残留】MPC 控制器持有**每回合**状态（NMPCController.reset
    # 清 `_meas_accel` / `_last_vel` / `_last_cmd` / `_prev_sol` / solve_times / solve_statuses），
    # 但它只在 `_mount_mpc` 时被 reset 一次；而 `eval_method` 用**同一条 env** 跑 n_seed 个回合
    # ⇒ 不逐回合清零就会让 `--n_seed 3` 的"3 个回合"不独立（回合间继承速度/指令基准）。
    # 此处按回合 reset；n_seed=1 时与"仅在挂载时 reset"等价 ⇒ 既有单 seed MPC 数值不受影响。
    # 【ADR-022 补注】该缺陷最初是在已删除的 FairMPCController 上暴露的（它有 `_gap0_init`/
    # `_gap_ref` 等更重的回合状态）；现存的 NMPCController 同样持有回合状态，故守卫继续有效。
    if _mpc is not None and hasattr(_mpc, 'reset'):
        _mpc.reset()
    st0 = len(_mpc.solve_times) if (_mpc is not None and hasattr(_mpc, 'solve_times')) else 0
    bridge_sat = 0     # MPC 桥接"请求超出 ±0.5 动作权限"的次数（可审计：见 mpc_act）
    # 【2026-10-08 日志可见性】约每 5% 打一条进度心跳。单回合可达 36000 步、静默数十分钟，
    # 一旦进程被 kill，"中间无输出"就无从判断跑到哪、指标是否正常。心跳给可观测的运行轨迹。
    prog_every = max(1, args.max_steps // 20)
    for i in range(args.max_steps):
        if actions is None or i % act_interval == 0:
            actions = act_fn(env)   # RL 决策间隔（semi-MDP 动作保持），rule 基线逐步执行
            _bd = getattr(env, '_mpc_bridge_diag', None)   # 仅 MPC 行会设置
            if _bd is not None:
                bridge_sat += int(_bd.get('ed_saturated', 0))
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
        if multi_train:
            # info 的 gap 指标见 TrainFleetEnv._gap_metrics / step：
            #   gap_err_mean = 各列"实际列距 - 动态目标间距"的均值（m，负=比目标更近）
            #   gap_min_m    = 全程各列中最小的实际列间距（m）
            ge = float(info.get('gap_err_mean', 0.0))
            gm = float(info.get('gap_min_m', float('inf')))
            gap_err_abs_sum += abs(ge)
            gap_err_abs_peak = max(gap_err_abs_peak, abs(ge))
            if np.isfinite(gm):
                gap_min_over_ep = min(gap_min_over_ep, gm)
                rear_end_steps += int(gm <= 0.0)   # 实际列距 ≤0 = 追尾（物理穿透）
        n += 1
        if (i + 1) % prog_every == 0:
            print(f"[progress] {i + 1}/{args.max_steps} 步 | 峰值车钩力 {peak / 1e3:.0f}kN | "
                  f"越限 {int(viol)} | 速度带 {band / max(n, 1):.1%} | 速度 {vel * 3.6:.1f}km/h",
                  flush=True)
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
    # 【2026-10-02】列距指标入组：安全列距 = 编队底线（与车钩力并列），须进主表。
    # 单列编组（num_trains<=1）无列间距概念 → 不产出该组键，避免主表混入无意义 0。
    if multi_train and np.isfinite(gap_min_over_ep):
        out['gap_err_mean_abs_m'] = gap_err_abs_sum / max(n, 1)   # 平均绝对列距误差（m）
        out['gap_err_peak_abs_m'] = gap_err_abs_peak              # 峰值绝对列距误差（m）
        out['gap_min_m'] = gap_min_over_ep                        # 全程最小实际列间距（m）
    # 【既定决策 2026-10｜追尾不作指标】"追尾步数"默认恒 0、且与"防追尾属 ATP 职权"
    # 的安全叙事矛盾（曾三令五申要求移除，2026-09 只改了后被 ADR-022 删除的
    # evaluate_m1_m3_long.py ⇒ 现行入口漏改，本次补齐）。物理穿透（实际列距 ≤0）一旦
    # 出现即判**该行评估无效并报错**；主表安全指标 = ATP 触发次数（safety_events）。
    assert rear_end_steps == 0, (
        f"评估无效：实际列距≤0（物理穿透）{rear_end_steps} 步，该行结果作废")
    if _mpc is not None and getattr(_mpc, 'solve_times', None) and _mpc.solve_times[st0:]:
        st = _mpc.solve_times[st0:]
        out['mpc_solve_mean_ms'] = float(np.mean(st) * 1e3)
        out['mpc_solve_max_ms'] = float(np.max(st) * 1e3)
        # 【2026-10-01 修复】求解失败次数是主指标之一，但"控制器是否记录状态"属**附加诊断**——
        # 缺失时绝不能让整轮评估崩掉（历史事故：某个不记录 `solve_statuses` 的 MPC 控制器
        # 使本行 AttributeError ⇒ **已跑完的 M0/M1 两行也一起丢失、不落盘**）。
        sts = getattr(_mpc, 'solve_statuses', None)
        if sts is not None:
            out['mpc_solve_fail'] = int(sum(1 for s in sts[st0:] if s != 'optimal'))
    if _mpc is not None:
        # 【2026-10-01】桥接权限饱和计数：MPC 的 ED 请求超出 ±0.5 调制权限的次数（步·机车）。
        # 该计数是"MPC 与 D-RL 动作权限是否对等、请求是否被兑现"的**可量化审计信号**
        # （口径见 mpc_act 的 n_sat）；仅 MPC 行产出，RL/规则行无此键。
        out['mpc_bridge_ed_saturated'] = int(bridge_sat)
    return out


def eval_method(name, mode, act_fn, args, act_interval=1):
    rng = np.random.default_rng(args.eval_seed)
    env = make_env(mode, args)
    rs = [rollout(env, act_fn, args, rng, act_interval=act_interval) for _ in range(args.n_seed)]
    env.close()
    agg = {k: float(np.mean([r[k] for r in rs])) for k in rs[0]}
    agg['per_seed'] = [{k: float(v) for k, v in r.items()} for r in rs]
    # MPC 附加诊断：逐项 `in` 守卫 —— `mpc_solve_fail` 只在控制器**记录了**
    # solve_statuses 时才产出（见 rollout），旧写法在 `mpc_solve_mean_ms` 命中时直接下标取它
    # ⇒ 无该字段的控制器会 KeyError、连累整行不落盘（与 LRN-20261001-013 同族）。
    extra = ''
    if 'mpc_solve_mean_ms' in agg:
        extra += (f" | MPC求解 {agg['mpc_solve_mean_ms']:.0f}ms均值/"
                  f"{agg['mpc_solve_max_ms']:.0f}ms峰值")
        if 'mpc_solve_fail' in agg:
            extra += f" | fail {agg['mpc_solve_fail']:.0f}"
    if 'mpc_bridge_ed_saturated' in agg:
        extra += f" | 桥接越权请求 {agg['mpc_bridge_ed_saturated']:.0f} 步·机车"
    # 【2026-10-02】列距（编队底线）：均值/峰值绝对误差 + 最小实际列距。逐项守卫，
    # 单列编组无该组键（不产出）时不打印，避免 KeyError 连累整行不落盘（LRN-20261001-013 同族）。
    # 追尾不打印（既定决策：移出主表，评估入口以 assert rear_end_steps == 0 守卫）。
    if 'gap_min_m' in agg:
        extra += (f" | 列距误差 {agg['gap_err_mean_abs_m']:.1f}m均值/"
                  f"{agg['gap_err_peak_abs_m']:.1f}m峰值 | 最小列距 {agg['gap_min_m']:.1f}m")
    # 【术语 2026-10-12】标签只用描述性中文 + 文献已有概念，不自造指标名：
    #   车钩超限 = coupler limit violations；ATP 触发次数 = ATP interventions；
    #   速度带内占比 = time within permissible speed band；列距/最小列距 = spacing error / min spacing
    print(f"{name}: reward {agg['reward']:+.0f} | peakCoupler {agg['peak_coupler_kN']:.0f}kN | "
          f"车钩超限 {agg['viol']:.0f} | ATP触发次数 {agg['safety_events']:.0f} | "
          f"空气制动步 {agg['ab_steps']:.0f} | meanED {agg['mean_ed']:.3f} | "
          f"速度带内占比 {agg['band_rate']:.2%} | 末速 {agg['final_speed_kmh']:.1f}km/h" + extra)
    return agg


def _gap_delta_str(a, b):
    """Δ列距（a-b）打印片段；任一行无该组键（单列编组不产出）则返回空串，避免 KeyError。"""
    if a is None or b is None or 'gap_min_m' not in a or 'gap_min_m' not in b:
        return ''
    return (f" | Δ列距误差 {a['gap_err_mean_abs_m']-b['gap_err_mean_abs_m']:+.1f}m | "
            f"Δ最小列距 {a['gap_min_m']-b['gap_min_m']:+.1f}m")


# --------------------------------------------------------------------------- #
# MPC → decompose 动作接口桥接（2026-10-01 修复 M1，甲方：反解加性关系）
# --------------------------------------------------------------------------- #
# decompose 模式下 env.step 的动作语义 = **规则基线的加性调制**（见
# MultiLocoController.get_action_decomposed）：
#     final_ed = clip(baseline_ed + ED_MOD_COEF · ed_mod, 0, 1)
#     ab_mod > +0.15 → 抑制本机车 AB 源；ab_mod < -0.15 → 提前引入 MIN 档 AB 兜底
# 故 MPC（原生输出 = 每列目标加速度）必须**反解**成 (ed_mod, ab_mod)；不能把
# get_action_accel 产出的绝对 ED 深度直接当 ed_mod（旧实现的缺陷，见 mpc_act）。
ED_MOD_COEF = float(inspect.signature(
    MultiLocoController.get_action_decomposed).parameters['ed_mod_coef'].default)
# 【ADR-023→024，2026-10-02】带宽**不在此手抄**：直接取 env 实际生效的
# `get_action_decomposed` 默认值（ADR-024 回退为 0.5 半幅），杜绝"评估按 A、执行按 B"
# 的静默失配（M1 桥接缺陷同族，见 LRN-20261001-017）。原为硬编码的镜像常量。
AB_SUPPRESS_MOD = 0.4      # > +0.15 ⇒ 请求抑制该机车 AB 源
AB_TRIGGER_MOD = -0.4      # < -0.15 ⇒ 请求提前引入 MIN 档 AB 兜底
# MPC 请求 AB 兜底的 ED 需求阈值：MPC 自身加速度下界 accel_lo=-0.75 ⇒ 其期望 ED 上限
# = 0.75。取 0.7 = "MPC 已用掉 ≥93% 自有权限仍在要制动" ⇒ 请求预触发兜底。
# 【可达性】desired_ed 可到 0.75 ⇒ 阈值 0.7 **可达**（勿上调到 ≥0.75，否则分支变死代码，
# 同 LRN-20261001-007 型）。单测 test_mpc_bridge_ab_trigger_reachable 守此不变式。
MPC_AB_TRIGGER_ED = 0.7
_MPC_BRIDGE_ANNOUNCED = False


def _rule_baseline_edab(ctrl, tr, env):
    """复算规则循环制动基线 (num_loco,2)，**不污染控制器的两态闩锁**。

    直接用权威实现 `get_action_cyclic_braking`（避免在评估侧复制一份规则逻辑而产生
    漂移），但该方法会写 `ctrl._cyclic_braking`，故调用前后保存/还原。

    ⚠️ 已知近似：本函数以**未协调**带边（v_max_adj=v_min_adj=0）复算，而 env 内部对
    follower 会叠加 `coordination_adj` 的抬带/压带（|adj| ≤ LEAN_MAX_ADJ=3 m/s）；
    该 adj 依赖"前一列已 step 之后的位置"，在 env.step 之前无法复现 ⇒ follower 处于
    带边附近时基线估计可能有偏差（有界，≤0.5 ED 深度）。偏差**不影响安全性**
    （env 侧 clip + SafetyLayer + ETCS 全程仍生效），只影响 MPC 请求的 ED 交付精度；
    这是在当前"闭包内 env 不可改"约束下能做到的最优近似（改 env 可精确，但那需停训）。

    非 MultiLocoController（无该方法）时退化为全零调制，由调用方兜底。
    """
    if not hasattr(ctrl, 'get_action_cyclic_braking'):
        return None
    saved = ctrl._cyclic_braking
    try:
        base = ctrl.get_action_cyclic_braking(
            tr, v_max=env.v_max, v_min=env.v_min, v_max_adj=0.0, v_min_adj=0.0)
    finally:
        ctrl._cyclic_braking = saved
    return np.asarray(base, dtype=float)


def mpc_act(env):
    """MPC 公平接入 decompose：每列目标加速度 → 每机车 (ed_mod, ab_mod) 调制。

    【2026-10-01 修复 M1｜量纲错配（strawman）】旧实现把 `get_action_accel` 产出的
    **绝对 ED 深度**直接当 `ed_mod` 传入，而 env 在 decompose 模式下把它解释为**规则基线的
    加性调制** ⇒ `clip(baseline_ed + 0.5·ed_abs, 0, 1)` 恒 ≥ baseline 且 ≈1.0
    （实测 `MPC meanED=1.000` vs `D-Rule 0.850`），且 AB 通道恒 0（`ab_mod=0` 落在 ±0.15
    死区内）⇒ **MPC 只剩"单调加 ED"一根杠杆**，与 D-RL 权限不对称。根因：旧评估脚本
    （`evaluate_m1_m3_long.py`，已按 ADR-022 删除，git 历史可查）的 MPC 走**非 decompose**
    通道（动作 = 每列绝对目标加速度），桥接被搬进 decompose 通道时未随语义改写。

    现改为**反解加性关系**（甲方）：
        desired_ed = clip(-U / max_accel, 0, 1)        # MPC 期望的绝对 ED 深度
        ed_mod     = clip((desired_ed - baseline_ed) / ED_MOD_COEF, -1, 1)
    并按 MPC 意图给 `ab_mod`（想停/加速 → 抑制；制动需求顶满自有权限 → 预触发兜底）。
    ⇒ MPC 与 D-RL 动作权限**完全一致**（同样 ±ED_MOD_COEF ED 调制、同样 AB 抑制/预触发阈值、
    同样**无牵引通道**——牵引由 env 的 `coordination_adj` 规则注入，对 RL/MPC 一视同仁）；
    唯一差异回到"决策来源"（NMPC 在线优化 vs MAPPO），符合 ADR-016 不失公允口径。

    两处实现细节（有意为之，勿"顺手"改回）：
    1. **不复用 `get_action_accel`**：它内部已乘 `_coupler_throttle_scale`，而 env 的
       `get_action_decomposed` 末尾会**再乘一次** ⇒ 高车钩力时 ED 被双重缓和。此处直接
       内联同一映射（`-U/max_accel`）只取期望深度，把车钩力缓和留给 env 侧统一施加。
       （`get_action_accel` 的牵引分支另有"算而未返回"的死赋值，属闭包内文件缺陷，
       本桥接不再消费该分支，待停训期清理。）
    2. 正 `target_accel`（MPC 想加速）⇒ `desired_ed=0` + 请求抑制 AB，即"缓解到惰行"；
       MPC 无法直接命令牵引（与 D-RL 权限一致，见上）。
    """
    global _MPC_BRIDGE_ANNOUNCED
    U = env._mpc_controller.compute_actions_from_env(env)
    acts = []
    n_sat = n_ab_trigger = n_ab_suppress = 0
    for ti, tr in enumerate(env.trains):
        ctrl = env.multi_loco_controllers[ti]
        max_a = max(float(getattr(ctrl, 'max_accel', 1.0)), 1e-6)
        desired_ed = float(np.clip(-float(U[ti]) / max_a, 0.0, 1.0))
        base = _rule_baseline_edab(ctrl, tr, env)
        if base is None:                       # 兜底：非 MultiLocoController
            acts.append(np.zeros((len(tr.loco_indices), 2), dtype=float))
            continue
        rows = np.zeros((base.shape[0], 2), dtype=float)
        # AB 意图（全列一致：每机车同权，与 D-RL 的逐机车 ab_mod 通道同语义）
        if desired_ed <= 1e-9:
            ab_mod = AB_SUPPRESS_MOD
            n_ab_suppress += 1
        elif desired_ed >= MPC_AB_TRIGGER_ED:
            ab_mod = AB_TRIGGER_MOD
            n_ab_trigger += 1
        else:
            ab_mod = 0.0
        for i in range(base.shape[0]):
            raw = (desired_ed - base[i, 0]) / ED_MOD_COEF
            rows[i, 0] = float(np.clip(raw, -1.0, 1.0))
            rows[i, 1] = ab_mod
            if abs(raw) > 1.0:
                n_sat += 1                     # 请求超出 ±0.5 权限 ⇒ 交付深度受限（可审计）
        acts.append(rows)
    if not _MPC_BRIDGE_ANNOUNCED:
        _MPC_BRIDGE_ANNOUNCED = True
        print(f"[mpc-bridge] 反解加性调制（ED_MOD_COEF={ED_MOD_COEF}；AB 抑制/预触发 "
              f"mod={AB_SUPPRESS_MOD:+.1f}/{AB_TRIGGER_MOD:+.1f}，预触发阈值 "
              f"desired_ed≥{MPC_AB_TRIGGER_ED}）—— MPC 与 D-RL 动作权限一致")
    env._mpc_bridge_diag = {'ed_saturated': n_sat, 'ab_trigger': n_ab_trigger,
                            'ab_suppress': n_ab_suppress}
    return np.concatenate(acts, axis=0).astype(np.float32)


def main():
    p = argparse.ArgumentParser(description='decompose 换架构对比评估')
    p.add_argument('--mode', choices=['all', 'decompose_m1', 'decompose_m0', 'mpc', 'single'],
                   default='all')
    p.add_argument('--checkpoint', default=DEFAULT_CKPT)
    p.add_argument('--grade', default='shuozhou_ningwuxi_beidaniu_49km')
    p.add_argument('--max_steps', type=int, default=36000,
                   help='评估时域（36000=完整 49.6km；15000=23.8km）')
    p.add_argument('--num_trains', type=int, default=3,
                   help='decompose 多列群组列数（主训练=3，6 机车智能体）')
    p.add_argument('--enable_mpc', action='store_true',
                   help='在 decompose env 上挂载 MPC 控制器（供 --mode mpc 使用）')
    p.add_argument('--mpc_type', choices=['nmpc'], default='nmpc',
                   help='MPC 基线类型。**只有 nmpc**：NMPCController（casadi+IPOPT，'
                        '列内集中质量多体 + MT-2 符号化车钩约束）。'
                        '【ADR-022】旧 fair / 简化 MPC 已删除；本参数保留为**单值枚举**，'
                        '只为让既有文档命令按原样可复现（不再是"默认值静默决定协议"）。')
    p.add_argument('--mpc_gap_min', type=float, default=20.0, help='MPC 最小列间距约束 (m)')
    p.add_argument('--mpc_inner_rule_cyclic', action='store_true', default=False,
                   help='【M3】MPC 自身再叠一层规则循环护盾。decompose 通道里 env 已无条件'
                        '施加规则基线 ⇒ 默认 False 才是与 D-RL 的 like-for-like；'
                        'True = MPC 双层护盾（仅复现历史 mpc_rule 对照用）。')
    p.add_argument('--n_seed', type=int, default=3)
    p.add_argument('--eval_seed', type=int, default=0)
    p.add_argument('--init_speed_kmh', type=float, default=80.0)
    p.add_argument('--target_speed', type=float, default=None,
                   help='巡航参考速度 (m/s)。默认 None = 不传该键，与训练一致地落 env 默认 '
                        '(v_min+v_max)/2；显式给值才覆盖（2026-10-07 修复原硬编码 20.0 的失配）')
    p.add_argument('--random_init_speed', action='store_true',
                   help='每回合随机初始速度 [55,75]km/h（鲁棒性协议）')
    p.add_argument('--decision_interval', type=int, default=None,
                   help='RL 决策间隔 N（动作保持，须与训练一致）；'
                        '默认 None = 自 ckpt metadata 自动读取，读不到则用训练标准值 10')
    p.add_argument('--mask_lever', type=str, default='none', choices=['none', 'ed', 'ab'],
                   help='【杠杆隔离消融】ed=禁用 ed_mod(仅AB杠杆)；ab=禁用 ab_mod(仅ED杠杆)。须与训练一致。')
    p.add_argument('--hetero', action='store_true',
                   help='【E4-H】评估在逐车钩异构参数分布上（held-out 用另一组 hetero_seed）')
    p.add_argument('--hetero_seed', type=int, default=0,
                   help='车钩异构抽样 seed（训练固定；held-out 用另一组，如 1000）')
    p.add_argument('--out_suffix', type=str, default='',
                   help='输出文件名后缀（区分 seed/interval/场景，防覆盖），如 "_s0_iv5"')
    args = p.parse_args()

    # 【2026-10-01 修复｜静默缺行】`--mode all` 语义 = 主对比全行（D-Rule / D-RL / MPC，ADR-016 Regime A）。
    # 旧写法在 MPC 块内用 `if getattr(args,'enable_mpc',False) or args.mode=='mpc'` 兜，
    # 而 `--enable_mpc` 是 store_true（默认 False）⇒ **`--mode all` 静默只出 2 行、缺 MPC**，
    # 且第 320 行 `len(results) >= 3` 的三行 Δ 摘要也随之静默跳过 —— 与 `REPRODUCIBILITY.md` §十
    # 「主对比三行 D-RL / D-Rule / MPC @53km」的文档口径不符。此处**在 build_metadata 之前**归一，
    # 保证 `metadata.eval_args.enable_mpc` 与实际行为一致（否则 metadata 记 False、实跑却挂了 MPC）。
    # 注：`make_env` 里的挂载对 M0/M1 行无行为影响（`_mpc_controller` 只在评估脚本的动作函数中使用，
    # env.step 从不读取它）。
    if args.mode in ('all', 'mpc'):
        args.enable_mpc = True

    # 【2026-10-01 修复】RL 决策间隔必须在 build_metadata **之前**解析为实际值，
    # 否则 metadata.eval_args 记的是 None、实跑却用了具体间隔（与「静默缺行」修复同一纪律）。
    args.decision_interval = resolve_decision_interval(args)

    # 【治理】评估入口工况断言 + 元数据内嵌结果 JSON（评估一律 OFFICIAL，无调试物理）
    official_entry_guard(__file__)
    _PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
    # 运行派生（2026-09-30）：metadata 的 physics 块随本次评估的编组固化
    _consist = run_consist('single' if args.mode == 'single' else 'decompose')
    _meta = build_metadata(project_root=_PROJECT_ROOT, case='official',
                           world_cfg=official_world_config(
                               PhysicsConfig(), env_cfg={'consist_preset': _consist}),
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
        # 【ADR-021 方向 B】按 ckpt 内嵌 metadata 判定价值头形态，否则 per-agent 权重
        # 装不进标量头（load_state_dict 形状不匹配）→ 评估直接失败。
        _critic = probe_critic_mode(args.checkpoint)
        agent = MAPPOAgent(num_drones=env0.num_agents, obs_per_drone=env0.obs_dim,
                           act_per_drone=env0.act_dim, device='cpu',
                           critic=_critic, decision_interval=args.decision_interval,
                           physics_dt=float(getattr(env0, 'dt', 0.1)))
        agent.load(args.checkpoint)
        env0.close()

        def policy_act(env):
            flat = env._get_obs_decomposed().flatten()
            a, _ = agent.select_actions(flat, deterministic=True)
            return a.reshape(env.num_agents, 2)

        results['decompose_M1_rl'] = eval_method(
            f'decompose-M1 RL({os.path.basename(args.checkpoint)}, interval={args.decision_interval})',
            'decompose', policy_act, args, act_interval=args.decision_interval)

    # `all` / `mpc` 均已在上方归一为 enable_mpc=True（见「静默缺行」修复注释）
    if args.mode in ('all', 'mpc'):
        results['mpc'] = eval_method(
            f'MPC(NMPC 集中质量多体+MT-2+IPOPT) @ {args.grade}',
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
                  f"ΔATP触发次数 {m1['safety_events']-m0['safety_events']:+.0f}"
                  + _gap_delta_str(m1, m0))
        if mp is not None:
            print(f"Δ(D-RL - MPC):    Δreward {m1['reward']-mp['reward']:+.0f} | "
                  f"ΔpeakCoupler {m1['peak_coupler_kN']-mp['peak_coupler_kN']:+.0f}kN | "
                  f"ΔATP触发次数 {m1['safety_events']-mp['safety_events']:+.0f}"
                  + _gap_delta_str(m1, mp))
    elif len(results) >= 2 and 'decompose_M1_rl' in results:
        m1, m0 = results['decompose_M1_rl'], results.get('decompose_M0_rule')
        if m0 is not None:
            print('-' * 78)
            print(f"Δ(D-RL - D-Rule): Δreward {m1['reward']-m0['reward']:+.0f} | "
                  f"ΔpeakCoupler {m1['peak_coupler_kN']-m0['peak_coupler_kN']:+.0f}kN | "
                  f"ΔATP触发次数 {m1['safety_events']-m0['safety_events']:+.0f}"
                  + _gap_delta_str(m1, m0))

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
