"""统一训练框架 CLI 入口（YOLO 风格）。

用法（WSL traffic_rl）：
    python run_training.py --experiment configs/experiments/l1_cyclic_mappo.yaml
    python run_training.py --experiment configs/experiments/platoon_mappo.yaml --seed 1 --episodes 200
    python run_training.py --experiment configs/experiments/fair_dqn.yaml \
        --override env_cfg.max_steps=60 --episodes 3

后续新增实验线 = 新增/改 configs/experiments/*.yaml，不改框架。
"""
import argparse
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from src.trainer.config_schema import parse_experiment_yaml
from src.trainer.train_runner import TrainRunner

logging.basicConfig(level=logging.INFO, format='%(message)s')


def main():
    p = argparse.ArgumentParser(description='统一训练框架（YOLO 风格，配置驱动）')
    p.add_argument('--experiment', required=True, help='实验 YAML 路径')
    p.add_argument('--seed', type=int, default=None)
    p.add_argument('--episodes', type=int, default=None)
    p.add_argument('--resume', type=str, default=None, help='续训 checkpoint 路径')
    p.add_argument('--checkpoint_dir', type=str, default=None)
    p.add_argument('--results_dir', type=str, default=None)
    p.add_argument('--override', action='append', default=[], metavar='key=value',
                   help='覆盖配置，如 --override env_cfg.max_steps=60')
    args = p.parse_args()

    cfg = parse_experiment_yaml(args.experiment, overrides=args.override)

    # 高频 CLI 覆盖
    if args.seed is not None:
        cfg.seed = args.seed
    if args.episodes is not None:
        cfg.episodes = args.episodes
    if args.resume:
        cfg.resume = args.resume
    if args.checkpoint_dir:
        cfg.checkpoint_dir = args.checkpoint_dir
    if args.results_dir:
        cfg.results_dir = args.results_dir

    logging.getLogger().info("=" * 60)
    logging.getLogger().info(f"实验: {cfg.name} | algorithm={cfg.algorithm} "
                             f"interaction={cfg.interaction} | seed={cfg.seed} "
                             f"episodes={cfg.episodes} simcase={cfg.simcase}")
    logging.getLogger().info(f"checkpoint_dir={cfg.checkpoint_dir} results_dir={cfg.results_dir}")
    logging.getLogger().info("=" * 60)

    TrainRunner(cfg).run()


if __name__ == '__main__':
    main()