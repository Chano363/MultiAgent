# outputs/ 资产物理版本索引（2026-09-06 治理补录）

> 用途：标注各产物目录的**物理版本状态**，引用前必读。物理版本判定依据：
> Newmark 欠松弛修复（2026-09-02，修复前≈75% 动力学）、缓解波建模变更、decompose 架构切换（ADR-009，2026-09-05）。
> 规范：`project_constraint.md` §三（引用前核对物理工况版本）；废弃产物已隔离至 `deprecated_results/`。

## ✅ 当前物理（可论文引用，仍须核对 metadata/物理哈希）

| 目录                                    | 内容                                            | 物理版本           |
| :------------------------------------ | :-------------------------------------------- | :------------- |
| `checkpoints_dec_full_iv10/`          | decompose 终版 3-seed（seed0/1/2 best + ep10-60） | 当前物理 + iv10 ✔ |
| `results_dec_full_iv10/`              | 对应训练历史 JSON/CSV                               | 当前物理 ✔        |
| `results_decompose/`                  | 15000 步评估 + 3-seed best 评估 + AB/ED 消融          | 当前物理 ✔        |
| `abl_checkpoints/` `abl_results/`     | 杠杆隔离消融（mask_ed / mask_ab）训练                    | 当前物理 ✔        |
| `deprecated_results/`                 | 废弃产物集中区（pre-release-fix、smoke）                 | **论文禁止引用**     |

## ⚠️ 历史物理（仅回溯，论文引用前须重跑或标 superseded）

| 目录                                                              | 所属架构/时期                                   | 物理版本风险                          |
| :-------------------------------------------------------------- | :--------------------------------------- | :------------------------------ |
| `checkpoints/` `checkpoints_full/` `results_full/`              | 早期 fleet 阈值协同（checkpoints\_mappo\_fleet\_*） | ⚠️ 无物理版本标注，可能含 Newmark 修复前产物     |
| `checkpoints_100pct*/`（\_etcs/\_ad2/\_ad2g/\_full/\_smooth/\_vcoop） | 2026-08-23 论文冲刺期（M1/M3/DQN-fair 等）        | ⚠️ Newmark 修复前/缓解波建模变更前          |
| `results_100pct/` `results_100pct_etcs/`                        | 同上评估产物                                    | ⚠️ 同上                          |
| `checkpoints_phys2*/`（\_cur/\_warm） `results_phys2/` `results_cyclic_phys2/` | 物理对齐 phys2 重训期（2026-08-26 前后）             | ⚠️ 缓解波建模变更前后混杂，逐 checkpoint 核对    |
| `checkpoints_dec_3seed_archive/`                                | decompose 早期 3-seed 存档                     | ⚠️ release-fix 前，已被 iv10 目录取代     |
| `results_ad2/` `results_ad2g/`                                  | 旧 ad2/ad2g 训练评估                           | ⚠️ 同上                          |
| `phys_validation/`                                              | 物理验证曲线（大体积，未入库）                           | 产物本身是验证锚，与架构无关                  |
| `logs/` `train_logs/` `results/` `diagnostics/` `figures/`       | 日志/诊断/图表                                  | 引用具体数值时以 JSON/CSV + metadata 为准 |
| `deploy/`                                                       | 部署杂项                                      | 非实验产物                           |

## 规则

1. **论文表格数值**只允许来自 ✅ 区（当前物理）+ metadata 物理哈希核对一致。
2. ⚠️ 区资产要升级为可引用：在当前物理上重跑，或标注 `superseded` 并说明差异来源。
3. 新产物目录名必须携带物理/架构版本标识（如 `_iv10`），禁止产生新的无标注目录。
