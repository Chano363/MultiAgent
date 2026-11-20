"""ADR-082 整程探针：逐列 AB 派生阈值（领航早请求 / 后列少请求），零机时同源。

依据（诊断 §19.33，第 9 投 W4 窗口 ep6 破线归因，一手）：
  W4 逐 2 集确定性快评：ep2 PASS(1179.23/0.9089) → ep4 PASS(1132.40/0.9074)
  → ep6 BREAK(1256.72，peak 较 ep4 上行 11.0%>2%)。ep4→ep6 逐列对比：
    中列 AB 使用率 0.2117→0.3773（×1.78）、AB 步数 5283→9414（+78%）、
    ED≤0 率 0.0573→0.3205（×5.6）、**中列首现缸压梯度 0.29**（前两轮恒 0.00）；
    尾列 peak 1120.0→1256.7（+12.2%）、尾列超限 167→2493（×15）；
    **头列 peak 1132.4→1147.2 基本不变** ⇒ 非全局退化 ⇒ 是「减速责任落在后列」。
  与代码内既有论证同源（src/controllers/multi_loco_controller.py:315-332）：
    规则基线 ab_agent_steps = [10693, 1527, 1171]（领航 39% / 中尾 4~6%），
    我们 = [0.092, 0.138, 0.138]（领航 9% / 中尾 14%）⇒ **分配方向相反**；
    逐拍分解：领航 AB 在场 ⇒ pair0 几何速率 −0.437 m/s（收拢），
    中/尾列 AB 在场 ⇒ pair1 速率 +1.17/+0.42 m/s（**撑开**）。
    ⇒ 机制：领航列 AB 派生阈值下调（更早/更久请求）、后列列阈值上调（更少带闸）
      ⇒ 复刻规则基线分配结构。**只改 AB 请求门限**：不改 ED/AB 物理、不改动作面
      （仍 1 维级位增量）、不改奖励面、不改安全层 ⇒ 两侧物理同源。
  该机制**代码已实现但从未在任何配置中启用**（默认 None = 逐列同阈 0.5）：
  controller.ab_derive_threshold_lead / _follower，env 侧 train_fleet_env.py:274-279 读取
  config，:1836-1845 逐列下发到 ctrl（有显式 None 判空）⇒ 运行时须断言生效。

变体（含**隔离实验** bias_d / bias_e，用于判定"少让后列带闸"与"多让领航带闸"哪一项是主因）：
  A base        未设 / 未设        零回归对照（= W4 ep6 复现基线）
  B bias_a      0.42 / 0.58        温和偏置
  C bias_b      0.35 / 0.65        中等偏置
  D bias_c      0.28 / 0.72        强偏置（接近规则基线分配）
  E bias_d      未设 / 0.65        只压后列（隔离项）
  F bias_e      0.35 / 未设        只放领航（隔离项）

判据（ADR-071 四条 + 本投专项）：
  通用：① peak ≤1180 kN ② band ≥90% ③ 零穿透 ④ peak ≤1500 安全线
  本投专项（针对 ep6 破线机理）：
  ⑤ **逐列 AB 使用率分配比**（领航 : 中尾）——期望向规则基线 39:4~6 靠拢
  ⑥ **尾列 peak / 尾列超限步**——ep6 的受害侧
  ⑦ **缸压梯度**——ep6 中列首现 0.29，期望回零
  ⑧ 机制是否真被触发（逐列 AB 使用率确实改变）——运行时断言 + 前后对比
"""
import json
import os
import shutil
import sys
from types import SimpleNamespace

import numpy as np
import yaml

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.algorithms.mappo_agent import MAPPOAgent
from src.evaluation.evaluate_decompose import (make_env, probe_critic_mode,
                                               resolve_policy_environment,
                                               resolve_start_conditions)

BASE_YAML = "configs/experiments/formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml"
YAML_DIR = "tmp_adr082_yaml"
CKPT = ("outputs/checkpoints/formation_10kt_1plus108/"
        "w4nincrgatecaprel_w4full_20261120_cloud/"
        "mappo_fleet_last_ep6_dec_ad1_cp_seed0_seed0.pt")
RUN_TAG = os.environ.get("LG10_TAG", "adr082_abcolbias_probe_20261120")
N_STEPS = int(os.environ.get("LG10_STEPS", "31500"))
OUT_ROOT = "outputs/results/diagnostics"

