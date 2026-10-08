"""训练框架：续训（resume）解析与状态恢复。

把「从已有 checkpoint 继续训练」做成框架一等公民，解决旧 `--resume` 三个硬伤：

1. 路径写错 → 静默从头重训：`resolve_checkpoint` 对不存在的路径直接抛错；
2. `--episodes` 语义混乱（是"再跑 N 集"）：`plan_run_episodes` 统一为「总目标集数」；
3. 历史/最优态不恢复（学习曲线只剩续训段）：`load_source_history` 从源目录拼接既有曲线。

进度读取优先级（高→低）：`cfg.start_ep>0`（人工校正逃生口）> checkpoint 内嵌
`metadata.done_ep` > 源 history 行数 > 文件名 `_ep{N}[._]`。旧格式 .pt 无 done_ep
时自动回退后三者，并把各信号打印出来供核对。
"""
import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

logger = logging.getLogger('Resume')

_EP_RE = re.compile(r"_ep(\d+)[._]")


@dataclass
class ResumePlan:
    """一次续训的完整解析结果（供 TrainRunner 使用）。"""
    source_pt: str
    done_ep: int = 0                        # 已训全局集数（checkpoint 完成时的 ep 计数）
    best_reward: float = float('-inf')
    long_eval_best: dict = field(
        default_factory=lambda: {'reward': float('-inf'), 'ep': 0})
    prior_rewards: List[float] = field(default_factory=list)
    prior_peak: List[float] = field(default_factory=list)
    prior_viol: List[float] = field(default_factory=list)
    weights_only: bool = False
    source_results_dir: Optional[str] = None


def resolve_checkpoint(cfg) -> str:
    """解析 `cfg.resume` 为具体 .pt 路径。

    支持：具体文件路径 / 字面量 'latest'|'last' / 目录（在其内取最新 ep）。
    路径不存在 → FileNotFoundError（旧行为会静默从头重训，现已禁止）。
    """
    raw = str(getattr(cfg, 'resume', '') or '').strip()
    if not raw:
        raise ValueError("[resume] resume 为空，不应调用 resolve_checkpoint")

    low = raw.lower()
    if low in ('latest', 'last') or Path(raw).is_dir():
        search_dir = Path(raw) if Path(raw).is_dir() else Path(cfg.checkpoint_dir)
        path = _pick_latest(search_dir)
        logger.info(f"[resume] '{raw}' → 选中最新 checkpoint：{path}")
        return path

    p = Path(raw)
    if not p.is_file():
        raise FileNotFoundError(
            f"[resume] 指定的续训 checkpoint 不存在：{p}\n"
            f"（旧行为会静默从头重训，现已禁止；请核对路径，或用 --resume latest）")
    return str(p)


def _pick_latest(d: Path) -> str:
    """目录内取「最新 ep」checkpoint；best（无 ep 号）不参与自动选取。"""
    if not d.exists():
        raise FileNotFoundError(f"[resume] checkpoint 目录不存在：{d}")
    pts = list(d.glob("*.pt"))
    if not pts:
        raise FileNotFoundError(f"[resume] 目录内无 checkpoint（*.pt）：{d}")

    def _key(f: Path):
        m = _EP_RE.search(f.name)
        epn = int(m.group(1)) if m else -1
        return (epn, f.stat().st_mtime)

    return str(max(pts, key=_key))


def plan_run_episodes(cfg, done_ep: int) -> int:
    """续训时 `--episodes` = 总目标集数 → 返回本轮实跑集数（并校验）。

    非续训路径不调用本函数（保持 `--episodes` = 实跑集数）。
    """
    total = int(cfg.episodes)
    if total <= done_ep:
        raise ValueError(
            f"[resume] 目标总集数 --episodes={total} ≤ 已训 {done_ep} ep，无回合可训。\n"
            f"  请把 --episodes 设为 > {done_ep} 的总集数；"
            f"若已训集数推断有误，用 --override start_ep=<正确值> 校正。")
    return total - done_ep


def _source_results_dir(ckpt_path: str) -> Optional[Path]:
    """推断续训权重所属的 results 目录（兼容 <dir>/results 与 <dir> 两种布局）。"""
    d = Path(ckpt_path).parent
    for cand in (d / 'results', d):
        if cand.is_dir() and next(cand.glob('train_history_*.json'), None) is not None:
            return cand
    return d if d.is_dir() else None


