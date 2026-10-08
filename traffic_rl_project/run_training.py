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


from src.trainer.config_schema import parse_experiment_yaml
from src.trainer.train_runner import TrainRunner

logging.basicConfig(level=logging.INFO, format='%(message)s')


def main():
    p = argparse.ArgumentParser(description='统一训练框架（YOLO 风格，配置驱动）')
    p.add_argument('--experiment', required=True, help='实验 YAML 路径')
    p.add_argument('--seed', type=int, default=None)
    p.add_argument('--episodes', type=int, default=None)
    p.add_argument('--resume', type=str, default=None,
                   help="续训 checkpoint 路径（或 'latest'）。给定后 --episodes 语义变为"
                        "『总目标集数』，实跑 = 总目标 - 已训集数（自动从 checkpoint/历史推断）")
    p.add_argument('--resume-weights-only', action='store_true',
                   help='续训只加载网络权重并重置优化器/value_norm（跨物理版本迁移用）')
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
    if args.resume_weights_only:
        cfg.resume_weights_only = True
    if args.checkpoint_dir:
        cfg.checkpoint_dir = args.checkpoint_dir
    if args.results_dir:
        cfg.results_dir = args.results_dir

    # 【2026-10-07 治本｜完整详细日志强制落盘】训练全程 stdout 同步写入 run.log，
    # 位于本次 run 的 results_dir（随产物归档，不污染 outputs/ 根级）。
    # 不许再依赖调用方 shell 重定向/tee —— 曾因 `| tail -N` 把 long_eval 记录连同警告
    # 一起截掉，导致"未达标"只剩文件缺失这一个间接线索，被迫重跑 2h 评估补证据
    # （LRN-20261007-002）。mode='a'：续训/重复调用追加到同一 run.log，不覆盖历史。
    Path(cfg.results_dir).mkdir(parents=True, exist_ok=True)
    _fh = logging.FileHandler(Path(cfg.results_dir) / 'run.log', mode='a', encoding='utf-8')
    _fh.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(message)s'))
    logging.getLogger().addHandler(_fh)

    logging.getLogger().info("=" * 60)
    logging.getLogger().info(f"实验: {cfg.name} | algorithm={cfg.algorithm} "
                             f"interaction={cfg.interaction} | seed={cfg.seed} "
                             f"episodes={cfg.episodes} simcase={cfg.simcase}")
    logging.getLogger().info(f"checkpoint_dir={cfg.checkpoint_dir} results_dir={cfg.results_dir}")
    logging.getLogger().info("=" * 60)

    TrainRunner(cfg).run()


if __name__ == '__main__':
    main()