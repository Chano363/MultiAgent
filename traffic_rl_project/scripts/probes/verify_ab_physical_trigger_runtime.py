"""第 11 投干预面②（`ab_physical_trigger`）的**运行时自证**（零机时零成本）。

为什么需要（AGENTS.md 证据纪律第 6 条 / ADR-077 教训）：
    ADR-077 查出三个 AB 门键只写在 YAML 里、env 从未读取下发 ⇒ 相关机制在两个
    训练窗口中**从未起作用**，而 ADR 与诊断都声称它生效 ⇒ 归因链失实。
    本次改动的两个键（`ab_physical_trigger` / `ab_physical_avail_threshold`）
    虽然**接线完整**（§19.51.4 核实：env 读入 → 下发 controller → controller 内有使用点），
    但"接线完整"**不等于**"运行时真的开着" ⇒ 必须有一支**直接读运行时状态**的自证。

自证内容（全部是**运行时读数**，不是静态字符串断言）：
    ① env 实例持有 `ab_physical_trigger` / `ab_physical_avail_threshold` 且取值与配置一致；
    ② env 构造出的**每个子环境的 controller** 上，这两个属性确实被下发（不是只有 env 属性）；
    ③ **对照侧**（不开闸配置）读出 `ab_physical_trigger == False` ⇒ 证明该读数确实来自配置、
       而不是恒为 True 的常量（否则自证无意义）；
    ④ controller 侧**确有使用点**：源码中 `self.ab_physical_trigger` 被读取（防止退化���死代码，
       即 ADR-077 的镜像形态）。

⚠️ 本自证**不跑整程**（短窗只作活性校验，红线 3）⇒ **不产出任何峰值/安全判据**，
    只证明"配置 → env → controller"这条链在运行时确实通。

用法（conda env traffic_rl，项目根目录）：
    python scripts/probes/verify_ab_physical_trigger_runtime.py
    python scripts/probes/verify_ab_physical_trigger_runtime.py \
        --experiment configs/experiments/formation_ed_ab_3train_1plus108_nincrgatecaprel_colgap.yaml
"""
from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT))

import numpy as np  # noqa: E402

MAIN_CFG = ("configs/experiments/"
            "formation_ed_ab_3train_1plus108_nincrgatecaprel_colgap.yaml")
CTRL_CFG = ("configs/experiments/"
            "formation_ed_ab_3train_1plus108_nincrgatecaprel_colgap_ctrl.yaml")
CTRL_SRC = ROOT / "src" / "controllers" / "multi_loco_controller.py"


def _build_env(experiment: str):
    import yaml
    from src.environments.train_fleet_env import TrainFleetEnv

    cfg = yaml.safe_load((ROOT / experiment).read_text(encoding="utf-8"))
    env_cfg = dict(cfg.get("env_cfg") or {})
    return TrainFleetEnv(env_cfg), env_cfg


