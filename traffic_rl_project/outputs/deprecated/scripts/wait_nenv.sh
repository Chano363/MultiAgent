#!/bin/bash
cd /mnt/d/Code/MultiAgent/traffic_rl_project || exit 9
for i in $(seq 1 360); do
  if grep -q 'Ep 10/' outputs/diag_53km_nenv_seed0.log 2>/dev/null; then
    echo REACHED_EP10; break
  fi
  if ! kill -0 887 2>/dev/null; then
    echo PROCESS_DIED; break
  fi
  sleep 10
done
echo FINAL
tail -12 outputs/diag_53km_nenv_seed0.log