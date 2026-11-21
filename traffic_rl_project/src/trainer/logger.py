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
from pathlib import Path

import numpy as np

logger = logging.getLogger('TrainingLogger')

# 奖励分量固定列序（与 TrainFleetEnv._calculate_reward 的 reward_term 键一致；
# 固定列序而非动态表头，保证续训 append 与跨 run 合并可比）。
TERM_KEYS = ('speed_band', 'rel_anchor', 'speed_over', 'gap_eff', 'gap_danger',
             'coupler_peak', 'coupler_over', 'ab_cost', 'ed_cost')


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
        # 【2026-11-10 判据③通道】奖励分量逐集落盘（独立文件，理由同上：既有 CSV 列数冻结）。
        # 旧实现只在训练结束时把分量的全程累计打印一次日志 → 无法按 20 集窗口评估
        # "车钩峰值项占比降而 rel_anchor/gap_eff 不塌陷"（判据③），也无法事后复算。
        self._terms_csv_path = (self.log_dir / f"train_reward_terms_{tag}.csv").as_posix()
        # 【ADR-083 / 诊断 §19.44】逐列车钩力量通道（**独立文件**，理由同上：既有 CSV
        # 列数冻结）。落每列的 peak(kN) 与超限步数，使"训练期逐列量能否与评估态
        # 同向"这一候选前提②可在下一次重训窗口内直接判定（否则只能事后猜）。
        # ⚠️ 只写文件，不影响控制/学习路径（零物理改动）。
        self._col_csv_path = (self.log_dir / f"train_col_coupler_{tag}.csv").as_posix()
        self._num_trains = 0   # 由首行落盘时确定（续训时沿用既有列数）

        self.log_dir.mkdir(parents=True, exist_ok=True)
        self._init_csv()
        self._init_loss_csv()
        self._init_terms_csv()
        self._init_col_csv()

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
                            'total_loss_k', 'time_s', 'gap_err_mean', 'gap_min_m',
                            'overspeed_car_steps', 'speed_mean_kmh',
                            'route_end_traj_hits'])

    def _init_loss_csv(self):
        """优化器诊断 CSV（X2）。续训保留旧行；首次训练覆写。"""
        if not self.resume or not Path(self._loss_csv_path).exists():
            with open(self._loss_csv_path, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow([
                    'episode', 'value_loss', 'policy_loss', 'entropy', 'approx_kl',
                    'grad_norm', 'value_norm_mean', 'value_norm_std', 'total_loss'])

    def _init_terms_csv(self):
        """奖励分量 CSV（2026-11-10）。续训保留旧行；首次训练覆写。"""
        if not self.resume or not Path(self._terms_csv_path).exists():
            with open(self._terms_csv_path, 'w', newline='', encoding='utf-8') as f:
                csv.writer(f).writerow(['episode', 'n_steps']
                                       + [f'{k}_sum' for k in TERM_KEYS]
                                       + ['total_sum'])

    def _init_col_csv(self):
        """逐列车钩力量 CSV（ADR-083 / §19.44）。续训保留旧行；首次训练覆写。

        列数 = 1(episode) + 1(n_steps) + 2×n_cols(peak_kN / viol_steps)。
        n_cols 由首行落盘时确定并写入表头；续训时若文件已存在，沿用其列数
        （避免续训前后表头不一致 ⇒ 解析失败）。
        """
        if self.resume and Path(self._col_csv_path).exists():
            try:
                with open(self._col_csv_path, 'r', encoding='utf-8') as f:
                    header = next(csv.reader(f))
                self._num_trains = max(
                    0, (len(header) - 2) // 2)
            except Exception:
                self._num_trains = 0
            return
        with open(self._col_csv_path, 'w', newline='', encoding='utf-8') as f:
            csv.writer(f).writerow(['episode', 'n_steps'])

    # ------------------------------------------------------------------ #
    def log_col_coupler(self, ep: int, col_peak_kN, col_viol_steps, steps: int) -> None:
        """逐集落盘**逐列**车钩力量（ADR-083 / §19.44，候选前提①的落盘通道）。

        `col_peak_kN[i]` = 第 i 列本集断面力峰值（kN）；`col_viol_steps[i]` = 第 i 列
        本集超限**步数**（口径与评估侧 `train_peak_coupler_kN` / `train_coupler_viol`
        对齐）。只写文件，不影响控制/学习路径（零物理改动、零额外仿真成本）。

        表头在首次落盘时按列数写入；后续集沿用（列数不应变）。
        """
        peaks = [float(x) for x in (col_peak_kN or [])]
        viols = [int(x) for x in (col_viol_steps or [])]
        n = min(len(peaks), len(viols))
        peaks, viols = peaks[:n], viols[:n]
        if n == 0:
            return
        if self._num_trains != n:
            # 列数变化（首集确定列数 / 理论上不应变）⇒ 重写表头后追加本行
            self._num_trains = n
            with open(self._col_csv_path, 'w', newline='', encoding='utf-8') as f:
                w = csv.writer(f)
                w.writerow(['episode', 'n_steps']
                           + [f'col{i}_peak_kN' for i in range(n)]
                           + [f'col{i}_viol_steps' for i in range(n)])
        with open(self._col_csv_path, 'a', newline='', encoding='utf-8') as f:
            row = [int(ep), int(steps)]
            row += [f"{p:.6g}" for p in peaks]
            row += [int(v) for v in viols]
            csv.writer(f).writerow(row)

    # ------------------------------------------------------------------ #
    def log_episode(self, ep: int, reward: float, peak_coupler_kN: float,
                    violations: int, total_loss: float = 0.0, elapsed: float = 0.0,
                    gap_err_mean: float = 0.0, gap_min_m: float = 0.0,
                    value_loss: float = 0.0, policy_loss: float = 0.0,
                    entropy: float = 0.0, approx_kl: float = 0.0,
                    grad_norm: float = 0.0, value_norm_mean: float = 0.0,
                    value_norm_std: float = 0.0,
                    overspeed_car_steps: int = 0, speed_mean_kmh: float = 0.0,
                    route_end_traj_hits: int = -1):
        """逐集调用：写 CSV 行 + 刷终端行 + 写 TB 标量。

        value_loss/policy_loss/entropy/approx_kl/grad_norm/value_norm_* 为【X2 2026-09-30】
        新增的优化器诊断量，单独写 `train_loss_{tag}.csv` + TB（见 `_loss_csv_path`）。
        overspeed_car_steps / speed_mean_kmh 为【2026-11-08】新增的两列（追加在 CSV 末尾）：
        超速车·步（任一车 > 线路限速即计 1，逐集累计）+ 领航列平均速度，用于判定
        "车钩力峰值下降是否以超速上升为代价"。
        route_end_traj_hits 为【2026-11-08 截断判据】：本集 n_env 条轨迹中"跑到剖面末端"
        （route_end_reached=True）的条数；== n_env 才算未被 max_steps 砍断，不足则该集
        **不计入改善统计**。-1 = 本次运行未记录（旧归档向后兼容）。
        """
        # CSV（每集一行，实时）
        # 【2026-11-08 修复】time_s = **本集墙钟耗时**（秒），由调用方传入 elapsed。
        # 旧实现写 `time.time()`（绝对时间戳 ≈1.79e9），按集估时长会被彻底误导：
        # 2026-11-08 的 200 集阶段门首集实测 44.9 min/集，CSV 却记成 1794149724.7。
        with open(self._csv_path, 'a', newline='', encoding='utf-8') as f:
            w = csv.writer(f)
            w.writerow([int(ep), f"{float(reward):.2f}", f"{float(peak_coupler_kN):.1f}",
                        int(violations), f"{float(total_loss):.3f}", f"{float(elapsed):.1f}",
                        f"{float(gap_err_mean):.1f}", f"{float(gap_min_m):.1f}",
                        int(overspeed_car_steps), f"{float(speed_mean_kmh):.1f}",
                        int(route_end_traj_hits)])

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
               f"gap_err {gap_err_mean:+.0f}m | gap_min {gap_min_m:.0f}m | "
               f"ovs {overspeed_car_steps} | vavg {speed_mean_kmh:.1f}km/h | "
               f"end {route_end_traj_hits}")
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
                # 【2026-11-08 取舍判据】
                self._writer.add_scalar('overspeed_car_steps', overspeed_car_steps, t)
                self._writer.add_scalar('speed_mean_kmh', speed_mean_kmh, t)
                self._writer.add_scalar('route_end_traj_hits', route_end_traj_hits, t)
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
    def log_reward_terms(self, ep: int, terms: dict, steps: int) -> None:
        """逐集落盘奖励分量累计值（2026-11-10，判据③通道）。

        `terms` = 本集各分量**累计值**（n_env 并行轨迹已在父进程合并；单位与 reward 同），
        `steps` = 本集累计步数（含 n_env 各轨迹）。除以 steps 得每步均值；
        各项绝对值占比即可按 20 集窗口统计"车钩峰值项占比是否下降"。
        只写文件，不影响控制/学习路径。
        """
        with open(self._terms_csv_path, 'a', newline='', encoding='utf-8') as f:
            row = [int(ep), int(steps)]
            row += [f"{float(terms.get(k, 0.0)):.6g}" for k in TERM_KEYS]
            row.append(f"{float(sum(terms.values())):.6g}")
            csv.writer(f).writerow(row)

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