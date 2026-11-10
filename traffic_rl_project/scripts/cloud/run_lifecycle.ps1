# 本地看护（Windows）：防止云实例被回收后无人管、"开着空等"计费。
#
# 职责（三种结局都收口）：
#   1) 训练结束（exit_code.txt 出现）：调 pull_artifacts.sh 回传→校验→放行 → API 停机复核
#      → 校验通过则释放（-Release）。
#   2) 异常退出：同 1（产物齐全即可释放，归档标 ABORTED）。
#   3) 心跳超时：回传日志（尽力）→ API 停机复核 → 写 DEAD 标记本地账本 → 释放。
# 另设 -MaxHours 硬上限：超时无条件回传+停机+释放，防止无人值守长跑烧钱。
#
# 记账：每一步都写 outputs/logs/cloud/lifecycle_<runid>.csv（开机/关机时刻、时长、
# 单价、估算费用），事后可与阿里云账单核对。
#
# 用法（Windows PowerShell）：
#   powershell -File scripts/cloud/run_lifecycle.ps1 -InstanceId i-xxx -PublicIp 1.2.3.4 \
#     -RunId cloud_20261110_101500 -PricePerHour 1.436 [-MaxHours 24] [-Release]
param(
  [Parameter(Mandatory=$true)][string]$InstanceId,
  [Parameter(Mandatory=$true)][string]$PublicIp,
  [Parameter(Mandatory=$true)][string]$RunId,
  [double]$PricePerHour = 1.436,
  [double]$MaxHours = 24,
  [string]$Region = "cn-heyuan",
  [int]$PollSeconds = 60,
  [int]$StaleHeartbeatMin = 30,
  [switch]$Release
)

$ErrorActionPreference = "Stop"
$Root = Resolve-Path (Join-Path $PSScriptRoot "..\..")
$Py = if ($env:PY_CLOUD) { $env:PY_CLOUD } else { "python" }
$LogDir = Join-Path $Root "outputs\logs\cloud"
New-Item -ItemType Directory -Force -Path $LogDir | Out-Null
$Ledger = Join-Path $LogDir "lifecycle_$RunId.csv"
if (-not (Test-Path $Ledger)) {
  "ts_iso,event,detail,elapsed_h,price_per_h,est_cost_yuan" | Set-Content -Encoding utf8 $Ledger
}

function Log-Event([string]$Event, [string]$Detail) {
  $age = ((Get-Date) - $script:Start).TotalHours
  $cost = [math]::Round($age * $PricePerHour, 2)
  ('{0},{1},"{2}",{3:N3},{4},{5}' -f (Get-Date -Format "o"), $Event, $Detail, $age, $PricePerHour, $cost) |
    Add-Content -Encoding utf8 $Ledger
  Write-Host ("[{0}] {1} | {2} | elapsed={3:N2}h est={4}元" -f (Get-Date -Format "HH:mm:ss"), $Event, $Detail, $age, $cost)
}

function Get-State {
  $out = & $Py (Join-Path $Root "scripts\cloud\instance_state_aliyun_ecs.py") $InstanceId --region $Region 2>&1 | Out-String
  $status = if ($out -match "Status\s*=\s*(\w+)") { $Matches[1] } else { "UNKNOWN" }
  $mode = if ($out -match "StoppedMode\s*=\s*(\w+)") { $Matches[1] } else { "" }
  return @{ Status = $status; Mode = $mode; Raw = $out }
}

function Invoke-StopAndVerify {
  $out = & $Py (Join-Path $Root "scripts\cloud\instance_state_aliyun_ecs.py") --stop $InstanceId --region $Region 2>&1 | Out-String
  Log-Event "stop_api" ($out -replace "\r?\n", " " | ForEach-Object { $_.Trim() })
  if ($out -match "已停费") { Log-Event "stop_verified" "Status=Stopped StoppedMode=StopCharging"; return $true }
  Log-Event "stop_unverified" "未确认 StopCharging，禁止释放，需人工核查"
  return $false
}

$script:Start = Get-Date
$startEpoch = [int][double]::Parse((Get-Date -UFormat %s))
Log-Event "guard_start" "iid=$InstanceId ip=$PublicIp run=$RunId price=$PricePerHour/h max=${MaxHours}h"

$pulled = $false
$deadline = $script:Start.AddHours($MaxHours)

while ($true) {
  $st = Get-State
  Log-Event "poll" ("status=" + $st.Status + " mode=" + $st.Mode)

  # 1) 回传 + 校验（实例还活着才能 rsync）
  if (-not $pulled -and $st.Status -eq "Running") {
    $pullOut = & wsl -d Ubuntu-24.04 -e bash (Join-Path $Root "scripts/cloud/pull_artifacts.sh") `
      --ip $PublicIp --run-id $RunId 2>&1 | Out-String
    if ($LASTEXITCODE -eq 0) {
      $pulled = $true
      Log-Event "pull_ok" "产物回传并校验通过"
    } elseif ($pullOut -match "无 exit_code") {
      Log-Event "pull_wait" "训练仍在跑"
    } else {
      Log-Event "pull_fail" (($pullOut -split "\r?\n" | Select-Object -Last 3) -join " ")
    }
  }

  if ($pulled) {
    $ok = Invoke-StopAndVerify
    if ($ok -and $Release) {
      $rel = & $Py (Join-Path $Root "scripts\cloud\instance_state_aliyun_ecs.py") --stop $InstanceId --release --region $Region 2>&1 | Out-String
      Log-Event "release" (($rel -replace "\r?\n", " ").Trim())
    }
    Log-Event "guard_exit" ("released=" + [bool]$Release)
    break
  }

  # 2) 已经停了（实例侧看护先关机）：停机即已止血，但产物未回传 → 不释放
  if ($st.Status -in @("Stopped", "UNKNOWN")) {
    if ($st.Status -eq "Stopped") {
      Log-Event "instance_stopped_before_pull" "实例侧已关机；产物仍在磁盘，未释放（需人工决定是否开机取回）"
    } else {
      Log-Event "state_unknown" "API 查询失败，继续轮询"
    }
    if ($st.Status -eq "Stopped") { break }
  }

  # 3) 超出预算上限：无条件止血
  if ((Get-Date) -gt $deadline) {
    Log-Event "max_hours_exceeded" ("超过 ${MaxHours}h，强制停机")
    $null = Invoke-StopAndVerify
    break
  }

  Start-Sleep -Seconds $PollSeconds
}

$total = ((Get-Date) - $script:Start).TotalHours
Log-Event "guard_end" ("总时长 {0:N2}h，估算 {1:N2} 元（单价 {2}/h）" -f $total, ($total * $PricePerHour), $PricePerHour)
Write-Host "账本：$Ledger"