def load_source_history(source_results_dir, seed):
    """从源 results 目录拼接既有训练曲线，返回 (rewards, peak, viol, meta)。"""
    if not source_results_dir:
        return [], [], [], {}
    d = Path(source_results_dir)
    files = sorted(d.glob(f'train_history_*seed{seed}*.json'))
    if not files:
        files = sorted(d.glob('train_history_*.json'))
    if not files:
        return [], [], [], {}
    try:
        hist = json.loads(files[-1].read_text(encoding='utf-8'))
    except Exception as e:  # 历史缺失不应中断续训
        logger.warning(f"[resume] 读取历史 {files[-1]} 失败（{type(e).__name__}: {e}），跳过拼接")
        return [], [], [], {}
    rewards = list(hist.get('rewards', []))
    logger.info(f"[resume] 拼接历史曲线：{files[-1]}（{len(rewards)} 行）")
    return (rewards, list(hist.get('peak_coupler_kN', [])),
            list(hist.get('violations', [])), hist.get('meta', {}) or {})


def read_progress(cfg, ckpt_path: str) -> ResumePlan:
    """读取 checkpoint 进度（已训集数 / best / 历史 / long_eval best）。"""
    plan = ResumePlan(source_pt=ckpt_path,
                      weights_only=bool(getattr(cfg, 'resume_weights_only', False)))

    ckpt_meta = {}
    try:
        import torch
        ck = torch.load(ckpt_path, map_location='cpu', weights_only=False)
        ckpt_meta = ck.get('metadata') or {}
    except Exception as e:  # 旧格式/损坏 → 退化为文件名与历史推断
        logger.warning(f"[resume] 读取 {ckpt_path} metadata 失败"
                       f"（{type(e).__name__}: {e}），退化为文件名/历史推断")
        ckpt_meta = {}
    if not isinstance(ckpt_meta, dict):
        ckpt_meta = {}

    src_dir = _source_results_dir(ckpt_path)
    plan.source_results_dir = str(src_dir) if src_dir else None
    plan.prior_rewards, plan.prior_peak, plan.prior_viol, prior_meta = (
        load_source_history(src_dir, cfg.seed))

    # ---- 已训集数：start_ep 逃生口 > metadata.done_ep > history 行数 > 文件名 ----
    signals = {}
    start_ep = int(getattr(cfg, 'start_ep', -1) or -1)
    if start_ep > 0:
        signals['start_ep'] = start_ep
    if ckpt_meta.get('done_ep') is not None:
        signals['metadata.done_ep'] = int(ckpt_meta['done_ep'])
    if plan.prior_rewards:
        signals['history_rows'] = len(plan.prior_rewards)
    m = _EP_RE.search(Path(ckpt_path).name)
    if m:
        signals['filename'] = int(m.group(1))
    done = 0
    for key in ('start_ep', 'metadata.done_ep', 'history_rows', 'filename'):
        if key in signals:
            done = signals[key]
            break
    plan.done_ep = done
    logger.info(f"[resume] 进度信号 {signals} → 采用 done_ep={done}")

    # ---- best_reward：checkpoint 内嵌 > 历史曲线最大 > 源 meta ----
    best = float('-inf')
    if ckpt_meta.get('best_reward') is not None:
        best = float(ckpt_meta['best_reward'])
    if plan.prior_rewards:
        best = max(best, float(max(plan.prior_rewards)))
    if prior_meta.get('best_reward') is not None:
        best = max(best, float(prior_meta['best_reward']))
    plan.best_reward = best

    # ---- long_eval best：checkpoint 内嵌 > 源目录 long_eval_best.json ----
    le = ckpt_meta.get('long_eval_best')
    if not isinstance(le, dict) and src_dir:
        f = Path(src_dir) / 'long_eval_best.json'
        if f.exists():
            try:
                le = json.loads(f.read_text(encoding='utf-8'))
            except Exception:
                le = None
    if isinstance(le, dict):
        plan.long_eval_best = le

    if done > 0 and not plan.prior_rewards:
        logger.warning(f"[resume] 已训 {done} ep 但源目录无 train_history_*.json，"
                       f"学习曲线无法拼接（仅本段起算）")
    return plan