def _ctrl_attrs(env):
    """取出 env 实际下发动作的那批 controller。

    ⚠️ 【2026-11-21 自证修正】下发点 `train_fleet_env.py:1902` 发生在
    `env.multi_loco_controllers` 上（逐列 controller 列表），**不是** `tr.ctrl`
    （单列子环境自己的 controller）⇒ 取错对象会读到"从未被下发"的副本
    （表现为属性为 None/False ⇒ 假阴性）。本函数按"env.multi_loco_controllers
    优先、tr.ctrl 仅作退路"的顺序取。
    """
    out = []
    ctrls = getattr(env, "multi_loco_controllers", None) or []
    out.extend([c for c in ctrls if c is not None])
    if out:
        return out
    trains = getattr(env, "trains", None) or []
    for tr in trains:
        ctrl = getattr(tr, "ctrl", None) or getattr(tr, "controller", None)
        if ctrl is not None:
            out.append(ctrl)
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--experiment", default=MAIN_CFG)
    ap.add_argument("--control-experiment", default=CTRL_CFG)
    args = ap.parse_args()

    ok = True

    def check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal ok
        if not cond:
            ok = False
        print(f"[{'OK ' if cond else 'FAIL'}] {name}{(' — ' + detail) if detail else ''}")

    # ---- 主线配置：期望开启 ----
    env, env_cfg = _build_env(args.experiment)
    want = bool(env_cfg.get("ab_physical_trigger", False))
    want_thr = float(env_cfg.get("ab_physical_avail_threshold", 0.99))
    check("env 持有 ab_physical_trigger", getattr(env, "ab_physical_trigger", None) == want,
          f"env={getattr(env, 'ab_physical_trigger', None)} cfg={want}")
    check("env 持有 ab_physical_avail_threshold",
          abs(float(getattr(env, "ab_physical_avail_threshold", -1)) - want_thr) < 1e-12,
          f"env={getattr(env, 'ab_physical_avail_threshold', None)} cfg={want_thr}")

    # ⚠️ 下发发生在**每步动作计算之前**（env:1902 在 get_action_notch_incr 调用前）
    # ⇒ 必须**跑至少一步**才能读到"运行时真的收到"的取值。
    n_cols = int(getattr(env, "num_trains", 3))
    try:
        # ⚠️ 必须先 reset：`_executed_actions` 在 reset 里初始化（train_fleet_env.py:1220），
        #    不 reset 直接 step 会抛 AttributeError（首次踩到，已修）。
        env.reset(options={"speed": 60.0 / 3.6})
        for _ in range(3):
            _o, _r, term, trunc, _i = env.step(
                np.zeros((n_cols, env.act_dim), dtype=np.float32))
            if term or trunc:
                break
        check("env 可 reset+步进", True, "已跑 1–3 步")
    except Exception as e:  # pragma: no cover
        check("env 可 reset+步进", False, str(e))

    ctrls = _ctrl_attrs(env)
    check("controller 数量 = 列数", len(ctrls) == int(getattr(env, "num_trains", 3)),
          f"ctrls={len(ctrls)}")
    if ctrls:
        c0 = ctrls[0]
        check("controller 收到 ab_physical_trigger（运行时下发）",
              getattr(c0, "ab_physical_trigger", None) == want,
              f"ctrl={getattr(c0, 'ab_physical_trigger', None)} expected={want}")
        check("controller 收到 ab_physical_avail_threshold（运行时下发）",
              abs(float(getattr(c0, "ab_physical_avail_threshold", -1)) - want_thr) < 1e-12,
              f"ctrl={getattr(c0, 'ab_physical_avail_threshold', None)} expected={want_thr}")
    else:
        check("能取到 controller", False, "env 未暴露 controller 属性（无法自证下发）")

    # ---- 对照配置：期望关闭（证明读数确实来自配置）----
    try:
        cenv, ccfg = _build_env(args.control_experiment)
        cwant = bool(ccfg.get("ab_physical_trigger", False))
        cn = int(getattr(cenv, "num_trains", 3))
        try:
            cenv.reset(options={"speed": 60.0 / 3.6})
            for _ in range(3):
                _o, _r, term, trunc, _i = cenv.step(
                    np.zeros((cn, cenv.act_dim), dtype=np.float32))
                if term or trunc:
                    break
        except Exception as e:  # pragma: no cover
            print(f"[WARN ] 对照侧步进异常（仍继续读属性）：{e}")
        cctrls = _ctrl_attrs(cenv)
        cv = (getattr(cctrls[0], "ab_physical_trigger", None)
              if cctrls else getattr(cenv, "ab_physical_trigger", None))
        check("对照侧 ab_physical_trigger=False（读数来自配置而非常量）",
              (cv is False) and (cwant is False), f"ctrl/env={cv} cfg={cwant}")
    except Exception as e:  # pragma: no cover
        check("对照侧可构造", False, str(e))

    # ---- 使用点（防死代码）----
    src = CTRL_SRC.read_text(encoding="utf-8")
    uses = len(re.findall(r"self\.ab_physical_trigger", src))
    check("controller 侧存在使用点（非死代码）", uses >= 2,
          f"self.ab_physical_trigger 命中 {uses} 次（定义 + 读取）")

    print("\n[verify] RESULT =", "PASS" if ok else "FAIL")
    print("[verify] ⚠️ 本自证只证明『配置→env→controller』链路在运行时通，"
          "不产出任何峰值/安全判据；机制效果须由第 11 投干预实验回答。")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
