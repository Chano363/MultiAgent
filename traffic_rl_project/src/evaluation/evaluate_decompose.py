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

import numpy as np
import torch

from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent
from src.physics_governance import official_entry_guard, official_world_config
from src.physics_config import PhysicsConfig
from src.metadata import build_metadata

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
    # m0/single 行不使用 RL（act_interval 恒 1），该值仅作 metadata 记录
    return TRAIN_DEFAULT_DECISION_INTERVAL


def resolve_policy_environment(args):
    """Resolve input schema/consist before constructing the evaluation env."""
    requested = getattr(args, 'formation_relative_speed_obs', None)
    if args.mode in ('all', 'decompose_m1') and os.path.isfile(args.checkpoint):
        checkpoint = torch.load(args.checkpoint, map_location='cpu', weights_only=False)
        metadata = checkpoint.get('metadata', {})
        schema = metadata.get('observation_schema', {})
        config = metadata.get('hyperparameters', {}).get('env_cfg', {})
        recorded = config.get('formation_relative_speed_obs')
        if schema.get('name') in ('loco_ed_ab_relative_speed_v1', 'loco_ed_ab_base12'):
            recorded = schema['name'] == 'loco_ed_ab_relative_speed_v1'
        if recorded is not None:
            if requested is not None and requested != recorded:
                raise ValueError('Requested observation schema differs from checkpoint metadata')
            requested = recorded
        elif requested is None and checkpoint.get('model_signature', {}).get('obs_dim') == 14:
            raise ValueError('14-dimensional checkpoint lacks observation schema; '
                             'specify --formation-relative-speed-obs explicitly')
        recorded_consist = config.get('consist_preset')
        if recorded_consist:
            chosen = getattr(args, 'consist_preset', None)
            if chosen is not None and chosen != recorded_consist:
                raise ValueError('Requested consist differs from checkpoint metadata')
            args.consist_preset = recorded_consist
    args.formation_relative_speed_obs = bool(requested)


# env 的默认初始速度（`train_fleet_env._reset_once`：options['speed'] 缺省 65 km/h）。
# 仅在既无 `--experiment` 也读不到 ckpt metadata 时兜底 —— 不是"随便挑的默认值"。
ENV_DEFAULT_INIT_SPEED_KMH = 65.0


def resolve_start_conditions(args):
    """解析并固化「起点条件」（初始速度 + 起点里程），禁止评估静默用另一套起点。

    【2026-11-10 修复｜训练/评估/归档三套口径不同源】修复前本脚本
    `--init_speed_kmh` 默认 **80 km/h**，而训练用 YAML `init_speed_kmh: 70.0`
    （`train_runner` 取 `cfg.init_speed_kmh`）；起点里程在未给 `--experiment` 时
    恒为 0（上游不构造 `start_randomization` ⇒ `_start_rand=None` ⇒ `route_offset=0`），
    而训练是 `start_randomization: {min_m: 4300, max_m: 4300}`。三条链路起点不同源
    ⇒ 同一策略在三个"基线"下分别给出 1072 / 1289 / 1302 kN 峰值，对比失效。

    修法：`--init_speed_kmh` 缺省 None = 按「实验 YAML → ckpt metadata → env 默认」
    逐级取值（与 `resolve_decision_interval` 同款"自描述优先"纪律），并把来源、
    实际值打印出来；起点里程由 `_report_start_conditions` 在 `make_env` 内打印。
    """
    if args.random_init_speed and args.init_speed_kmh is not None:
        raise SystemExit('--random_init_speed 与 --init_speed_kmh 互斥：前者已声明随机起点，'
                         '后者是固定起点口径')
    if args.init_speed_kmh is not None:
        print(f"[起点口径] 初始速度 {float(args.init_speed_kmh):.1f} km/h（来源：命令行 --init_speed_kmh）")
        return

    kmh, source = None, None
    exp = getattr(args, 'experiment', None)
    if exp:
        # 【训练-评估同参】YAML 的 init_speed_kmh 是顶层字段（不在 env_cfg 内），
        # 与 train_runner 的取值优先级 `env_cfg.get(...) or cfg.init_speed_kmh` 一致。
        from src.trainer.config_schema import parse_experiment_yaml
        _cfg = parse_experiment_yaml(exp)
        kmh = float(_cfg.env_cfg.get('init_speed_kmh', _cfg.init_speed_kmh))
        source = f'实验 YAML {exp}'
    if kmh is None and os.path.isfile(getattr(args, 'checkpoint', '') or ''):
        try:
            ck = torch.load(args.checkpoint, map_location='cpu', weights_only=False)
            hp = (ck.get('metadata') or {}).get('hyperparameters') or {}
            val = (hp.get('env_cfg') or {}).get('init_speed_kmh', hp.get('init_speed_kmh'))
            if val is not None:
                kmh, source = float(val), f'ckpt metadata {os.path.basename(args.checkpoint)}'
        except Exception as e:
            print(f"[起点口径] 读 ckpt 失败（{type(e).__name__}: {e}），继续按下一级取值")
    if kmh is None:
        kmh, source = ENV_DEFAULT_INIT_SPEED_KMH, 'env 默认（无实验 YAML / ckpt 可依）'
        print("[起点口径][WARN] 未能从实验 YAML 或 ckpt 取得训练初始速度，回退 env 默认 "
              f"{kmh:.1f} km/h；若非训练同源场景，请显式传 --init_speed_kmh")
    args.init_speed_kmh = float(kmh)
    print(f"[起点口径] 初始速度 {kmh:.1f} km/h（来源：{source}）")


