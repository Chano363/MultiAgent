"""env_cfg 配置生效性校验（机器守卫；ADR-077，诊断 §19.23）。

目的：防「YAML 配了、运行时没生效」这类**死配置**再次出现。
本项目的 AB 门三键（`ab_release_speed_gate` / `ab_release_speed_kmh` /
`ab_apply_speed_min_kmh`）曾长期只写在 YAML 里，`train_fleet_env` 从未读取、
从未下发到 controller ⇒ 第 6 投 / 第 8 投训练中这两个机制**从未起作用**，
而文档与 ADR 都声称它们生效 ⇒ 归因链失实、训练口径与探针口径分裂。
本守卫把这类错误从「靠人读文档发现」变成「机器拦截」。

检查逻辑（对每个实验配置）：
  1. 用 YAML 的 env_cfg 构造 TrainFleetEnv（与训练同一入口）；
  2. 对每个 env_cfg 键：
     - env 自身有同名属性 → 比对 env 属性 vs YAML 值；
     - 否则 controller 有同名属性 → 比对 controller 属性 vs YAML 值；
     - 两侧都没有 → 归入「无处安放」（可能是别名/换算键，需人工确认，
       本脚本只 WARN 不报错）；
  3. 差异项 = ERROR ⇒ 退出码 1。

注意（边界，勿当万灵药）：
  · 本守卫只查**「配了但没生效」**这一种形式错误，
    **不保证**机制本身合理、参数取值合适、效果达标；
  · 「无处安放」只 WARN —— 部分键是别名或单位换算
    （如 `ab_low_speed_margin_kmh` → controller 侧是 `_mps`），
    需要时看代码确认；
  · 键值比较对 bool 用相等、对数值用 1e-9 容差。

用法（在 traffic_rl_project 根目录）：
    python scripts/check_env_cfg_effectiveness.py
    python scripts/check_env_cfg_effectiveness.py configs/experiments/xxx.yaml
退出码：0 = 全部生效（可能含 WARN）；1 = 存在死配置；2 = 无可用配置。
"""
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[1]   # scripts/ → traffic_rl_project
sys.path.insert(0, str(ROOT))

CFG_DIR = ROOT / "configs" / "experiments"

# 「无处安放」白名单：别名 / 单位换算 / 由其它机制消费的键（人工确认过）
# 键 → 说明（诊断 §19.23 复校结论）
KNOWN_ALIASES = {
    "speed_ref_table": "env 侧由 _load_speed_ref_table 消费（速度带表，非 controller 属性）",
    "ab_low_speed_margin_kmh": "别名：controller 侧为 ab_low_speed_margin_mps（km/h→m/s 换算）",
    "ab_staged_apply": "env 侧属性，controller 不持有（单列子环境 train_env 的门控）",
    "ab_staged_gap_s": "env 侧属性，controller 不持有（同上）",
    "ebi_stop_hold_mps": "env 侧属性，透传给 safety_layer（非 controller 属性）",
    "start_randomization": "trainer/评估侧消费（起点里程随机化，非 controller 属性）",
    "hierarchical": "ADR-009.1 换架构后 decompose 模式显式置 False（分层控制器已废止，"
                    "该键仅作旧 config 兼容解析）",
}


def _values_equal(got, want):
    if isinstance(want, bool):
        return bool(got) == want
    try:
        return abs(float(got) - float(want)) < 1e-9
    except (TypeError, ValueError):
        return got == want


def check_one(cfg_path):
    """返回 (errors, warns, checked) 三元组。"""
    import importlib
    env_mod = importlib.import_module("src.environments.train_fleet_env")

    with open(cfg_path, "r", encoding="utf-8") as f:
        cfg = yaml.safe_load(f)
    env_cfg = (cfg or {}).get("env_cfg") or {}
    if not env_cfg:
        return [], [], 0

    env = env_mod.TrainFleetEnv(env_cfg)
    try:
        ctrls = getattr(env, "multi_loco_controllers", None) or []
        errors, warns, checked = [], [], 0
        for key, want in env_cfg.items():
            # 三态判定：
            #  ① 有同名属性且值一致 → 生效（checked）
            #  ② 有同名属性但值不一致 → 死配置（ERROR），除非在白名单里说明是有意覆盖
            #  ③ 两侧都无同名属性 → 别名/其它消费者（WARN，需人工确认）
            if hasattr(env, key):
                got, tgt = getattr(env, key), "env"
            elif ctrls and hasattr(ctrls[0], key):
                got, tgt = getattr(ctrls[0], key), "ctrl"
            else:
                why = KNOWN_ALIASES.get(key, "env 与 controller 均无同名属性（需人工确认）")
                warns.append((key, want, why))
                continue
            if _values_equal(got, want):
                checked += 1
            elif key in KNOWN_ALIASES:
                warns.append((key, want,
                              "运行时=%s（已知有意覆盖：%s）" % (got, KNOWN_ALIASES[key])))
            else:
                errors.append((key, want, got, tgt))
        return errors, warns, checked
    finally:
        try:
            env.close()
        except Exception:
            pass


def main(argv):
    if len(argv) > 1:
        paths = [Path(p) for p in argv[1:]]
    else:
        paths = sorted(CFG_DIR.glob("*.yaml"))
    if not paths:
        print("[cfg-guard] 没有可检查的配置", file=sys.stderr)
        return 2

    total_err = 0
    for p in paths:
        try:
            errors, warns, checked = check_one(p)
        except Exception as e:
            print("[cfg-guard] %s: 检查异常 %s" % (p.name, e))
            total_err += 1
            continue
        rel = p.relative_to(ROOT) if ROOT in p.parents else p
        if errors:
            print("[cfg-guard] %s: ✗ 死配置 %d 项（配了但运行时不一致）"
                  % (rel, len(errors)))
            for key, want, got, tgt in errors:
                print("           %-32s YAML=%-14s 运行时(%s)=%s"
                      % (key, want, tgt, got))
            total_err += len(errors)
        else:
            print("[cfg-guard] %s: ✓ 生效 %d 项" % (rel, checked))
        for key, want, why in warns:
            print("           WARN %-30s YAML=%-14s %s" % (key, want, why))

    if total_err:
        print("[cfg-guard] 结论：存在 %d 项死配置 ⇒ 相关机制在训练中不会生效"
              % total_err)
        return 1
    print("[cfg-guard] 结论：所有被检查配置均无死配置")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
