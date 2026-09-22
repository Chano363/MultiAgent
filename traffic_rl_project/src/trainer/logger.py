"""YOLO 式训练日志系统（TrainingLogger）。

对标 Ultralytics (YOLO) 的训练日志体验，供统一训练框架 TrainRunner 驱动：

- 终端实时进度表（tqdm）：每集一行刷新 ep / reward / peakCoupler / viol / loss / 耗时
- TensorBoard scalars：每集 reward/peakCoupler/viol/loss/KL 曲线，跨 seed 可合并对比
- 每集 CSV append：不等 log_interval，逐集落盘（对标 YOLO 的 results.csv）
- last.pt：每集快照中间权重（对标 YOLO 的 weights/last.pt），异于 best.pt

设计原则：
1. 零强依赖——tensorboard/tqdm 缺任一都降级为"终端 print + CSV"，训练绝不因日志崩。
2. 不改数据口——指标数据全由 TrainRunner 传入，本模块只负责"展示 + 落盘"。
3. 逐集高频调用是它的本职，不要在外部做"每 N 集才调"。
"""
import os
import csv
import logging
import time
from pathlib import Path

import numpy as np

logger = logging.getLogger('TrainingLogger')


class TrainingLogger:
    def __init__(
        self,
        log_dir: str,          # 结果目录（CSV dst）
        figures_dir: str,       # 图目录（未用，保留接口）
        checkpoint_dir: str,    # last.pt 落点
        tag: str,               # 实验代号（csv/tb 命名的 tag，与 history_tag 一致）
        seed: int = 0,
        total_episodes: int = 200,
        ckpt_meta: dict = None, # 传给 last.pt 的权威 metadata
        save_fn=None,           # callable(path, metadata) —— 由外部绑定 agents.save
        tb: bool = True,        # 尝试启动 TensorBoard
    ):
        self.log_dir = Path(log_dir)
        self.checkpoint_dir = Path(checkpoint_dir)
        self.tag = tag
        self.seed = seed
        self.total = total_episodes
        self.ckpt_meta = ckpt_meta or {}
        self.save_fn = save_fn
        self._csv_path = (self.log_dir / f"train_history_{tag}.csv").as_posix()

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._init_csv()

        # ---- tqdm 实时进度表（YOLO 风格的滚动行） ----
        self._tqdm = None
        self._use_tqdm = False
        try:
            from tqdm import tqdm
            if save_fn is not None and tb:  # 正常完整模式才开进度条
                self._tqdm = tqdm(total=total_episodes, desc=f"[RL·{tag}]",
                                  unit='ep', dynamic_ncols=True)
                self._use_tqdm = True
        except Exception as e:
            logger.info(f"[log] 终端进度条不可用（降级 print）：{e}")

        # ---- TensorBoard scalars ----
        self._writer = None
        if tb:
            try:
                from torch.utils.tensorboard import SummaryWriter
                tb_dir = self.log_dir.parent / 'tensorboard'
                self._writer = SummaryWriter(log_dir=tb_dir.as_posix())
                logger.info(f"[log] TensorBoard logs → {tb_dir}；查看：tensorboard --logdir={tb_dir.parent}")
            except Exception as e:
                logger.info(f"[log] TensorBoard 不可用（降级，训练继续）：{e}")
                self._writer = None

    # ------------------------------------------------------------------ #
    def _init_csv(self):
        exists = Path(self._csv_path).exists()
        # 全量覆写，避免残留旧行（对标 artifacts 的完整数据，断点续训由 run 侧拼接传入）
        Path(self._csv_path).parent.mkdir(parents=True, exist_ok=True)
        with open(self._csv_path, 'w', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow(['episode', 'reward', 'peak_coupler_kN', 'violations', 'total_loss_k', 'time_s'])

    # ------------------------------------------------------------------ #
    def log_episode(self, ep: int, reward: float, peak_coupler_kN: float,
                    violations: int, total_loss: float = 0.0, elapsed: float = 0.0):
        """逐集调用：写 CSV 行 + 刷终端行 + 写 TB 标量。"""
        _ = elapsed
        # CSV（每集一行，实时）
        with open(self._csv_path, 'a', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow([int(ep), f"{float(reward):.2f}", f"{float(peak_coupler_kN):.1f}",
                        int(violations), f"{float(total_loss):.3f}", f"{time.time():.1f}"])

        # 终端（每集刷新）
        msg = (f"Ep {ep}/{self.total} | R {reward:+.0f} | "
               f"pkCpl {peak_coupler_kN:.0f}kN | viol {violations} | loss {total_loss:.3f}")
        if self._use_tqdm and self._tqdm is not None:
            self._tqdm.set_postfix_str(msg)
            self._tqdm.update(1)
        else:
            logger.info(msg)

        # TensorBoard
        if self._writer is not None:
            try:
                t = int(ep)
                self._writer.add_scalar('reward', reward, t)
                self._writer.add_scalar('peak_coupler_kN', peak_coupler_kN, t)
                self._writer.add_scalar('violations', violations, t)
                self._writer.add_scalar('total_loss', total_loss, t)
            except Exception as e:
                logger.info(f"[log] TB write 跳过：{e}")

    # ------------------------------------------------------------------ #
    def save_last(self, global_ep: int, best_path_name: str) -> str:
        """快照中间权重 last.pt（YOLO weights/last 语义）。global_ep 用于命名。"""
        if self.save_fn is None:
            return ''
        try:
            p = str(Path(self.checkpoint_dir) / f"mappo_fleet_last_ep{global_ep}_{self.tag}_seed{self.seed}.pt")
            self.save_fn(p, self.ckpt_meta)
            return p
        except Exception as e:
            logger.warning(f"[log] last.pt 保存失败（训练继续）：{e}")
            return ''

    # ------------------------------------------------------------------ #
    def close(self):
        if self._tqdm is not None:
            self._tqdm.close()
        if self._writer is not None:
            try:
                self._writer.close()
            except Exception:
                pass