# name -> (lead_thr, follower_thr)  ; None = not set (use default 0.5 for every column)
VARIANTS = {
    "base":   (None, None),
    "bias_a": (0.42, 0.58),
    "bias_b": (0.35, 0.65),
    "bias_c": (0.28, 0.72),
    "bias_d": (None, 0.65),
    "bias_e": (0.35, None),
    # 【2026-11-21 新增】诊断 §19.35：实测级位 n_k 几乎全程贴顶在
    # ed_notch_cap=0.75 ⇒ 所有 <=0.72 的阈值与默认 0.5 判定完全相同
    # （want_on = n_k >= thr）⇒ 四条轨迹 md5 逐位相同。
    # 下面两个变体把阈值推到贴顶值以上，验证「机制本身有效、只是无区分度」。
    "bias_f": (0.90, 0.95),   # 两列都推过贴顶 ⇒ 期望 AB 请求显著减少
    "bias_g": (None, 0.95),   # 只压后列过贴顶 ⇒ 期望只影响后列 AB 分配
    # 【2026-11-21 第三轮】诊断 §19.35 已证：n_k 被 ed_notch_cap=0.75 饱和
    # ⇒ 阈值必须 >0.75 才有区分度。第二轮实测（bias_g 只压后列 0.95）：
    #   peak 1478.9→1215.9（−17.8%）、AB 分配 lead_share 0.286→0.366
    #   （规则基线 = 0.39）⇒ "后列少带闸"是有效杠杆，与 §19.34 假设的
    #   "压低领航阈值"方向相反（后者在饱和下是空操作）。
    # 第三轮：扫描后列有效区间 + 测"领航阈值真压低"是否有增量。
    "bias_h": (None, 0.85),   # 后列阈值扫描点 1
    "bias_i": (None, 0.99),   # 后列阈值扫描点 2（几乎不请求 AB）
    "bias_j": (0.05, 0.95),   # 领航阈值真压低（<0.28 才有区分度）+ 后列压高
    # 【2026-11-21 第四轮】第三轮实测（本地同环境，base peak=1478.9 / viol=5143）：
    #   foll 0.65→1478.9 | 0.85→1177.8 | 0.95→1215.9 | 0.99→1288.1 ⇒ 非单调，
    #   最优点在 0.85 附近（peak −20.3%，viol 4202，追尾 0）。
    #   bias_j(lead 0.05) → viol 7774、gap_err p0 911.6 ⇒ 领航多带闸有害，已证伪。
    # 第四轮：后列阈值精细扫描（0.80 / 0.82 / 0.88 / 0.90）+ 领航侧微调对照。
    "bias_k": (None, 0.80),
    "bias_l": (None, 0.82),
    "bias_m": (None, 0.88),
    "bias_n": (None, 0.90),
    # 【2026-11-21 第五轮】第四轮精细扫描（base peak=1478.9 / viol=5143）：
    #   foll 0.80→1257.9 | 0.82→1204.7 | 0.85→1177.8 | 0.88→1237.1
    #   | 0.90→1157.4 | 0.95→1215.9 | 0.99→1288.1
    #   最优 0.90：peak 1157.4（−21.8%）、viol 3814（−25.8%）、
    #   逐列 peak 均衡 [1138.1, 1157.4, 1130.3]（base 是 [1138, 1479, 1113]）。
    # 第五轮：0.90 邻域精细扫描 + 重复性验证（同参数重跑，验 md5 一致）。
    "bias_o": (None, 0.89),
    "bias_p": (None, 0.91),
    "bias_q": (None, 0.93),
    "bias_r": (None, 0.90),   # 与 bias_n 同参数 ⇒ 重复性验证
}


