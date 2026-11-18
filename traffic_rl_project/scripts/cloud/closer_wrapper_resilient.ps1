# Resilient dual-active closer wrapper (2026-11-18 owner: "full permissions, just don't burn money").
# ASCII-only on purpose: PowerShell 5.1 misreads non-BOM UTF-8 Chinese comments.
#
# Replaces one-shot run_w4*_closer.ps1 wrappers:
#   1) SELF-HEAL: if closer python dies (crash / killed), wrapper restarts it after 20s.
#      Absolute deadline is computed ONCE at task start; each restart receives only the
#      REMAINING minutes, so a crash can never extend the billing window.
#   2) DUAL-ACTIVE: register two scheduled tasks (Role=primary / backup) with the SAME
#      config. Both watch the same instance; either can stop it. stop_instance() is
#      idempotent (already-Stopped+StopCharging -> success), so the loser exits cleanly.
#   3) Only exits when the closer self-log shows CLOSEOUT_OK (verified StopCharging).
#      Any other exit => restart. "No money saved" is never treated as success.
#
# Usage via schtasks (/TR must stay <261 chars; pass config file + role only):
#   powershell -NoProfile -ExecutionPolicy Bypass -File D:\Code\MultiAgent\traffic_rl_project\scripts\cloud\closer_wrapper_resilient.ps1 -Config D:\Code\MultiAgent\traffic_rl_project\outputs\configs\closer_w4xxx.json -Role primary
param(
  [Parameter(Mandatory=$true)][string]$Config,
  [ValidateSet('primary','backup')][string]$Role = 'primary',
  [switch]$DryRun
)

$cfg = Get-Content $Config -Raw | ConvertFrom-Json
$base = 'D:\Code\MultiAgent\traffic_rl_project'
$py = 'D:\Anaconda\python.exe'
$closer = Join-Path $base 'scripts\cloud\closer_aliyun_ecs.py'
$trace = Join-Path $base "outputs\logs\cloud\closer_${Role}_wrapper_trace.log"
$stdout = Join-Path $base "outputs\logs\cloud\closer_${Role}_stdout.log"
$selfLog = Join-Path $base "outputs\logs\cloud\closer_${Role}.log"
$pullDir = Join-Path $base "outputs\results\$($cfg.run_tag)_${Role}"
$deadlineAbs = (Get-Date).AddMinutes([int]$cfg.deadline_min)

function W([string]$m) {
  $line = "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [$Role] $m"
  Write-Output $line
  Add-Content -Path $trace -Value $line -Encoding utf8
}

W "wrapper entered pid=$PID config=$Config dryrun=$DryRun"
$env:PYTHONIOENCODING = 'utf-8'
$restarts = 0
while ($true) {
  $remain = [math]::Max(1, [math]::Ceiling(($deadlineAbs - (Get-Date)).TotalMinutes))
  $a = @(
    $closer,
    '--instance', $cfg.instance,
    '--ip', $cfg.ip,
    '--deadline-min', "$remain",
    '--marker', $cfg.marker,
    '--log', $cfg.log,
    '--start-marker', $cfg.start_marker,
    '--exit-pattern', $cfg.exit_pattern,
    '--exit-min-count', "$($cfg.exit_min_count)",
    '--poll-s', "$($cfg.poll_s)",
    '--pull-glob', $cfg.pull_glob,
    '--pull-dir', $pullDir,
    '--self-log', $selfLog,
    '--region', $cfg.region
  )
  foreach ($g in $cfg.abort_glob) { $a += @('--abort-glob', $g) }
  if ($DryRun) { $a += '--dry-run' }
  W "python start remain=${remain}min restarts=$restarts"
  & $py @a *>> $stdout
  $rc = $LASTEXITCODE
  $last = if (Test-Path $selfLog) { (Get-Content $selfLog -Tail 1 -Encoding utf8) } else { '' }
  if ($last -match 'CLOSEOUT_OK') {
    W "CLOSEOUT_OK verified (rc=$rc) - wrapper exits"
    exit 0
  }
  $restarts++
  W "python exited rc=$rc WITHOUT closeout - self-heal restart in 20s (restarts=$restarts)"
  Start-Sleep -Seconds 20
}
