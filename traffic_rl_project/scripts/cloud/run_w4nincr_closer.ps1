# W4-nincr closer schtasks wrapper (avoids /TR 261-char limit, SERVER_OPS S15).
# ASCII-only on purpose: PowerShell 5.1 misreads non-BOM UTF-8 Chinese comments.
# run_tag=w4nincr_full_20261118 (ADR-074 route-2 first lever, notch-derivative).
# IP below is a PLACEHOLDER until the instance boots (StopCharging releases the
# public IP); update --ip after boot, then restart this task.
$trace = 'D:\Code\MultiAgent\traffic_rl_project\outputs\logs\cloud\closer_wrapper_trace.log'
$stdout = 'D:\Code\MultiAgent\traffic_rl_project\outputs\logs\cloud\closer_stdout_w4nincr_20261118.log'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] wrapper entered pid=$PID" | Out-File $trace -Append -Encoding utf8
$env:PYTHONIOENCODING = 'utf-8'
& 'D:\Anaconda\python.exe' -c "print('PYTHON_ALIVE')" *> "$stdout.probe"
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] probe exit=$LASTEXITCODE probe_out=$(Get-Content "$stdout.probe" -Raw -ErrorAction SilentlyContinue)" | Out-File $trace -Append -Encoding utf8
& 'D:\Anaconda\python.exe' 'D:\Code\MultiAgent\traffic_rl_project\scripts\cloud\closer_aliyun_ecs.py' `
  --instance i-f8zcp6vvis4rnztw0p9y `
  --deadline-min 510 `
  --ip 47.120.13.44 `
  --marker /root/traffic_rl_project/outputs/results/formation_10kt_1plus108/w4nincr_full_20261118/exit_code.txt `
  --log /root/traffic_rl_project/outputs/logs/cloud/lifecycle_w4nincr_full_20261118.txt `
  --start-marker w4nincr_START `
  --exit-pattern 'train_rc=' `
  --exit-min-count 1 `
  --pull-glob '/root/traffic_rl_project/outputs/results/formation_10kt_1plus108/w4nincr_full_20261118/*' `
  --pull-dir 'D:\Code\MultiAgent\traffic_rl_project\outputs\results\w4nincr_recovery' `
  --self-log 'D:\Code\MultiAgent\traffic_rl_project\outputs\logs\cloud\closer_w4nincr_20261118.log' *> $stdout
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] python exit=$LASTEXITCODE" | Out-File $trace -Append -Encoding utf8
exit $LASTEXITCODE