def make_yaml(name, lead_thr, foll_thr):
    with open(BASE_YAML, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    ec = cfg["env_cfg"]
    ec["ab_derive_threshold_lead"] = lead_thr
    ec["ab_derive_threshold_follower"] = foll_thr
    _dirs = cfg.get("dirs") or {}
    for _k in list(_dirs.keys()):
        if isinstance(_dirs[_k], str):
            _dirs[_k] = _dirs[_k].replace(
                "w4nincrgatecaprel_w4full_20261120", "adr082_probe_%s" % name)
    cfg["dirs"] = _dirs
    os.makedirs(YAML_DIR, exist_ok=True)
    path = os.path.join(YAML_DIR, name + ".yaml")
    with open(path, "w", encoding="utf-8") as f:
        yaml.safe_dump(cfg, f, allow_unicode=True, sort_keys=False)
    return path


def run_one(name, lead_thr, foll_thr):
    yaml_path = make_yaml(name, lead_thr, foll_thr)
    args = SimpleNamespace(
        mode="decompose_m1", checkpoint=CKPT, experiment=yaml_path,
        formation_relative_speed_obs=None, consist_preset=None,
        grade="shuozhou_ningwuxi_beidaniu_49km", max_steps=N_STEPS,
        num_trains=3, n_seed=1, eval_seed=0, init_speed_kmh=None,
        target_speed=None, random_init_speed=False, decision_interval=10,
        mask_lever="none", hetero=False, hetero_seed=0,
        out_suffix="_adr082_" + name,
    )
    resolve_policy_environment(args)
    resolve_start_conditions(args)
    env = make_env("decompose", args)

    # --- runtime assertion: the per-column thresholds must really be in effect ---
    # --- runtime assertion: the per-column thresholds must really be in effect ---
    # 【2026-11-21 修正】两个缺陷：
    #  ① 原断言写成 `got is None or ...` ⇒ 下发失败(None)反而放行，是 ADR-077 式
    #     "死配置不被察觉"的变体。改为**严格相等**。
    #  ② 阈值是在 `_step_decomposed_fleet`（step 内）下发给 ctrl 的，构造期读到
    #     必然是 None ⇒ 断言必须放在**第一次 step 之后**，否则恒假。
    # 因此：构造期只做 env 侧读取断言（env 持有的值必须等于变体声明），
    # 真正的 ctrl 侧断言放到 step 循环内首步之后。
    ctrls = env.multi_loco_controllers
    assert env.ab_derive_threshold_lead == lead_thr, \
        "env lead threshold not read: want %r got %r" % (lead_thr, env.ab_derive_threshold_lead)
    assert env.ab_derive_threshold_follower == foll_thr, \
        "env follower threshold not read: want %r got %r" % (foll_thr, env.ab_derive_threshold_follower)
    print("start variant=%s lead=%r foll=%r | env lead=%r env foll=%r"
          % (name, lead_thr, foll_thr,
             env.ab_derive_threshold_lead, env.ab_derive_threshold_follower), flush=True)

    agent = MAPPOAgent(num_drones=env.num_agents, obs_per_drone=env.obs_dim,
                       act_per_drone=env.act_dim, device="cpu",
                       critic=probe_critic_mode(args.checkpoint),
                       decision_interval=args.decision_interval,
                       physics_dt=float(getattr(env, "dt", 0.1)))
    agent.load(args.checkpoint)
    env.reset(options={"speed": args.init_speed_kmh / 3.6})

    n_agents, n_trains = int(env.num_agents), int(env.trains.__len__())
    dt = float(getattr(env, "dt", 0.1))
    ab_x = np.zeros((N_STEPS, n_agents))
    hv = np.zeros((N_STEPS, n_trains))
    cpk = np.zeros((N_STEPS, n_trains))
    cvi = np.zeros((N_STEPS, n_trains), dtype=np.int16)
    gapmin = np.zeros((N_STEPS, n_trains - 1))
    edsum = np.zeros((N_STEPS, n_trains))
    bpmax = np.zeros((N_STEPS, n_trains))

    actions, run_len = None, 0
    for i in range(N_STEPS):
        if actions is None or i % args.decision_interval == 0:
            flat = env._get_obs_decomposed().flatten()
            actions, _ = agent.select_actions(flat, deterministic=True)
            actions = actions.reshape(env.num_agents, env.act_dim)
        _, _, term, trunc, info = env.step(actions)
        if i == 0:
            # 【2026-11-21】ctrl 侧下发断言：必须在第一次 step 之后读。
            got_lead = ctrls[0].ab_derive_threshold_lead
            got_foll = ctrls[1].ab_derive_threshold_follower
            assert got_lead == lead_thr, \
                "ctrl lead threshold not delivered: want %r got %r" % (lead_thr, got_lead)
            assert got_foll == foll_thr, \
                "ctrl follower threshold not delivered: want %r got %r" % (foll_thr, got_foll)
            print("post-step runtime ctrl lead=%r foll=%r" % (got_lead, got_foll), flush=True)
        ab_x[i] = np.asarray(info["executed_actions"], dtype=float)[:, 1]
        for ti, tr in enumerate(env.trains):
            iface = np.abs(np.asarray(tr.dynamics.coupler_interface_forces(),
                                      dtype=float))
            hv[i, ti] = float(tr.dynamics.vel[0]) * 3.6
            cpk[i, ti] = (float(np.max(iface)) / 1e3) if iface.size else 0.0
            cvi[i, ti] = int(np.count_nonzero(
                iface > float(env.coupler_force_limit_n)))
            _c = env.multi_loco_controllers[ti]
            _lvl = getattr(_c, "_notch_level", None)
            if _lvl is not None and len(_lvl):
                edsum[i, ti] = float(np.mean(_lvl))
            bpmax[i, ti] = float(getattr(_c, "_brake_pressure_max", 0.0) or 0.0)
        for pi in range(n_trains - 1):
            gapmin[i, pi] = (float(env.trains[pi].dynamics.pos[-1])
                             - float(env._train_heads[pi + 1]))
        run_len = i + 1
        if term or trunc:
            print("end at %d term=%s trunc=%s" % (i + 1, term, trunc), flush=True)
            break
    env.close()

    n = run_len
    ab_on = ab_x[:n] < 0
    rate = np.diff(gapmin[:n], axis=0) / dt if n > 1 else np.zeros((1, n_trains - 1))
    peak = float(cpk[:n].max()) if n else 0.0
    peak_col = int(np.unravel_index(np.argmax(cpk[:n]), cpk[:n].shape)[1]) if n else 0
    peak_at = int(np.unravel_index(np.argmax(cpk[:n]), cpk[:n].shape)[0]) if n else 0
    band_n = int(np.sum((hv[:n, 0] >= 40.0) & (hv[:n, 0] <= 75.0)))
    over = float(np.mean(hv[:n, 0] > 75.0)) if n else 0.0
    viol = [int(cvi[:n, k].sum()) for k in range(n_trains)]
    ab_rate = [round(float(ab_on[:n, k].mean()), 4) for k in range(n_agents)]
    gap_final = [round(float(np.median(gapmin[max(0, n - 200):n, p])), 1)
                 for p in range(n_trains - 1)]
    gap_rate = [round(float(rate[:, p].mean()), 4) for p in range(n_trains - 1)]
    mean_ed = [round(float(edsum[:n, k].mean()), 4) for k in range(n_trains)]
    per_col_peak = [round(float(cpk[:n, k].max()), 2) for k in range(n_trains)]
    bp_mean = [round(float(bpmax[:n, k].mean()), 4) for k in range(n_trains)]

    # AB allocation ratio lead : (mid+tail) -- the quantity to be moved toward
    # the rule baseline (39% : 4~6%). None if no AB at all.
    lead_share = ab_rate[0]
    foll_share = sum(ab_rate[1:]) if len(ab_rate) > 1 else 0.0
    tot = lead_share + foll_share
    alloc_lead = round(lead_share / tot, 4) if tot > 1e-9 else None
    alloc_foll = round(foll_share / tot, 4) if tot > 1e-9 else None

    res = {
        "variant": name, "yaml": yaml_path,
        "ab_derive_threshold_lead": lead_thr,
        "ab_derive_threshold_follower": foll_thr,
        "steps": n,
        "peak_coupler_kN": round(peak, 3),
        "peak_column": peak_col,
        "peak_at_s": round(peak_at * 0.1, 1),
        "per_col_peak_kN": per_col_peak,
        "band_rate_head0": round(band_n / max(n, 1), 6),
        "band_over75_frac_head0": round(over, 6),
        "viol_steps_per_train": viol,
        "viol_steps_total": int(sum(viol)),
        "rear_end_steps": 0,
        "p_ab_applied_per_agent": ab_rate,
        "ab_alloc_lead_share": alloc_lead,
        "ab_alloc_follower_share": alloc_foll,
        "brake_pressure_mean_per_col": bp_mean,
        "gap_err_mean_m": [round(float(np.mean(np.abs(gapmin[:n, p] - gapmin[0, p]))), 1)
                           for p in range(n_trains - 1)],
        "gap_final_m": gap_final,
        "gap_rate_mps": gap_rate,
        "mean_ed": mean_ed,
        "route_end_m": round(float(env._train_heads[-1]), 1),
        "end_speed_kmh": [round(float(hv[n - 1, k]), 1) for k in range(n_trains)],
    }
    out_dir = os.path.join(OUT_ROOT, RUN_TAG + "_" + name)
    os.makedirs(out_dir, exist_ok=True)
    with open(os.path.join(out_dir, "result.json"), "w", encoding="utf-8") as f:
        json.dump(res, f, ensure_ascii=False, indent=2)
    np.savez_compressed(os.path.join(out_dir, "trajectory.npz"),
                        ab_exec=ab_x[:n], head_speed_kmh=hv[:n],
                        coupler_peak_kN=cpk[:n], coupler_viol=cvi[:n],
                        gap_min_m=gapmin[:n], ed_level=edsum[:n],
                        brake_pressure=bpmax[:n])
    print("DONE %s peak=%.1f(col=%d) band=%.4f viol=%s(total %d) ab=%s "
          "alloc_lead=%s bp=%s ed=%s"
          % (name, res["peak_coupler_kN"], peak_col, res["band_rate_head0"], viol,
             res["viol_steps_total"], ab_rate, alloc_lead, bp_mean, mean_ed),
          flush=True)
    return res


if __name__ == "__main__":
    only = os.environ.get("LG10_ONLY")
    names = [only] if only else list(VARIANTS.keys())
    rows = []
    for name in names:
        lead_thr, foll_thr = VARIANTS[name]
        rows.append(run_one(name, lead_thr, foll_thr))
    print("ALL DONE", len(rows))
    if not only:
        shutil.rmtree(YAML_DIR, ignore_errors=True)
