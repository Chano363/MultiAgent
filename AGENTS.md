# AGENTS.md

## Repo layout

Two independent packages at the root:

- **`gym_pybullet_drones/`** — upstream fork of gym-pybullet-drones (quadcopter physics sim). Install with `pip3 install -e .` inside conda env. Run its tests: `cd gym_pybullet_drones && pytest tests/`.
- **`traffic_rl_project/`** — the actual RL research project. Depends on gym-pybullet-drones. Entry point: `traffic_rl_project/src/main.py`.

The research project wraps `MultiHoverAviary` (VEL mode) in `traffic_rl_project/src/environments/formation_control_env.py`.

## Environment

WSL2 Ubuntu 24.04 + Conda (miniconda3) + Python 3.10 + NVIDIA GPU. Python, conda, and WSL are already installed — do not reinstall.

```sh
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
```

Use Windows PowerShell for network access / downloads, not WSL.

## Key commands

```sh
# Train (MAPPO is the only algorithm that converges)
cd /mnt/d/Code/MultiAgent/traffic_rl_project
python src/main.py --mode train --algorithm MAPPO --episodes 500

# Resume from checkpoint
python src/main.py --mode continue --checkpoint outputs/checkpoints/xxx.pt

# Test
python src/main.py --mode test --checkpoint outputs/checkpoints/xxx.pt

# gym-pybullet-drones tests
cd /mnt/d/Code/MultiAgent/gym_pybullet_drones
pytest tests/
```

No linter, typechecker, or formatter is configured in this repo. Follow PEP 8.

## Gotchas (will bite you if ignored)

| Issue | Fix |
|---|---|
| Agent Lightning script never exits | `SharedMemoryExecutionStrategy` must set `main_thread="algorithm"` |
| YAML `3e-4` parsed as string | Always use decimal: `0.0003` |
| Action dim mismatch | Env interaction: reshape `(num_drones, 4)`. Transition storage: flatten to 12-dim. |
| Loss always 0 | Ensure `batch_size ≤ n_steps`, otherwise buffer never fills |
| Episode truncates at step 1 | pybullet-drones default: `x>2.0`. Override to `x>20.0` for formation tasks |
| INFO logs not printing | Every script needs `logging.basicConfig(level=logging.INFO)` |
| VEL mode gravity bias | Do NOT add artificial Z-axis bias. Direction normalization dilutes it. PID handles gravity compensation automatically. |

## Algorithm status

- **MAPPO**: Only algorithm that converged (best reward 235.5)
- **SAC**: Policy degrades late in training
- **PPO**: Unstable, not recommended
- **DQN**: Implemented but not validated

## Config files

- `traffic_rl_project/configs/train_config.yaml` — hyperparameters per algorithm
- `traffic_rl_project/configs/env_config.yaml` — environment params (num_drones, distances, reward weights)
- `traffic_rl_project/configs/agent_lightning_config.yaml` — Agent Lightning optimization config

YAML `.get()` paths must exactly match the YAML structure; mismatches silently fall back to defaults.

## Project docs

- `traffic_rl_project/docs/PROJECT_PIPELINE.md` — **pipeline 总览 + 下一步计划，先读这个**
- `traffic_rl_project/docs/learning_report.md` — full technical report, read first for deep context
- `traffic_rl_project/docs/training_results_standardized.md` — formal results
- `.learnings/LEARNINGS.md` — captured debugging insights

## Code conventions

- PEP 8
- Training scripts must configure logging at entry point
- Temporary scripts must be deleted after use
- Use checkpoints to avoid retraining; save models regularly
- Never use manual/mock environments — only gym-pybullet-drones simulation
