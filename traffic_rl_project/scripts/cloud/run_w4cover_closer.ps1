# W4-COVER closer 的 schtasks wrapper（/TR 261 字符限制的解法，SERVER_OPS §15）
# 只做一件事：把长参数收在文件里，/TR 仅传本脚本的无空格路径。
# 2026-11-18 12:20 重注册：run_tag=w4cover_full_20261118b（原 20261118 目录因
# closer 诊断测试误触发停机已写 ABORTED_BY_INTERRUPTION.txt，不得引用）。
# stdout/stderr 全部落盘 + trace 行：schtasks 环境下 python 输出必须有归宿；
# probe/trace 用于抓 wrapper/python 的真实退出路径（12:23/12:25 秒退无日志排障）。
$trace = 'D:\Code\MultiAgent\traffic_rl_project\outputs\logs\cloud\closer_wrapper_trace.log'
$stdout = 'D:\Code\MultiAgent\traffic_rl_project\outputs\logs\cloud\closer_stdout_w4cover_20261118b.log'
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] wrapper entered pid=$PID" | Out-File $trace -Append -Encoding utf8
$env:PYTHONIOENCODING = 'utf-8'
& 'D:\Anaconda\python.exe' -c "print('PYTHON_ALIVE')" *> "$stdout.probe"
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] probe exit=$LASTEXITCODE probe_out=$(Get-Content "$stdout.probe" -Raw -ErrorAction SilentlyContinue)" | Out-File $trace -Append -Encoding utf8
& 'D:\Anaconda\python.exe' 'D:\Code\MultiAgent\traffic_rl_project\scripts\cloud\closer_aliyun_ecs.py' `
  --instance i-f8zcp6vvis4rnztw0p9y `
  --deadline-min 480 `
  --ip 47.120.13.44 `
  --marker /root/traffic_rl_project/outputs/results/formation_10kt_1plus108/w4cover_full_20261118b/exit_code.txt `
  --log /root/traffic_rl_project/outputs/logs/cloud/w4cover_full_20261118b.log `
  --start-marker w4cover_START_b `
  --exit-pattern 'train_rc=|训练完成' `
  --exit-min-count 1 `
  --pull-glob '/root/traffic_rl_project/outputs/results/formation_10kt_1plus108/w4cover_full_20261118b/*' `
  --pull-dir 'D:\Code\MultiAgent\traffic_rl_project\outputs\results\w4cover_b_recovery' `
  --self-log 'D:\Code\MultiAgent\traffic_rl_project\outputs\logs\cloud\closer_w4cover_20261118b.log' *> $stdout
"[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] python exit=$LASTEXITCODE" | Out-File $trace -Append -Encoding utf8
exit $LASTEXITCODE
