#!/usr/bin/env bash
BASE=/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/checkpoints_formation
# seed0 并行段自 ep1624 起（resume 872 后窗口内 751ep → 全局 1623 起新段）；旧串行段 = ep<1600
# seed1 并行段自 ep130 起（resume 120 best 后窗口内 689ep → 全局 809）
for s in 0 1; do
  f="$BASE/final_seed$s/results/train_history_dec_ad2_cp_seed$s.csv"
  echo "===== seed$s 并行段(治本后)统计 ====="
  if [ $s -eq 0 ]; then
    tr '\r' '\n' < "$f" | tail -n +2 | awk -F, '$1>=1624{n++; if($3>mx)mx=$3; if($3<mn)mn=$3; sum+=$2; if($4>0)v++; if($3>=1000)bad++} END{printf "ep数=%d | reward均值=%.0f | pkCpl min=%.0f max=%.0f | viol>0的ep=%d | pkCpl>=1000的ep=%d\n",n,sum/n,mn,mx,v,bad}'
  else
    tr '\r' '\n' < "$f" | tail -n +2 | awk -F, '$1>=130{n++; if($3>mx)mx=$3; if($3<mn)mn=$3; sum+=$2; if($4>0)v++; if($3>=1000)bad++} END{printf "ep数=%d | reward均值=%.0f | pkCpl min=%.0f max=%.0f | viol>0的ep=%d | pkCpl>=1000的ep=%d\n",n,sum/n,mn,mx,v,bad}'
  fi
done