#!/usr/bin/env pwsh
# outputs 整理（2026-09-22）：
#   目标结构: training_results/（训练结果:模型/图像/metadata/评估JSON）
#             sim_validation/（仿真器数据图表）
#             deprecated/（历史/废弃资产，仅回溯）
#   跳过活跃目录: final_seed0/1（训练在写）、results_decompose（评估在写）、logs_final_parallel（在写）
$ErrorActionPreference = 'Stop'
$root = 'd:\Code\MultiAgent\traffic_rl_project\outputs'
Set-Location $root

# ---- 1. 骨架 ----
foreach ($d in 'training_results','sim_validation','deprecated') { New-Item -ItemType Directory -Path $d -Force | Out-Null }

$log = @()

# ---- 2. sim_validation/（仿真器数据图表：物理验证锚/诊断/trace/扫描） ----
$sim_dirs = @('phys_validation','diagnostics','coupler_param_scan','trace_53km_realgap_short','trace_53km_rule','trace_53km_rule_etcs_ab','trace_53km_rule_etcs_ab_full','trace_53km_rule_etcs_diag','trace_53km_rule_etcs_fix','trace_53km_rule_etcs_on','trace_53km_rule_realgap','trace_acc_3000','trace_c3','trace_sync_probe')
foreach ($d in $sim_dirs) {
  if (Test-Path $d) { Move-Item -Path $d -Destination "sim_validation/$d"; $log += "sim_validation: $d" }
}

# ---- 3. training_results/（现役非活跃训练产物） ----
$tr_dirs = @('figures','train_logs','mt2_l1','abl_checkpoints','abl_results','results_dec_full_iv10')
foreach ($d in $tr_dirs) {
  if (Test-Path $d) { Move-Item -Path $d -Destination "training_results/$d"; $log += "training_results: $d" }
}
# 顶层散落的 train_*.log 移入 training_results/train_logs/
Get-ChildItem -File -Filter 'train_*.log' | ForEach-Object { Move-Item $_.FullName "training_results/train_logs/"; $log += "training_results/train_logs: $($_.Name)" }
Get-ChildItem -File -Filter 'checkpoints_formation_seed0.log' | ForEach-Object { Move-Item $_.FullName "training_results/train_logs/"; $log += "training_results/train_logs: $($_.Name)" }

# ---- 4. deprecated/（历史/废弃） ----
$dep_dirs = @('_no_metadata_staging','checkpoints_formation_53km','diag_53km_abgate','diag_53km_anneal','diag_53km_bc','diag_53km_bcsmoke','diag_53km_coupler_pen','diag_53km_divergence','diag_53km_nenv','diag_53km_nenv_smoke','diag_53km_p1_bcnenv_curric','diag_53km_p2_curric1500','diag_53km_p3_curric1200','diag_53km_relanchor','diag_53km_rollback','logs','logs_r0','deploy','results','results_100pct','results_100pct_etcs','results_ad2','results_ad2g','results_cyclic_phys2','results_full','results_phys2','results_r0_dec','results_r0_dec_abl','results_r0_l1','results_r0_platoon_m1')
foreach ($d in $dep_dirs) {
  if (Test-Path $d) { Move-Item -Path $d -Destination "deprecated/$d"; $log += "deprecated: $d" }
}

# ---- 5. 顶层散落历史脚本/日志/数据 分类归档 ----
# 5a. 历史脚本(.sh/.ps1) → deprecated/scripts/
New-Item -ItemType Directory -Path 'deprecated/scripts' -Force | Out-Null
Get-ChildItem -File | Where-Object { $_.Extension -in '.sh','.ps1' -and $_.Name -ne 'launch_final_5seed_parallel.sh' } | ForEach-Object {
  Move-Item $_.FullName 'deprecated/scripts/'; $log += "deprecated/scripts: $($_.Name)" }

# 5b. 历史日志(.log/.txt) → deprecated/logs_txt/
New-Item -ItemType Directory -Path 'deprecated/logs_txt' -Force | Out-Null
Get-ChildItem -File | Where-Object { $_.Extension -in '.log','.txt' } | ForEach-Object {
  Move-Item $_.FullName 'deprecated/logs_txt/'; $log += "deprecated/logs_txt: $($_.Name)" }

# 5c. 历史数据(.csv/.json/.md 除 README) → deprecated/data/
New-Item -ItemType Directory -Path 'deprecated/data' -Force | Out-Null
Get-ChildItem -File | Where-Object { $_.Extension -in '.csv','.json' } | ForEach-Object {
  Move-Item $_.FullName 'deprecated/data/'; $log += "deprecated/data: $($_.Name)" }

# ---- 汇总 ----
"=== 迁移清单 ($($log.Count) 项) ===" | Out-File reorganize_log.txt -Encoding utf8
$log | Out-File reorganize_log.txt -Append -Encoding utf8
Write-Output "迁移完成，清单见 outputs/reorganize_log.txt（共 $($log.Count) 项）"