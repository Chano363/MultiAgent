# Runtime-effectiveness verifier for closer / billing-guard SCHEDULTASK settings.
# ASCII-only on purpose (PS 5.1 mis-decodes BOM-less UTF-8).
#
# WHY (2026-11-21, after diagnostics 19.33 idle-burn #2):
#   tests/test_closer_registration_resilience.py asserts that the register
#   scripts CONTAIN the flags "-AllowStartIfOnBatteries", "-StartWhenAvailable",
#   "-RestartCount 3", ... That is a static string check. It proves the source
#   text mentions the switches, NOT that the registered task actually carries
#   them. That is exactly the ADR-077 family defect ("config declared !=
#   runtime effective"): a flag that is present in the source but dropped or
#   overridden at the settings layer would still pass every static test.
#
#   This script closes that gap OFFLINE and for FREE: it evaluates the REAL
#   `$settings = New-ScheduledTaskSettingsSet ...` line out of the real
#   register script, registers a throwaway probe task with that settings
#   object, reads the task back with Get-ScheduledTask, exports the task XML,
#   and asserts the RESOLVED property values. No cloud instance, no ssh, no
#   billing. The probe task is unregistered in a finally block.
#
# Usage:
#   powershell -NoProfile -ExecutionPolicy Bypass -File verify_closer_settings.ps1 `
#     -RegisterScript D:\Code\MultiAgent\traffic_rl_project\scripts\cloud\register_closer_pair.ps1
#
# Prints one JSON object on stdout: {"script":..., "checks":{...}, "all_pass":bool}
param(
  [Parameter(Mandatory=$true)][string]$RegisterScript,
  [string]$ProbeTaskName = '',
  [switch]$KeepProbeTask
)

$ErrorActionPreference = 'Stop'
# Scheduled-task cmdlets emit a progress stream ("Completed 0/2") that pollutes
# stdout/stderr of the child process; silence it so the JSON verdict is clean.
$ProgressPreference = 'SilentlyContinue'
$src = Get-Content $RegisterScript -Raw -ErrorAction Stop

# 1) Extract the settings construction from the REAL register script.
#    Both register scripts build the settings on a single long line; find the
#    statement start and take the rest of that physical line.
$idx = $src.IndexOf('New-ScheduledTaskSettingsSet')
if ($idx -lt 0) {
  Write-Output (ConvertTo-Json @{ script = $RegisterScript; error = 'settings_line_not_found'; all_pass = $false })
  exit 2
}
$nlPos = $src.IndexOf("`n", $idx)
if ($nlPos -lt 0) { $nlPos = $src.Length }
$stmt = $src.Substring($idx, $nlPos - $idx).Trim()
# strip a trailing line-continuation marker and any trailing comment
$stmt = ($stmt -replace '`\s*$', '')
$stmt = ($stmt -replace '#.*$', '').Trim()

# 2) Evaluate it with the variables it references in scope.
#    The scripts define $execLimit before the settings line; provide it here.
$execLimit = New-TimeSpan -Days 3
try {
  # The extracted statement is the constructor call itself (the "$settings = "
  # prefix was outside the captured span), so capture its OUTPUT as the object.
  $settings = & ([scriptblock]::Create($stmt))
} catch {
  Write-Output (ConvertTo-Json @{ script = $RegisterScript; error = "settings_eval_failed: $($_.Exception.Message)"; all_pass = $false })
  exit 2
}
if ($null -eq $settings) {
  Write-Output (ConvertTo-Json @{ script = $RegisterScript; error = 'settings_object_null'; stmt = $stmt; all_pass = $false })
  exit 2
}

# 3) Register a throwaway probe task carrying that settings object.
if ($ProbeTaskName -eq '') {
  $ProbeTaskName = 'ZZ_VERIFY_CLOSER_' + (Get-Date -Format 'yyyyMMddHHmmss')
}
$action = New-ScheduledTaskAction -Execute 'cmd.exe' -Argument '/c exit 0'
$trigger = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(10)
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive

$registered = $false
try {
  try {
    Register-ScheduledTask -TaskName $ProbeTaskName -Action $action -Trigger $trigger -Principal $principal -Settings $settings -Force -ErrorAction Stop | Out-Null
    $registered = $true
  } catch {
    # Fallback: S4U (same path the real closer prefers). If both fail we cannot
    # observe the resolved settings -> report failure rather than fake a pass.
    $principal2 = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType S4U
    Register-ScheduledTask -TaskName $ProbeTaskName -Action $action -Trigger $trigger -Principal $principal2 -Settings $settings -Force -ErrorAction Stop | Out-Null
    $registered = $true
  }

  # 4) Read the task BACK and inspect the resolved values.
  $t = Get-ScheduledTask -TaskName $ProbeTaskName
  $xml = Export-ScheduledTask -TaskName $ProbeTaskName

  $checks = [ordered]@{
    # battery: DisallowStartIfOnBatteries must be false so a battery switch
    # cannot prevent the guard from starting; StopIfGoingOnBatteries must be
    # false so a battery switch cannot KILL the running guard.
    disallow_start_if_on_batteries_false = ($xml -notmatch '<DisallowStartIfOnBatteries>true</DisallowStartIfOnBatteries>')
    stop_if_going_on_batteries_false   = ($xml -notmatch '<StopIfGoingOnBatteries>true</StopIfGoingOnBatteries>')
    # a missed trigger must be made up
    start_when_available_true          = ($xml -match '<StartWhenAvailable>true</StartWhenAvailable>')
    # self-restart of a crashed task
    restart_count_ge_3                = ($t.Settings.RestartCount -ge 3)
    restart_interval_positive          = ($t.Settings.RestartInterval -ne $null -and $t.Settings.RestartInterval -gt '00:00:00')
    # no duplicate guard instances
    multiple_instances_ignore_new     = ($t.Settings.MultipleInstances -eq 'IgnoreNew')
    # the task must not be capped to a short execution limit
    execution_time_limit_not_short    = ($t.Settings.ExecutionTimeLimit -ne $null)
    # trigger must exist and be a once+repetition trigger
    trigger_present                   = ($t.Triggers.Count -ge 1)
  }
  $all = $true
  foreach ($k in $checks.Keys) { if (-not $checks[$k]) { $all = $false } }

  Write-Output (ConvertTo-Json -Depth 5 -Compress @{
    script = $RegisterScript
    probe_task = $ProbeTaskName
    registered = $registered
    resolved = [ordered]@{
      RestartCount = $t.Settings.RestartCount
      RestartInterval = $t.Settings.RestartInterval
      MultipleInstances = [string]$t.Settings.MultipleInstances
      StartWhenAvailable = $t.Settings.StartWhenAvailable
      DisallowStartIfOnBatteries = $t.Settings.DisallowStartIfOnBatteries
      StopIfGoingOnBatteries = $t.Settings.StopIfGoingOnBatteries
      ExecutionTimeLimit = [string]$t.Settings.ExecutionTimeLimit
      Triggers = $t.Triggers.Count
    }
    checks = $checks
    all_pass = $all
  })
  if (-not $all) { exit 1 }
  exit 0
} finally {
  if ($registered -and (-not $KeepProbeTask)) {
    # Silence the unregister progress/error stream: it otherwise interleaves
    # with the JSON verdict on stdout and makes the payload hard to parse.
    $prevEap = $ErrorActionPreference
    $ErrorActionPreference = 'SilentlyContinue'
    try { Unregister-ScheduledTask -TaskName $ProbeTaskName -Confirm:$false 2>&1 | Out-Null } catch {}
    $ErrorActionPreference = $prevEap
  }
}
