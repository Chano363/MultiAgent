"""训练产物落盘（统一框架 part）：save_training_artifacts。

【2026-09-06 从 train_fleet.py 迁移】统一训练框架复用点。train_fleet /
train_cyclic_braking 均改为从本模块导入，避免重复复刻。
老脚本只 re-export，不破坏既有 `from src.trainer.train_fleet import save_training_artifacts`。
"""
import json
import csv
from pathlib import Path
import logging

import numpy as np

logger = logging.getLogger('Artifacts')


def save_training_artifacts(
    rewards, peak_coupler, violations, meta, results_dir, figures_dir, tag
):
    """保存训练历史（JSON/CSV）并绘制学习曲线 PNG（论文/PPT 用）。

    每次调用都全量覆写，保证训练中断（前台超时）后已有数据不丢失。
    """
    Path(results_dir).mkdir(parents=True, exist_ok=True)
    Path(figures_dir).mkdir(parents=True, exist_ok=True)
    hist = {
        'rewards': [float(r) for r in rewards],
        'peak_coupler_kN': [float(c) for c in peak_coupler],
        'violations': [float(v) for v in violations],
        'meta': meta,
    }
    with open(Path(results_dir) / f"train_history_{tag}.json", 'w',
              encoding='utf-8') as f:
        json.dump(hist, f, ensure_ascii=False, indent=2)
    with open(Path(results_dir) / f"train_history_{tag}.csv", 'w',
              newline='', encoding='utf-8') as f:
        w = csv.writer(f)
        w.writerow(['episode', 'reward', 'peak_coupler_kN', 'violations'])
        for i, (r, c, v) in enumerate(zip(rewards, peak_coupler, violations)):
            w.writerow([i + 1, f"{r:.2f}", f"{c:.1f}", f"{v:.1f}"])

    # 学习曲线图（三子图：reward 原始+10ep滑动平均 / 车钩力峰值 / 超限次数）
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        from src.utils.plot_style import setup_cjk_font
        setup_cjk_font()

        eps = np.arange(1, len(rewards) + 1)
        fig, axes = plt.subplots(3, 1, figsize=(8, 9), sharex=True)
        axes[0].plot(eps, rewards, alpha=0.35, color='tab:blue', label='每回合')
        if len(rewards) >= 10:
            ma = np.convolve(rewards, np.ones(10) / 10, mode='valid')
            axes[0].plot(eps[9:], ma, color='tab:blue', lw=2,
                         label='10 回合滑动平均')
        axes[0].axhline(0, color='gray', lw=0.6, ls='--')
        axes[0].set_ylabel('回合奖励')
        axes[0].legend(loc='lower right', fontsize=8)
        axes[0].set_title(f'MAPPO 群组协同训练曲线（{tag}）', fontsize=11)

        axes[1].plot(eps, peak_coupler, alpha=0.35, color='tab:orange')
        if len(peak_coupler) >= 10:
            ma_c = np.convolve(peak_coupler, np.ones(10) / 10, mode='valid')
            axes[1].plot(eps[9:], ma_c, color='tab:orange', lw=2)
        axes[1].axhline(1000, color='red', lw=1.0, ls='--', label='1000 kN 安全限值')
        axes[1].set_ylabel('车钩力峰值 (kN)')
        axes[1].legend(loc='upper right', fontsize=8)

        axes[2].plot(eps, violations, alpha=0.35, color='tab:green')
        if len(violations) >= 10:
            ma_v = np.convolve(violations, np.ones(10) / 10, mode='valid')
            axes[2].plot(eps[9:], ma_v, color='tab:green', lw=2)
        axes[2].set_ylabel('车钩力超限次数')
        axes[2].set_xlabel('训练回合')
        for ax in axes:
            ax.grid(alpha=0.3)
        fig.tight_layout()
        fig.savefig(Path(figures_dir) / f"fig_learning_curve_{tag}.png", dpi=150)
        plt.close(fig)
    except Exception as e:  # 绘图失败不应中断训练
        logger.warning(f"[警告] 学习曲线绘制失败（训练继续）: {e}")