#!/bin/bash
# 诊断 M1 vs M3 反转根因：对比 100% 动力学 + ETCS vs 历史 75% 无 ETCS
cd /mnt/d/Code/MultiAgent/traffic_rl_project
echo "=== 历史 75% 无 ETCS 数据（phys2_full_comparison_20260830.txt，已确认）==="
echo "M1(5seed): reward=+36004 追尾=0 车钩力=659kN"
echo "M3: reward=+9791 追尾=69 车钩力=543kN"
echo "→ M1 协同增量 = +26213（正，M1 占优）"
echo ""
echo "=== 当前 100% + ETCS 数据（eval_100pct_all.log）==="
echo "固定初态: M1=+14697 M3=+21099 → 增量 = -6402（负，M3 占优）"
echo "随机化5seed gap100: M1=+24990 M3=+33735 → 增量 = -8745（负）"
echo ""
echo "=== 关键差异 ===
1. 协议步数: 历史 3000 步，本次修正后 3000 步（已对齐）
2. ETCS: 历史无，本次有（9/2 新增真 ATP）
3. 动力学: 历史 75%，本次 100%（Bug 3 修复）
4. 编组/环境: 相同"
