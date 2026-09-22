#!/usr/bin/env bash
source ~/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project
echo "=== which python ==="
which python
echo "=== torch/import 验证 ==="
timeout 90 python - <<'PY'
import torch
print("torch", torch.__version__)
from src.trainer.train_runner import TrainRunner
print("TrainRunner import OK")
PY
echo "exit=$?"