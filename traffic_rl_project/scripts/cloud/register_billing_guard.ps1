# Register the ALWAYS-ON billing guard: pure-API (zero ssh) hard stop at an absolute deadline.
# 2026-11-20 added after closer dual-active died (Triggers=0 + Interactive logon + no restart):
# even if EVERY ssh-based closer dies, this task runs every 10 min and force-stops the instance
# at the deadline via DescribeInstances/StopInstance. No ssh / no long-lived wrapper to die.
#
# Usage (PowerShell):
#   powershell -NoProfile -ExecutionPolicy Bypass -File register_billing_guard.ps1 `
#     -Instance i-xxxx -StopAfter '2026-11-20T18:11' -RunTag w4xxx
# -StopAfter MUST use ISO 'T' (no space) - argument-splitting hazard (SERVER_OPS section 15).
param(
  [Parameter(Mandatory=$true)][string]$Instance,
  [Parameter(Mandatory=$true)][string]$StopAfter,
  [Parameter(Mandatory=$true)][string]$RunTag,
  [string]$Region = 'cn-heyuan',
  [string]$TaskPrefix = 'billing_guard'
)
$base = 'D:\Code\MultiAgent\traffic_rl_project'
$py = 'D:\Anaconda\python.exe'
$guard = Join-Path $base 'scripts\cloud\billing_guard.py'
$logDir = Join-Path $base 'outputs\logs\cloud'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null
$selfLog = Join-Path $logDir "billing_guard_${RunTag}.log"
$name = "${TaskPrefix}_${RunTag}"

# Validate ISO format (T separator, no space) before registering.
if ($StopAfter -notmatch '^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$') {
  throw "StopAfter must be ISO 'YYYY-MM-DDTHH:MM' (no space): got '$StopAfter'"
}
$deadline = [datetime]::ParseExact($StopAfter, 'yyyy-MM-ddTHH:mm', $null)

$argStr = "-NoProfile -ExecutionPolicy Bypass -File `"$guard`" --instance $Instance --region $Region --stop-after $StopAfter --self-log `"$selfLog`""
$action = New-ScheduledTaskAction -Execute $py -Argument $argStr
$repInterval = New-TimeSpan -Minutes 10
$repDuration = New-TimeSpan -Days 3
$startAt = $deadline.AddMinutes(-10)
$trigger = New-ScheduledTaskTrigger -Once -At $startAt -RepetitionInterval $repInterval -RepetitionDuration $repDuration
$execLimit = New-TimeSpan -Minutes 5
# 2026-11-20 FIX: same battery/restart hardening as register_closer_pair.ps1 - the
# ultimate backstop must never be stopped by a battery switch or a missed trigger.
$settings = New-ScheduledTaskSettingsSet -MultipleInstances IgnoreNew -ExecutionTimeLimit $execLimit -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -RestartCount 3 -RestartInterval (New-TimeSpan -Minutes 1)

# Prefer SYSTEM (no session dependency); fall back to current-user Interactive if the
# session lacks privilege (non-admin). Both are pure-API short processes, every 10 min.
$mode = 'Interactive'
try {
  $principal = New-ScheduledTaskPrincipal -UserId 'SYSTEM' -LogonType ServiceAccount -RunLevel Highest
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null
  $mode = 'SYSTEM'
} catch {
  Write-Output "SYSTEM register unavailable ($($_.Exception.Message)) -> fallback Interactive"
  $principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive
  Register-ScheduledTask -TaskName $name -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null
}
Start-ScheduledTask -TaskName $name
$t = Get-ScheduledTask -TaskName $name
Write-Output "BILLING_GUARD_REGISTERED task=$name state=$($t.State) logon=$mode triggers=$($t.Triggers.Count) stop_after=$StopAfter log=$selfLog"
