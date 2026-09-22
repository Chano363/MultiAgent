#!/usr/bin/env bash
LOG=/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/logs_final_parallel
for s in 0 1; do
  f="$LOG/seed$s.log"
  echo "===== seed$s 并行段指标（每ep取最后一次刷新） ====="
  tr '\r' '\n' < "$f" | grep -oE 'Ep [0-9]+/1400 \| R [+-][0-9]+ \| pkCpl [0-9.]+kN \| viol [0-9]+ \| loss [-0-9.]+' | tail -800 | \
  awk '{
    split($2,e,"/"); ep=e[1]; sub(/kN/,"",$8); rr=$5; ppk=$8; vv=$11; ll=$14;
    if(ep>maxep)maxep=ep;
    pkv[ep]=ppk; v[ep]=vv; l[ep]=ll; R[ep]=rr; n_seen[ep]=1
  }
  END{
    n=0; mx=0; mn=1e9; sumR=0; viol=0; bad=0;
    for(i=1;i<=maxep;i++) if(i in n_seen){n++; if(pkv[i]>mx)mx=pkv[i]; if(pkv[i]<mn)mn=pkv[i]; sumR+=R[i]; if(v[i]>0)viol++; if(pkv[i]>=1000)bad++}
    printf "统计ep数=%d | reward均值=%.0f | pkCpl min=%.1f max=%.1f | viol>0的ep=%d | pkCpl>=1000的ep=%d\n", n, sumR/n, mn, mx, viol, bad;
    printf "最近8ep: ";
    for(i=maxep-7;i<=maxep;i++) if(i in n_seen) printf "ep%d(R%s pk%s v%s loss%s) ", i, R[i], pkv[i], v[i], l[i];
    print ""
  }'
done