def _report_start_conditions(cfg):
    """打印本次 env 实际生效的起点里程，起点随机段缺失时 WARN（不再静默从 0 起步）。

    `eval_mode=True` 时路线偏移恒取 `start_randomization.min_m`（见
    `train_fleet_env._reset_once`）；配置缺失 ⇒ `_start_rand=None` ⇒ 0 m，
    此时 3 列编队队尾落在负里程，`grade_at` 对越界静默沿用首段坡度 ⇒ 虚构路况。
    """
    sr = cfg.get('start_randomization')
    if isinstance(sr, dict) and sr.get('enabled'):
        lo = float(sr.get('min_m', 0.0))
        hi = float(sr.get('max_m', lo))
        print(f"[起点口径] 起点里程 {lo:.0f}–{hi:.0f} m（eval_mode 取 min_m={lo:.0f} m）")
        return
    print("[起点口径][WARN] 未配置 start_randomization（起点里程 = 0 m）：编队队尾将落在负里程，"
          "坡度按首段外推 ⇒ 与训练（固定 4300 m）不同源，本次结果不可与训练/基线归档直接比较；"
          "如需同源请传 --experiment <训练 YAML>")


def run_consist(mode, args=None):
    """本次评估实际使用的编组预设（`make_env` 与 metadata 共用同一表达式）。

    mode='decompose' → 3列×1+1（本脚本主对比，头/中部双机车 2 万吨，对齐朔黄线实际运营编组 ADR-035）；mode='single' → 旧架构 1+0。
    """
    if mode == 'decompose' and args is not None and getattr(args, 'consist_preset', None):
        return args.consist_preset
    return '20kt_1plus108_1plus108' if mode == 'decompose' else '10kt_1plus0'


