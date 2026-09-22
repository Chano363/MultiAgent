#!/usr/bin/env bash
BASE=/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/checkpoints_formation
for s in 0 1; do
  f="$BASE/final_seed$s/results/train_history_dec_ad2_cp_seed$s.csv"
  echo "===== seed$s 最近 10 ep（ep,reward,pkCpl,viol,loss） ====="
  tr '\r' '\n' < "$f" | tail -10
  echo
  echo "----- seed$s 全程统计 -----"
  tr '\r' '\n' < "$f" | tail -n +2 | awk -F, 'BEGIN{v=0;mx=0;mn=1e9;sum=0;n=0;bad=0;vmax=0}
    {n++; if($3>mx)mx=$3; if($3<mn)mn=$3; sum+=$2; if($4>0){v++; if($4>vmax)vmax=$4} if($3>=1000)bad++}
    END{printf "ep数=%d | reward均值=%.0f | pkCpl min=%.0f max=%.0f | viol>0的ep=%d(最大viol=%d) | pkCpl>=1000的ep=%d\n", n, sum/n, mn, mx, v, vmax, bad}'
  echo
done