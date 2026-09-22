# deprecated/ 历史资产归档（2026-09-22 outputs 整理）

> 本目录集中收纳 **历史物理版本 / 已废弃 / 已完成使命** 的产物，**仅供回溯，论文禁止引用**。
> 引用任何资产前，先核对 `README_legacy_artifacts.md`（outputs 根）的物理版本判定与 metadata。
> 物理版本风险要点：Newmark 欠松弛修复（2026-09-02 前≈75% 动力学）、缓解波建模变更、decompose 架构切换（ADR-009，2026-09-05）。

## 内容一览

| 子目录/文件 | 内容 | 状态 |
| :--- | :--- | :--- |
| `_no_metadata_staging/` | 旧物理 checkpoints_*（含内部 deprecated_results） | ⚠️ 无 metadata，论文禁引 |
| `checkpoints_formation_53km/` | 53km 早期训练/评估日志 | 已被现役 checkpoints_formation 取代 |
| `diag_53km_*/`（14 个目录） | 53km curriculum/nenv 系列诊断实验 | 历史诊断留痕 |
| `logs/` `logs_r0/` | 早期训练日志（mdqn/w1/r0 链） | 历史 |
| `deploy/` | 部署杂项（旧 mappo_best_ep430） | 非现役部署 |
| `results/` `results_100pct*/` `results_phys2/` `results_full/` `results_ad2/` `results_ad2g/` `results_cyclic_phys2/` | 历史评估产物 | ⚠️ 物理版本混杂 |
| `results_r0_*` | R0 阶段 decompose/l1 评估 | 已被现役取代 |
| `scripts/` | 顶层历史脚本（*.sh 除现役 launch_final_5seed_parallel.sh） | 已完成使命 |
| `logs_txt/` | 顶层历史日志/文本（*.log *.txt） | 历史 |
| `data/` | 顶层历史数据（*.csv *.json 诊断） | 历史 |
| `reorganize_outputs.ps1` | 本次整理脚本（迁移清单留痕） | 一次性 |

## 现役保留（不在本目录）

- `training_results/` — 现役训练结果（模型/图像/metadata/评估JSON）：figures、train_logs、mt2_l1、abl_*、results_dec_full_iv10
- `sim_validation/` — 仿真器数据图表：phys_validation、diagnostics、coupler_param_scan、trace_*
- `checkpoints_formation/`（含 final_seed0-4 现役长训）— 迁移待训练/评估全部完成后执行
- `results_decompose/` — 现役评估（含进行中的 53km/35km 4 个任务）
- `logs_final_parallel/` — 现役 5-seed 长训逐 seed 日志
- 顶层 `launch_final_5seed_parallel.sh`（现役驱动）、`reorganize_log.txt`（本次整理清单）

> ⚠️ 训练完成后的待办：把 `checkpoints_formation/final_seed{0,2,3,4}`（seed1 保留原位）等现役产物并入 `training_results/` 对应结构，并更新本 README。

### 2026-09-22 二轮归档（历史资产集中收敛）

按用户指示"所有历史资产收进 deprecated，其余目录只保留最新结果"，新增迁移：

| 新子目录 | 来源 | 归档内容 |
| :--- | :--- | :--- |
| `sim_validation_hist/` | `outputs/sim_validation/` | 全部旧 run/profiles 验证数据、`trace_*` 诊断轨迹、coupler_param_scan、diagnostics（保留最新 `phys_validation/run_20260907_192050`） |
| `training_results_hist/` | `outputs/training_results/` | `mt2_l1/`（旧 L1 循环制动模型）、`train_logs/`（166 个历史训练日志） |
| `checkpoints_formation_hist/` | `outputs/checkpoints_formation/` | 全部旧 seed 目录（seed0-4、DIVERGED*、_smoke*、valid_* 等）与历史日志/脚本（仅保留 `final_seed0-4` 现役长训） |
| `results_decompose_hist/` | `outputs/results_decompose/` | 旧 15000 步 / R0 / rand / iv5/20 / abl 消融评估 JSON（保留最新 best/last/ep841/mpc 评估） |

> 现役保留（本目录之外）：`sim_validation/{figures, phys_validation/run_20260907_192050}`、`training_results/{figures, results_dec_full_iv10, abl_*}`、`checkpoints_formation/final_seed{0..4}`、`results_decompose/`（13 个最新评估 JSON）、`logs_final_parallel/`。
