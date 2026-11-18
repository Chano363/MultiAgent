"""开训前置自检：COVER 配置解析 → env/agent 接线正确 + 三目录唯一。
用法：python tests/check_cover_config_wiring.py
"""
from src.trainer.config_schema import parse_experiment_yaml
from src.trainer.registry import _build_env, _build_agents

cfg = parse_experiment_yaml(
    "configs/experiments/formation_ed_ab_3train_1plus108_cover.yaml")
env = _build_env(cfg)
agents = _build_agents(env, cfg, "cpu")

print("env.cover_enabled  =", env.cover_enabled)
print("agent.cover_enabled=", agents.cover_enabled)
cc = agents.cover_controller
print("controller terms   =", cc.terms if cc else None)
print("up_factor          =", cc.up_factor if cc else None)
print("weight_max         =", cc.weight_max if cc else None)
print("target_cov         =", cc.target_cov if cc else None)
print("checkpoint_dir     =", cfg.checkpoint_dir)
print("results_dir        =", cfg.results_dir)
print("figures_dir        =", cfg.figures_dir)

assert env.cover_enabled is True, "env cover 未启用"
assert agents.cover_enabled is True, "agent cover 未启用"
assert cc is not None, "controller 未构造"
assert tuple(cc.terms) == ("speed_band", "rel_anchor", "gap_eff")
assert cc.up_factor == 1.05, cc.up_factor
assert cc.weight_max == 4.0, cc.weight_max
assert cc.target_cov == 0.0, cc.target_cov
# 三目录必须同 run_tag，且不是历史目录
tag = "w4cover_full_20261118"
assert all(tag in d for d in (cfg.checkpoint_dir, cfg.results_dir, cfg.figures_dir))
assert "fullprof_v7_refspeed" not in cfg.checkpoint_dir, "覆写历史目录!"
print("CONFIG_WIRING_OK")
