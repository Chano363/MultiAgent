#!/usr/bin/env bash
# 【2026-10-04】沙盒启动器：v4 奖励（ADR-028 间距危险项穿透有界化）验证。
#
# 目的：验证穿透（后列队首越过前列车尾）时，间距危险项不再退化为"米²"
# （原 -60·53² ≈ -1.7e5/步 ⇒ 单集 R≈-9.18e6 ⇒ ValueNorm vstd 中毒）。
# 与 _debug_train_method_slice16k.yaml 同配置（剖面/编组/窗口一致），仅 reward schema
# 升 v4（train_fleet_env.REWARD_SCHEMA），产物目录改为 _debug_gapv4_bounded_slice16k，
# 不覆盖 v3 旧产物。安全层含 ADR-027 规则重排（保留）。
#
# 监控判据：gap_min<0 出现时单集 |R| 是否回到 ~1e4 量级、vstd 是否不再阶跃到 1e4+。
#
# ⚠️ 沙盒产物不进论文正文/主表（ADR-017 §3）。
set -e

source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

exec python -u run_training.py \
  --experiment configs/experiments/_debug_train_method_slice16k.yaml \
  --seed 0 \
  --checkpoint_dir outputs/checkpoints/formation/_debug_gapv4_bounded_slice16k \
  --results_dir outputs/checkpoints/formation/_debug_gapv4_bounded_slice16k/results \
  --override dirs.figures_dir=outputs/checkpoints/formation/_debug_gapv4_bounded_slice16k/figures