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
        ckpt_meta=None,         # 传给 last.pt 的权威 metadata（dict 或 callable()->dict）
        save_fn=None,           # callable(path, metadata) —— 由外部绑定 agents.save
        tb: bool = True,        # 尝试启动 TensorBoard
        initial: int = 0,       # 续训：tqdm 起始进度（已训集数）
        resume: bool = False,   # 续训：不截断既有 CSV（保留旧行）
    ):
        self.log_dir = Path(log_dir)
        self.checkpoint_dir = Path(checkpoint_dir)
        self.tag = tag
        self.seed = seed
        self.total = total_episodes
        self.ckpt_meta = ckpt_meta
        self.save_fn = save_fn
        self.initial = int(initial)
        self.resume = bool(resume)
        self._csv_path = (self.log_dir / f"train_history_{tag}.csv").as_posix()
        # 【2026-09-30 X2】优化器诊断单独落盘（value_loss / entropy / KL / value_norm），
        # 使"训练后期 value 发散"可证伪。**独立文件**而非给 train_history 加列：
        # 后者会让既有 CSV（旧 8 列 schema）与续训 append 的行列数不一致。
        self._loss_csv_path = (self.log_dir / f"train_loss_{tag}.csv").as_posix()

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._init_csv()
        self._init_loss_csv()

        # ---- tqdm 实时进度表（YOLO 风格的滚动行） ----
        self._tqdm = None
        self._use_tqdm = False
        try:
            from tqdm import tqdm
            if save_fn is not None and tb:  # 正常完整模式才开进度条
                self._tqdm = tqdm(total=total_episodes, initial=self.initial,
                                  desc=f"[RL·{tag}]", unit='ep', dynamic_ncols=True)
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
        # 续训时保留旧行（append）；首次训练全量覆写，避免残留旧数据。
        if not self.resume or not Path(self._csv_path).exists():
            Path(self._csv_path).parent.mkdir(parents=True, exist_ok=True)
            with open(self._csv_path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['episode', 'reward', 'peak_coupler_kN', 'violations',
                            'total_loss_k', 'time_s', 'gap_err_mean', 'gap_min_m'])

    def _init_loss_csv(self):
        """优化器诊断 CSV（X2）。续训保留旧行；首次训练覆写。"""
        if not self.resume or not Path(self._loss_csv_path).exists():
            with open(self._loss_csv_path, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow([
                    'episode', 'value_loss', 'policy_loss', 'entropy', 'approx_kl',
                    'grad_norm', 'value_norm_mean', 'value_norm_std', 'total_loss'])

    # ------------------------------------------------------------------ #
    def log_episode(self, ep: int, reward: float, peak_coupler_kN: float,
                    violations: int, total_loss: float = 0.0, elapsed: float = 0.0,
                    gap_err_mean: float = 0.0, gap_min_m: float = 0.0,
                    value_loss: float = 0.0, policy_loss: float = 0.0,
                    entropy: float = 0.0, approx_kl: float = 0.0,
                    grad_norm: float = 0.0, value_norm_mean: float = 0.0,
                    value_norm_std: float = 0.0):
        """逐集调用：写 CSV 行 + 刷终端行 + 写 TB 标量。

        value_loss/policy_loss/entropy/approx_kl/grad_norm/value_norm_* 为【X2 2026-09-30】
        新增的优化器诊断量，单独写 `train_loss_{tag}.csv` + TB（见 `_loss_csv_path`）。
        """
        _ = elapsed
        # CSV（每集一行，实时）
        with open(self._csv_path, 'a', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow([int(ep), f"{float(reward):.2f}", f"{float(peak_coupler_kN):.1f}",
                        int(violations), f"{float(total_loss):.3f}", f"{time.time():.1f}",
                        f"{float(gap_err_mean):.1f}", f"{float(gap_min_m):.1f}"])

        # 优化器诊断 CSV（X2：value 发散可证伪）
        with open(self._loss_csv_path, 'a', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow([
                int(ep), f"{float(value_loss):.6g}", f"{float(policy_loss):.6g}",
                f"{float(entropy):.6g}", f"{float(approx_kl):.6g}",
                f"{float(grad_norm):.6g}", f"{float(value_norm_mean):.6g}",
                f"{float(value_norm_std):.6g}", f"{float(total_loss):.6g}"])

        # 终端（每集刷新）
        msg = (f"Ep {ep}/{self.total} | R {reward:+.0f} | "
               f"pkCpl {peak_coupler_kN:.0f}kN | viol {violations} | loss {total_loss:.3f} | "
               f"vloss {value_loss:.3f} | KL {approx_kl:.3f} | vstd {value_norm_std:.2f} | "
               f"gap_err {gap_err_mean:+.0f}m | gap_min {gap_min_m:.0f}m")
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
                self._writer.add_scalar('gap_err_mean', gap_err_mean, t)
                self._writer.add_scalar('gap_min_m', gap_min_m, t)
                # 【X2】优化器诊断标量
                self._writer.add_scalar('value_loss', value_loss, t)
                self._writer.add_scalar('policy_loss', policy_loss, t)
                self._writer.add_scalar('entropy', entropy, t)
                self._writer.add_scalar('approx_kl', approx_kl, t)
                self._writer.add_scalar('grad_norm', grad_norm, t)
                self._writer.add_scalar('value_norm_mean', value_norm_mean, t)
                self._writer.add_scalar('value_norm_std', value_norm_std, t)
            except Exception as e:
                logger.info(f"[log] TB write 跳过：{e}")

    # ------------------------------------------------------------------ #
    def save_last(self, global_ep: int, best_path_name: str) -> str:
        """快照中间权重 last.pt（YOLO weights/last 语义）。global_ep 用于命名。"""
        if self.save_fn is None:
            return ''
        try:
            p = str(Path(self.checkpoint_dir) / f"mappo_fleet_last_ep{global_ep}_{self.tag}_seed{self.seed}.pt")
            meta = self.ckpt_meta() if callable(self.ckpt_meta) else self.ckpt_meta
            self.save_fn(p, meta)
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