def make_env(mode, args):
    """mode: 'decompose'（多列机车级 ED/AB，decompose 模式）| 'single'（1+0 旧架构单机单控）。"""
    num_trains = getattr(args, 'num_trains', 3)
    exp_yaml = getattr(args, 'experiment', None)
    if exp_yaml:
        # 【2026-10-22｜训练-评估同参】从实验 YAML 读**完整** env_cfg。
        # 原实现只构造 6 个键（num_trains/consist/grade/max_steps/eval_mode/decompose），
        # 缺控制器标定参数（cyclic_notch_50 / cyclic_brake_trigger_kmh / cyclic_release_kmh /
        # cyclic_ab_upgrade_kmh / ed_release_coordination / ed_release_hold_s / ed_release_boost_kn /
        # ed_upgrade_ramp_s / ed_upgrade_ramp_scale / ed_grade_feedforward / coupler_override /
        # eot / ed_native_force_conversion）与 v_max/v_min/ab_min_refill_s/车钩门限
        # ⇒ 评估出的规则基线与训练侧不是同一套，违反「训练-评估必须同参」铁律
        # （同族缺陷见 LRN-20261001-011）。给 --experiment 即从训练配置原样取 env_cfg。
        from src.trainer.config_schema import parse_experiment_yaml
        cfg = dict(parse_experiment_yaml(exp_yaml).env_cfg)
        cfg['num_trains'] = 1 if mode == 'single' else num_trains
        cfg['grade_profile'] = args.grade
        cfg['max_steps'] = args.max_steps
        cfg['eval_mode'] = True          # 评估恒定基准起点，且关掉冷启动限速位移
    else:
        # 主训练场景：3列×头/中部双机车=6 机车智能体（20kt_1plus108_1plus108，ADR-035），全程 36000 步
        cfg = {
            'num_trains': 1 if mode == 'single' else num_trains,
            'consist_preset': run_consist(mode, args),
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
        cfg['formation_relative_speed_obs'] = bool(getattr(args, 'formation_relative_speed_obs', False))
        if args.mask_lever and args.mask_lever != 'none':
            cfg['mask_lever'] = args.mask_lever   # 杠杆隔离消融：须与训练一致
        if args.hetero:
            cfg['hetero'] = True
            cfg['hetero_seed'] = args.hetero_seed  # E4-H held-out：另一组 seed=训练未见
    else:
        cfg['hierarchical'] = True
        cfg['adj_coef'] = 0.3
    _report_start_conditions(cfg)
    return TrainFleetEnv(cfg)


def rollout(env, act_fn, args, rng, act_interval=1):
    if args.random_init_speed:
        init = float(rng.uniform(55.0, 75.0)) / 3.6
    else:
        init = args.init_speed_kmh / 3.6
    obs, _ = env.reset(options={'speed': init})
    # 【2026-11-10 起点留痕】打印**实际生效**的初速与各列车头位置，供归档核对
    # "本行结果跑的是哪一段"。请求值与实际值不一致（如冷启动位移）时一并暴露。
    _heads = getattr(env, '_train_heads', None)
    _v0 = [round(float(tr.dynamics.vel[0]) * 3.6, 2) for tr in env.trains]
    print(f"[起点] 请求初速 {init * 3.6:.1f} km/h → 实际 {_v0} km/h | 各列头位 "
          f"{[round(float(h), 1) for h in _heads] if _heads is not None else 'n/a'} m",
          flush=True)
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
    # 【2026-10-08 日志可见性】约每 5% 打一条进度心跳。单回合可达 36000 步、静默数十分钟，
    # 一旦进程被 kill，"中间无输出"就无从判断跑到哪、指标是否正常。心跳给可观测的运行轨迹。
    prog_every = max(1, args.max_steps // 20)
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
    return out


def eval_method(name, mode, act_fn, args, act_interval=1):
    rng = np.random.default_rng(args.eval_seed)
    env = make_env(mode, args)
    rs = [rollout(env, act_fn, args, rng, act_interval=act_interval) for _ in range(args.n_seed)]
    env.close()
    agg = {k: float(np.mean([r[k] for r in rs])) for k in rs[0]}
    agg['per_seed'] = [{k: float(v) for k, v in r.items()} for r in rs]
    extra = ''
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


def main():
    p = argparse.ArgumentParser(description='decompose 换架构对比评估')
    p.add_argument('--mode', choices=['all', 'decompose_m1', 'decompose_m0', 'single'],
                   default='all')
    p.add_argument('--checkpoint', default=DEFAULT_CKPT)
    p.add_argument('--experiment', default=None,
                   help='【推荐】从实验 YAML 读取**完整** env_cfg（含控制器标定参数与车钩门限），'
                        '保证评估与训练同参；给出后 --num_trains/--grade/--max_steps 仍可覆盖。'
                        '不给则退回旧的 6 键最小 cfg（会缺标定参数，仅用于历史复现）。')
    p.add_argument('--formation-relative-speed-obs', action=argparse.BooleanOptionalAction,
                   default=None, help='Use 14D relative-speed observations; defaults to checkpoint schema')
    p.add_argument('--consist-preset', default=None,
                   help='Explicit consist; RL evaluation defaults to checkpoint env_cfg')
    p.add_argument('--grade', default='shuozhou_ningwuxi_beidaniu_49km')
    p.add_argument('--max_steps', type=int, default=36000,
                   help='评估时域（36000=完整 49.6km；15000=23.8km）')
    p.add_argument('--num_trains', type=int, default=3,
                   help='decompose 多列群组列数（主训练=3，6 机车智能体）')
    p.add_argument('--n_seed', type=int, default=3)
    p.add_argument('--eval_seed', type=int, default=0)
    p.add_argument('--init_speed_kmh', type=float, default=None,
                   help='初始速度 (km/h)。默认 None = 自「实验 YAML → ckpt metadata → env 默认 65」'
                        '逐级读取（2026-11-10 修复原默认 80 与训练 70 的静默失配）')
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
    resolve_policy_environment(args)
    # 【2026-11-10】起点口径必须在 build_metadata 之前固化为实际值（同 decision_interval 纪律）：
    # 否则 metadata.eval_args 记 None、实跑却用另一套速度，同族缺陷见 LRN-20261001-011。
    resolve_start_conditions(args)

    # 【2026-10-01 修复】RL 决策间隔必须在 build_metadata **之前**解析为实际值，
    # 否则 metadata.eval_args 记的是 None、实跑却用了具体间隔（与「静默缺行」修复同一纪律）。
    args.decision_interval = resolve_decision_interval(args)

    # 【治理】评估入口工况断言 + 元数据内嵌结果 JSON（评估一律 OFFICIAL，无调试物理）
    official_entry_guard(__file__)
    _PROJECT_ROOT = os.path.join(os.path.dirname(__file__), '..', '..')
    # 运行派生（2026-09-30）：metadata 的 physics 块随本次评估的编组固化
    _consist = run_consist('single' if args.mode == 'single' else 'decompose', args)
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
        _meta['observation_schema'] = dict(env0.observation_schema)
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

    # 单机单控(旧架构1+0)已从主对比中移除：它与 3列1+1 群组非同环境，无对比意义。
    # 仅 --mode single 时保留，供单独回测旧架构。
    if args.mode == 'single':
        results['single_loco_rule'] = eval_method(
            '单机单控(旧架构1+0, coor=0)', 'single',
            lambda env: np.zeros(env.num_trains), args)

    m1, m0 = results.get('decompose_M1_rl'), results.get('decompose_M0_rule')
    if m1 is not None and m0 is not None:
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
