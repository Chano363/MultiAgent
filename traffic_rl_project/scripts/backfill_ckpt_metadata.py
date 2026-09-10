"""把外置 metadata.json 回填进历史 .pt（一次性迁移脚本，2026-09-10）。

背景：历史 checkpoint 权重(.pt)与训练配置(metadata.json)分离存放——
.pt 在 run 目录顶层，metadata.json 在其 results/ 子目录，弱关联、易失配。

本脚本对指定 roots 下每个 .pt：
1. 向上就近找 metadata.json（.pt 同目录 → 同目录 results/ → 父目录 results/）
2. checkpoint 已含 'metadata' 键 → 跳过（幂等，可重复执行）
3. 否则注入 metadata（含 backfill 溯源标记）后原位重存

用法（WSL conda traffic_rl）：
    python scripts/backfill_ckpt_metadata.py outputs/checkpoints_formation ...          # dry-run
    python scripts/backfill_ckpt_metadata.py outputs/checkpoints_formation ... --apply  # 写盘
"""
import argparse
import json
from pathlib import Path

import torch


def find_metadata(pt_path: Path):
    """就近查找同 run 目录的 metadata.json（返回 Path 或 None）。"""
    d = pt_path.parent
    for cand in (d / 'metadata.json',
                 d / 'results' / 'metadata.json',
                 d.parent / 'results' / 'metadata.json'):
        if cand.is_file():
            return cand
    return None


def load_ckpt(pt: Path):
    """兼容不同 torch 版本的 torch.load（weights_only 参数存在性）。"""
    try:
        return torch.load(pt, map_location='cpu', weights_only=False)
    except TypeError:
        return torch.load(pt, map_location='cpu')


def main():
    ap = argparse.ArgumentParser(description='历史 .pt metadata 回填')
    ap.add_argument('roots', nargs='+', help='要扫描的根目录（rglob *.pt）')
    ap.add_argument('--apply', action='store_true', help='实际写盘（默认 dry-run）')
    args = ap.parse_args()

    stats = {'injected': 0, 'already': 0, 'no_meta': 0, 'fail': 0}
    no_meta_list = []
    for root in args.roots:
        for pt in sorted(Path(root).rglob('*.pt')):
            try:
                ckpt = load_ckpt(pt)
            except Exception as e:
                print(f"[FAIL] {pt}: {e}")
                stats['fail'] += 1
                continue
            if not isinstance(ckpt, dict):
                print(f"[SKIP-NONDICT] {pt}")
                stats['fail'] += 1
                continue
            if 'metadata' in ckpt:
                stats['already'] += 1
                continue
            mpath = find_metadata(pt)
            if mpath is None:
                print(f"[NO-META] {pt}")
                stats['no_meta'] += 1
                no_meta_list.append(str(pt))
                continue
            meta = json.loads(mpath.read_text(encoding='utf-8'))
            meta['backfill'] = {'source': str(mpath),
                                'script': 'scripts/backfill_ckpt_metadata.py'}
            print(f"[INJECT] {pt}  <-  {mpath}")
            stats['injected'] += 1
            if args.apply:
                ckpt['metadata'] = meta
                torch.save(ckpt, pt)

    print(f"\n== 统计 ==\n{stats}")
    if no_meta_list:
        print(f"\n== 无 metadata 的裸 .pt（{len(no_meta_list)} 个，staging 候选）==")
        for p in no_meta_list:
            print(f"  {p}")
    if not args.apply:
        print("\n(dry-run，未写盘；确认无误后加 --apply 执行)")


if __name__ == '__main__':
    main()
