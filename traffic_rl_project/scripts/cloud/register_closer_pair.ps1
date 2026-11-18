# Register the dual-active resilient closer pair for a training window.
# ASCII-only for PowerShell 5.1 safety.
#
# Usage (owner has approved the window; register BEFORE boot - red line 6):
#   powershell -NoProfile -ExecutionPolicy Bypass -File register_closer_pair.ps1 `
#     -RunTag w4xxx_full_YYYYMMDD -Ip 47.120.x.x -DeadlineMin 480 `
#     -StartMarker w4xxx_START -TaskPrefix w4xxx
#
# Generates a shared JSON config, registers TWO scheduled tasks (primary + backup),
# starts both, and prints their states. Both tasks run closer_wrapper_resilient.ps1:
# self-healing + idempotent API stop + CLOSEOUT_OK-only exit.
param(
  [Parameter(Mandatory=$true)][string]$RunTag,
  [Parameter(Mandatory=$true)][string]$Ip,
  [Parameter(Mandatory=$true)][int]$DeadlineMin,
  [Parameter(Mandatory=$true)][string]$StartMarker,
  [Parameter(Mandatory=$true)][string]$TaskPrefix,
  [string]$Instance = 'i-f8zcp6vvis4rnztw0p9y',
  [string]$Region = 'cn-heyuan',
  [switch]$DryRun
)

$base = 'D:\Code\MultiAgent\traffic_rl_project'
$cfgDir = Join-Path $base 'outputs\configs'; New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
$cfgPath = Join-Path $cfgDir "closer_${RunTag}.json"
$remoteRoot = '/root/traffic_rl_project/outputs'
$cfg = [ordered]@{
  run_tag        = $RunTag
  instance       = $Instance
  region         = $Region
  ip             = $Ip
  deadline_min   = $DeadlineMin
  marker         = "$remoteRoot/results/formation_10kt_1plus108/$RunTag/exit_code.txt"
  log            = "$remoteRoot/logs/cloud/lifecycle_${RunTag}.txt"
  start_marker   = $StartMarker
  exit_pattern   = 'train_rc='
  exit_min_count = 1
  poll_s         = 120
  abort_glob     = @(
    "$remoteRoot/results/formation_10kt_1plus108/$RunTag/BREAK_LINE.txt",
    "$remoteRoot/results/formation_10kt_1plus108/$RunTag/DEAD_*.txt"
  )
  pull_glob      = "$remoteRoot/results/formation_10kt_1plus108/$RunTag/*"
}
$cfg | ConvertTo-Json -Depth 5 | Set-Content -Path $cfgPath -Encoding UTF8
Write-Output "config=$cfgPath"

$wrapper = Join-Path $base 'scripts\cloud\closer_wrapper_resilient.ps1'
foreach ($role in @('primary','backup')) {
  $name = "${TaskPrefix}_closer_$role"
  $argStr = "-NoProfile -ExecutionPolicy Bypass -File `"$wrapper`" -Config `"$cfgPath`" -Role $role"
  if ($DryRun) { $argStr += ' -DryRun' }
  $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argStr
  $principal = New-ScheduledTaskPrincipal -UserId $env:USERNAME -LogonType Interactive
  Register-ScheduledTask -TaskName $name -Action $action -Principal $principal -Force | Out-Null
  Start-ScheduledTask -TaskName $name
  $st = (Get-ScheduledTask -TaskName $name).State
  Write-Output "task=$name state=$st"
}
Write-Output "DUAL_ACTIVE_REGISTERED prefix=$TaskPrefix deadline_min=$DeadlineMin dryrun=$DryRun"
