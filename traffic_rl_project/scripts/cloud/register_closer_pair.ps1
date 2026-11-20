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
# Closer configs are operational artifacts, not a new outputs/ first-level category.
# They live under the registered logs/ tree (EXECUTION_RULES output-layout R1 and section 1) which is
# gitignored, so instance ids and IPs never enter git. Never create outputs\configs here.
$cfgDir = Join-Path $base 'outputs\logs\cloud'; New-Item -ItemType Directory -Force -Path $cfgDir | Out-Null
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
  # NOTE (2026-11-19): quick-eval results live in results/decompose/ (file name
  # contains run_tag), while training products live in results/formation_.../<run_tag>/.
  # A single glob missed the quick-eval JSON (pilot: not pulled back) => two globs.
  pull_glob     = @("$remoteRoot/results/formation_10kt_1plus108/$RunTag/*", "$remoteRoot/results/decompose/*${RunTag}*")
}
$cfgJson = $cfg | ConvertTo-Json -Depth 5
# UTF-8 WITHOUT BOM: schtasks readers use PowerShell, but python json.load must also work.
[System.IO.File]::WriteAllText($cfgPath, $cfgJson, (New-Object System.Text.UTF8Encoding($false)))
Write-Output "config=$cfgPath"

$wrapper = Join-Path $base 'scripts\cloud\closer_wrapper_resilient.ps1'
# 2026-11-20 FIX (idle-burn root cause): old Register-ScheduledTask had no -Trigger and
# used Interactive logon => once the wrapper process died with the interactive session,
# the task stayed Ready forever and self-heal never happened (4 historical closers all Ready).
# Fix = 3 things: (1) 5min repetition trigger (re-launches a dead wrapper within 5min,
# recomputing remaining deadline so the billing window never extends);
# (2) MultipleInstances=IgnoreNew (no duplicate python while one is running);
# (3) try S4U logon, fall back to Interactive+trigger if not permitted.
# Ultimate backstop: register_billing_guard.ps1 (pure API, hard stop at absolute deadline).
# NOTE: keep this file ASCII-only - PS 5.1 mis-decodes BOM-less UTF-8 and breaks parsing.
$repInterval = New-TimeSpan -Minutes 5
$repDuration = New-TimeSpan -Days 3
$startAt = (Get-Date).AddSeconds(10)
$trigger = New-ScheduledTaskTrigger -Once -At $startAt -RepetitionInterval $repInterval -RepetitionDuration $repDuration
$execLimit = New-TimeSpan -Days 3
# 2026-11-20 FIX #2 (second idle-burn incident): the closer pair was terminated at
# 19:53:21 (LastTaskResult=0x800703E3, NumberOfMissedRuns=3) while the window was
# still training -> abort-glob never fired, nothing stopped the instance by itself.
# Settings-level causes addressed here:
#   - DisallowStartIfOnBatteries / StopIfGoingOnBatteries default TRUE: switching to
#     battery STOPS the running task. -AllowStartIfOnBatteries turns the first off,
#     -DontStopIfGoingOnBatteries turns the second off (verified: it is the only
#     switch that actually sets StopIfGoingOnBatteries=False).
#   - StartWhenAvailable default FALSE: a missed trigger was never made up.
#   - RestartCount default 0: the task had no self-restart; it depended on triggers only.
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit $execLimit -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)
foreach ($role in @('primary','backup')) {
  $name = "${TaskPrefix}_closer_$role"
  $argStr = "-NoProfile -ExecutionPolicy Bypass -File `"$wrapper`" -Config `"$cfgPath`" -Role $role"
  if ($DryRun) { $argStr += ' -DryRun' }
  $action = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument $argStr
  # S4U needs SeBatchLogonRight: a non-admin session can create the principal object,
  # but Register fails with access denied. Wrap the Register itself in try, fall back
  # to Interactive+trigger. Both modes carry the 5min trigger (the core of this fix).
  $mode = 'Interactive+trigger'
  try {
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null
    $mode = 'S4U'
  } catch {
    Write-Output "S4U register unavailable ($($_.Exception.Message)) -> fallback Interactive+trigger"
    $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
    Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null
  }
  Start-ScheduledTask -TaskName $name
  $st = (Get-ScheduledTask -TaskName $name).State
  Write-Output "task=$name state=$st logon=$mode triggers=$((Get-ScheduledTask -TaskName $name).Triggers.Count)"
}
Write-Output "DUAL_ACTIVE_REGISTERED prefix=$TaskPrefix deadline_min=$DeadlineMin dryrun=$DryRun (5min-trigger + IgnoreNew + self-heal)"
