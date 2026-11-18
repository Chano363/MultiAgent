"""开训前置自检：级位派生化（ADR-074）配置解析 → env/agent 接线 + 三目录唯一。
用法：python tests/check_nincr_config_wiring.py
"""
from src.trainer.config_schema import parse_experiment_yaml
from src.trainer.registry import _build_env, _build_agents

cfg = parse_experiment_yaml(
    "configs/experiments/formation_ed_ab_3train_1plus108_nincr.yaml")
env = _build_env(cfg)
agents = _build_agents(env, cfg, "cpu")

print("env.decompose      =", env.decompose)
print("env.act_dim        =", env.act_dim)
print("env.obs_dim        =", env.obs_dim)
print("action_space       =", env.action_space.shape)
print("agent act_per_drone=", agents.act_per_drone)
print("cover_enabled(env) =", getattr(env, 'cover_enabled', False))
print("notch rate         =", env.multi_loco_controllers[0].notch_incr_rate_notches)
print("derive threshold   =", env.multi_loco_controllers[0].ab_derive_threshold)
print("derive notch idx   =", env.multi_loco_controllers[0].ab_derive_notch_idx)
print("hold_s             =", env.multi_loco_controllers[0].ab_notch_hold_s)
print("checkpoint_dir     =", cfg.checkpoint_dir)
print("results_dir        =", cfg.results_dir)
print("figures_dir        =", cfg.figures_dir)

assert env.decompose == 'loco_notch_incr', env.decompose
assert env.act_dim == 1, env.act_dim                # 级位增量 1 维/机车
assert env.obs_dim == 13, env.obs_dim               # 12 + 级位
assert env.action_space.shape == (env.num_agents, 1)
assert agents.act_per_drone == 1, agents.act_per_drone
assert getattr(env, 'cover_enabled', False) is False, "COVER 必须关（隔离变量）"
for c in env.multi_loco_controllers:
    assert c.notch_incr_rate_notches == 3.0
    assert c.ab_derive_threshold == 0.5
    assert c.ab_derive_release_margin == 0.05
    assert c.ab_derive_notch_idx == 2
    assert c.ab_notch_hold_s == 90.0
    assert c.ab_low_speed_release is True
# 三目录必须同 run_tag，且不是历史目录
tag = "w4nincr_full_20261118"
assert all(tag in d for d in (cfg.checkpoint_dir, cfg.results_dir, cfg.figures_dir))
assert "w4cover_full" not in cfg.checkpoint_dir, "覆写历史目录!"
print("CONFIG_WIRING_OK")
