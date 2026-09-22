#!/usr/bin/env bash
echo "=== WSL 开机时长 ==="
uptime -s 2>/dev/null; uptime
echo "=== seed0/1 日志运行时长(确认是否中途重启) ==="
for s in 0 1; do
  echo "--- seed$s 最后3行 ---"
  tr '\r' '\n' < "/mnt/d/Code/MultiAgent/traffic_rl_project/outputs/logs_final_parallel/seed$s.log" | tail -3
done
echo "=== seed2/3/4 是否有 Traceback/Error/Killed ==="
grep -iE 'traceback|error|exception|killed|memoryerror|killed' /mnt/d/Code/MultiAgent/traffic_rl_project/outputs/logs_final_parallel/seed{2,3,4}.log | tail -10 || echo "无错误关键词"
echo "=== dmesg OOM (最近) ==="
dmesg 2>/dev/null | grep -iE 'oom|killed process' | tail -5 || echo "无权限或无OOM记录"