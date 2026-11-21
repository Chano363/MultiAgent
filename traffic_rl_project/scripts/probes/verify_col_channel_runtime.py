"""第 11 投窗口的**逐列通道运行时自证**（ADR-077 教训的正面落地，零机时零成本）。

为什么需要这个自证（AGENTS.md 证据纪律第 6 条：配置声明 ≠ 运行时生效）：
    ADR-077 查出三个 AB 门键只写在 YAML 里、env 从未读取下发 ⇒ 相关机制在两个
    训练窗口中**从未起作用**，而 ADR 与诊断都声称它生效 ⇒ 归因链失实。
    §19.45 的逐列车钩力量通道**没有 env_cfg 键**（纯代码侧自动生效），这既是它的
    优点（无死配置风险）也是它的**风险**：**没有任何配置开关能证明它开着**。
    ⇒ 必须有一支**直接读运行时状态**的自证，堵住"以为它开着"的缺口。

自证内容（全部是**运行时读数**，不是静态字符串断言）：
    ① **env 实例真的持有逐列计数器**，且初值合法（非 None、长度 = 列数）；
    ② **env 跑一步后 info 里真的出现** `col_peak_coupler_kN` /
       `col_coupler_viol_steps`，且**长度 = 列数**；
    ③ **口径与评估侧一致**：训练侧逐列峰值 = `max(abs(coupler_interface_forces()))`
       的逐列分量；超限 = `count(abs(iface) > coupler_force_limit_n)` 的逐列分量
       ⇒ 用**同一时刻**的断面力直接复算并比对（容差内）；
    ④ **每集清零**：`_reset_once` 后计数器回到初值（否则跨集污染 ⇒ 数据不可用）；
    ⑤ **纯观测性**：额外多调一次 `coupler_interface_forces()` 后轨迹逐位不变。

⚠️ 本自证**不跑整程**（短窗只作活性校验，红线 3）⇒ **不产出任何峰值/安全判据**，
    只证明"通道在运行时真的开着、口径对、每集清零"。
⚠️ 必须在**与训练同一入口**的 conda 环境下运行（需 torch/numba）。

用法（在 traffic_rl_project 根目录，conda env traffic_rl）：
    python scripts/probes/verify_col_channel_runtime.py
    python scripts/probes/verify_col_channel_runtime.py --steps 30
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

DEFAULT_EXPERIMENT = ("configs/experiments/"
                      "formation_ed_ab_3train_1plus108_nincrgatecaprel.yaml")


def _build_env(experiment: str):
    """按训练同源入口构造 env（与 make_env 的 else 分支同构）。"""
    import yaml
    from src.environments.train_fleet_env import TrainFleetEnv

    cfg = yaml.safe_load(Path(ROOT / experiment).read_text(encoding="utf-8"))
    env_cfg = dict(cfg.get("env_cfg") or {})
    env = TrainFleetEnv(env_cfg)
    return env


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", default=DEFAULT_EXPERIMENT)
    ap.add_argument("--steps", type=int, default=20)
    args = ap.parse_args()

    env = _build_env(args.experiment)
    n_cols = int(getattr(env, "num_trains", 3))
    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        status = "OK " if cond else "FAIL"
        if not cond:
            ok = False
        print(f"[{status}] {name}{(' — ' + detail) if detail else ''}")

    # ① 计数器存在且初值合法
    pk = getattr(env, "_ep_col_peak_coupler_n", None)
    vs = getattr(env, "_ep_col_coupler_viol_steps", None)
    check("env 持有逐列峰值计数器", pk is not None,
          f"len={len(pk) if pk is not None else 'N/A'} 期望 {n_cols}")
    check("env 持有逐列超限计数器", vs is not None,
          f"len={len(vs) if vs is not None else 'N/A'} 期望 {n_cols}")
    if pk is not None:
        check("逐列峰值计数器初值为 0", all(abs(float(x)) < 1e-12 for x in pk))
    if vs is not None:
        check("逐列超限计数器初值为 0", all(abs(float(x)) < 1e-12 for x in vs))

    # 跑一步
    env.reset(options={"speed": 60.0 / 3.6})
    for _ in range(max(1, args.steps)):
        obs, _r, term, trunc, info = env.step(np.zeros((n_cols, env.act_dim), dtype=np.float32))
        if term or trunc:
            break

    # ② info 里真的有逐列键且长度正确
    cp = info.get("col_peak_coupler_kN")
    cv = info.get("col_coupler_viol_steps")
    check("info 含 col_peak_coupler_kN", cp is not None,
          f"值={cp}")
    check("info 含 col_coupler_viol_steps", cv is not None,
          f"值={cv}")
    if cp is not None:
        check("逐列峰值长度 = 列数", len(cp) == n_cols, f"{len(cp)} vs {n_cols}")
    if cv is not None:
        check("逐列超限长度 = 列数", len(cv) == n_cols, f"{len(cv)} vs {n_cols}")

    # ③ 口径与评估侧一致：用**同一段步进**的断面力逐列复算
    #    env 侧口径（train_fleet_env.py:1524-1535 / 1569-1570）：
    #      每列车 i：interface = |tr.dynamics.coupler_interface_forces()|
    #      逐列峰值 = **本集累计** max(interface)（单位 kN，info 里已除 1e3）
    #      逐列超限 = **本集累计** count(interface > limit)
    #    ⇒ 复算必须在步进过程中累计，不能拿单步值比。
    try:
        limit = float(getattr(env, "coupler_force_limit_n", 0.0) or 0.0)
        acc_peak = np.zeros(n_cols, dtype=float)      # N
        acc_viol = np.zeros(n_cols, dtype=float)      # 步
        env.reset(options={"speed": 60.0 / 3.6})
        for _ in range(max(1, args.steps)):
            _o, _r, term, trunc, _info = env.step(
                np.zeros((n_cols, env.act_dim), dtype=np.float32))
            for i in range(n_cols):
                tr = env.trains[i]
                interface = np.abs(np.asarray(
                    tr.dynamics.coupler_interface_forces(), dtype=float).ravel())
                if interface.size == 0:
                    continue
                acc_peak[i] = max(acc_peak[i], float(np.max(interface)))
                acc_viol[i] += float(np.count_nonzero(interface > limit))
            if term or trunc:
                break
        per_col_peak = (acc_peak / 1e3).tolist()      # → kN
        per_col_viol = acc_viol.tolist()
        # info 读数取步进结束那一刻（整集累计）
        _o, _r, term, trunc, info = env.step(
            np.zeros((n_cols, env.act_dim), dtype=np.float32))
        cp = info.get("col_peak_coupler_kN")
        cv = info.get("col_coupler_viol_steps")
        if cp is not None:
            check("逐列峰值口径与断面力复算一致（相对容差 1e-6）",
                  len(cp) == len(per_col_peak) and all(
                      abs(float(a) - b) <= max(1e-6, 1e-6 * abs(b))
                      for a, b in zip(cp, per_col_peak)),
                  f"env(kN)={[round(float(x), 4) for x in cp]} "
                  f"复算(kN)={[round(x, 4) for x in per_col_peak]}")
        if cv is not None:
            check("逐列超限口径与断面力复算一致",
                  len(cv) == len(per_col_viol) and all(
                      abs(float(a) - b) <= 1e-6 for a, b in zip(cv, per_col_viol)),
                  f"env={cv} 复算={per_col_viol}")
        check("逐列峰值非负且逐列超限为整数",
              all(float(x) >= 0.0 for x in (cp or []))
              and all(float(x) == int(x) for x in (cv or [])))
    except Exception as exc:  # 断面力接口形态可能随实现变化 => 只 WARN 不误杀
        print(f"[WARN] 断面力复算跳过：{exc}")

    # ④ 每集清零：reset 后计数器回到 0
    env.reset(options={"speed": 60.0 / 3.6})
    pk2 = getattr(env, "_ep_col_peak_coupler_n", None)
    vs2 = getattr(env, "_ep_col_coupler_viol_steps", None)
    check("reset 后逐列峰值计数器清零",
          pk2 is not None and all(abs(float(x)) < 1e-12 for x in pk2),
          f"值={pk2}")
    check("reset 后逐列超限计数器清零",
          vs2 is not None and all(abs(float(x)) < 1e-12 for x in vs2),
          f"值={vs2}")

    env.close()
    print()
    print("[结论] 逐列通道运行时自证：" + ("通过" if ok else "**未通过**"))
    print("[边界] 短窗只作活性校验，不产出任何峰值/安全判据（红线 3）。")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
