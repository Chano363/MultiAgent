# Handoff：R0 车钩地基改进收官 —— A–E 落地/文献复核标定/归因实验/主实验全量重跑完成，剩余分层 platoon 线重训与论文数值更新待做

日期：2026-09-06 · 任务定位：**接手 agent 执行 R0（车钩/制动模型地基改进）的后续收尾**——代码与主实验已全部完成并双 commit，剩余为"受 R0 影响但未重训的实验线"与"论文/文档数值同步"。
前置阅读：本文件 → `docs/VALIDATION_BASELINE.md`「地基级建模体检 R0」节（SSOT）→ `docs/records/DIAGNOSTICS.md`（2026-09-06 R0 两节）→ 上一份 `HANDOFF_2026-09-06_ModelBasisReview.md`（R0 任务来源）→ `AGENTS.md`（Gotchas / 测试命令 / 研究定位）。

## 一句话现状

R0 五项（A 卸载刚度 / B Stribeck 摩擦 / C 机车 QKX100 分区 / D 循环衰减启用 / E 缓解排气两段式）已在 `coupler.py` 标量 + `train.py` 向量化**两处同步落地**，经于宗泽2025式(1)-(4)+李蔚2023表1 文献复核完成标定（**MT-2 u=1.0、τ=6.0s、QKX100 形状标定**），归因实验（fig3 循环制动 2266→1258 kN 落回四源实测带）驱动了两处标定修正；**171 项测试全绿**（新增 `test_coupler_model_refined.py` 18 项）；decompose 主实验（1+1 空电分离 3-seed）+ 双杠杆消融 + M0/单机基线 + MPC（3列车冒烟协议）+ 物理验证图全部在终版物理下重跑，**架构证据链全部保持**（M1 vs M0：车钩力 −22%、ATP −97%、末速 +22.8km/h）。

## 你要交付什么（接手后按优先级）

1. **分层 platoon 线全量重训重评**（最大缺口，见 §4.1）——第 1 层规则控速 MAPPO、M1/M3/M4/fair-DQN 的 3×1+0 模型均产出自 R0 前物理，`evaluate_m1_m3_long.py` 的 m1/m3/m4/mdqn_fair/fairmpc 模式目前**没有可用 checkpoint**（旧 ckpt 物理口径已作废）。
2. **ITSC 论文数值同步**（`docs/ITSC_PAPER.md/.tex`）：全文车钩力/奖励/对比表数字为 R0 前口径，须按 §3 汇总表 + VALIDATION_BASELINE R0 节改写，并补一段"建模版本声明"。
3. E4-H 车钩异构 held-out 评估在 R0 物理下重跑（`--hetero --hetero_seed 1000`，注意异构显式 couplers 优先于 QKX100 自动派发，见 §5 坑 6）。
4. 可选：MPC 完整 3000 步协议（本轮仅 300 步冒烟）、35/50km 剖面泛化线重跑、`plot_profile_validation.py` 文件名中文化。

## 1. 已完成（接手先确认在位，勿重做）

### 1.1 R0 五项实现 + 文献复核标定（commit `4a9b9bd`）

| # | 落地 | 标定值与依据 |
| :-: | :--- | :--- |
| A | `CouplerParams.unload_stiffness_ratio` 机制（标量+向量+异构抽样同步） | **MT-2 = 1.0**（于宗泽式(1) 加载/卸载共用同一 k，"卸载初期较小"是摩擦项翻转；经典分段构造数值恰对应 1.0）；QKX100 = 0.6。**HANDOFF 原建议 0.4 被归因实验否定**（+894kN 峰值膨胀破实测带） |
| B | `friction_static_n=750kN`(1.5×动) + `friction_v_er=0.2m/s` 线性过渡（式(2)） | 动摩擦 500kN 保留旧迟滞环锚（落锤 3.3m/s >> v_er） |
| C | `qkx100_params()`：月牙形两段刚度 k1=6e7>k2=2.14e7、2500kN@83mm、胶泥幂律阻尼 C\|v\|^0.55+F_d+f（式(3)(4)）；`TrainDynamics` 齐次默认按机车相邻耦合自动派发 | **C/n/F_d/f/k1/k2 为形状标定值**（文献只给结构+曲线形状，未给拟合常数——诚实边界已写入 docstring 与 VALIDATION_BASELINE） |
| D | `enable_cyclic_degrade` 默认 True（None→True）；official 显式 False 被拒（`simcase='debug'` 留消融）；`_OFFICIAL_LEGAL`/`PhysicsConfig` 同步 | 赵紫宁表5-5 C_β（首段=1.0 归一）；归因：D 使循环峰值 **−783kN** |
| E | 两段式缓解：波传播期（delay>0）满制动保持 → 波到达后 exp(−t/τ) 排风，frac≤0.02（≈4τ）彻底缓解 | **τ=6.0s** 按刘博阳 L1 拉钩力锚（742/1058/1337 → 1065/~1150/1281，带内单调）；τ 无文献解析值，标定边界已声明 |

### 1.2 归因实验（本轮方法论核心，防"参数拍脑袋"）

场景 = fig3 朔黄 23.8km 规则循环制动（1万吨 1+0，15000 步）。逐项关闭定位：初版(A0.4+B+D+Eτ4)=**2266** → −A=1372、−B=2177、−D=3049、−E=1881 → **终版(u1.0+B+D+τ6)=1258 kN**（旧物理 1141 的 +10%，带内）。τ 单独扫描（L1 场景）：1→2172、2→1714、4→1328、6→1065 kN——**非单调**（快排→前车脱开更快→拉钩力更大），勿想当然。

### 1.3 附带 bug 修复（顺带发现）

- **标量刚性限位 clip 不一致（存量）**：`coupler.py` 把刚性限位力与阻抗一起 clip，向量化版（2026-08-30 修复）封顶外独立叠加 → 已对齐，`test_vector_matches_scalar_both_buffer_types` 以 1e-9 锁定。
- **episode 状态残留**：`set_initial`/`set_initial_speed` 现复位 `_brake_segment/_brake_was_active/_air_brake_exhaust_t`（D 启用后段号跨 episode 累积会污染训练）。

### 1.4 测试与验证图

- 全量 `pytest tests/ -q` → **171 passed**（`outputs/logs_r0/pytest_final2.log`）。
- 新增 `tests/test_coupler_model_refined.py` 18 项：2270/2500 锚、月牙形割线单调、Stribeck 方向、小压缩量<MT-2、两处实现一致性、迟滞环耗能、排气指数衰减、**整段曲线跨工况核查**（R0.5：有界/无 NaN/S3 相位/能量守恒，随机 seed 参数化）。
- 物理图终版：`outputs/phys_validation/run_20260906_042552/`（fig1-7，fig3=1258kN/7段）+ `profiles_20260906_043017/`（35/50km 纵断面）。旧图目录保留未删（append-only）。

### 1.5 主实验全量重跑（commit `a504c66`，15000 步完整时域、best-checkpoint、3 评估 seed）

| 方法 | reward | 车钩力峰(kN) | viol | band率 | AB步 | meanED | 末速(km/h) | ATP事件 |
| :--- | ---: | ---: | :-: | ---: | ---: | ---: | ---: | ---: |
| **M1 seed0**（1+1 空电分离 RL） | **+74,530** | **554** | 0 | 99.99% | 3,170 | 0.12 | **63.6** | 1.44M |
| M1 seed1 / seed2 | +59,326 / +72,112 | 607 / 553 | 0/0 | 95.9%/99.99% | 4,083/0 | 0.04/0.74 | 51.9/40.2 | 1.44M |
| M0 规则基线 | +71,438 | 713 | 0 | 99.70% | 827 | 0.60 | 40.8 | 50.3M |
| 单机单控（旧架构 1+0） | −7,439 | 646 | 0 | 77.30% | 4,976 | 0 | 38.9 | 486M |
| 仅 ED 杠杆（mask_ab） | +72,014 | **546** | 0 | 100% | **0** | 0.73 | 51.6 | 1.44M |
| 仅 AB 杠杆（mask_ed） | +69,148 | 707 | 0 | 98.50% | 2,467 | 0.03 | 61.6 | 1.44M |
| MPC（mpc_rule，3列车，300步冒烟） | +4,813 | 583 | 0 | — | — | — | — | 0（**260.5ms/步 > 100ms 预算，Lim-2 保持**） |

- **结论保持**：架构链（单机→M0→M1）递进成立；M1 vs M0 = 车钩力 −22%、ATP −97%、末速 +22.8km/h、reward（seed0）+4.3%；消融机制保持（ED 杠杆=车钩力安全、AB 杠杆=吞吐）。**旧物理"仅 AB 杠杆 reward 反超双杠杆"的奖励设计异常消失**（+69.1k < M1 seed0 +74.5k）。
- 3-seed 训练 best：+73,602/+69,008/+71,345（旧 +73,733/+72,451/+71,944 同量级）——换基座不改可学性。
- 留痕：`outputs/results_decompose/eval_decompose_*_r0*.json`（含内嵌 metadata）、训练日志 `outputs/logs_r0/train_dec_*.log`、checkpoint `outputs/checkpoints_r0_dec{,_abl}/`。

## 2. 关键坑（新，勿重踩）

| 问题 | 解决 |
| :--- | :--- |
| **u=0.4（上份 HANDOFF 建议）破实测带** | 归因实验定标定值；任何"文献建议值"先过四源带门禁（D1/S4/L1 测试就是门禁） |
| **τ 缓解排气非单调** | 快排→前车脱开更快→拉钩力更大；扫 τ∈{1,2,4,6} 后按 L1 锚定 6.0 |
| **标量/向量化两处实现必须同步** | 一致性测试已锁定（1e-9）；改车钩先想"两处" |
| **official 治理已反转** | `enable_cyclic_degrade=False` 进 official 会抛异常；消融用 `simcase='debug'` |
| **5 训练并行时 OMP 线程超订阅** | 12 核机上每进程 `OMP_NUM_THREADS=2 MKL_NUM_THREADS=2`；否则 3 进程×12 线程互踩（曾误判为"训练变慢 60 倍"，实为日志每 10 ep 才打一行 + 线程争抢） |
| **E4-H 显式 couplers 优先于 QKX100 派发** | `hetero=True` 时逐钩抽样覆盖自动派发（货车异构研究域）；齐次默认才有机车 QKX100 分区 |
| **`pkill -f train_fleet` 会自杀** | 模式里用 `t[r]ain_fleet` 方括号技巧；`wsl -e bash -c` 内嵌套引号易碎，后台长任务写 .sh + `setsid nohup` |
| **评估 rollout 间 reset 不完全清动力学内部状态** | 旧 quirk 仍在：per_seed 后两个 seed 结果常完全相同；对比结论看均值即可，勿逐 seed 过度解读 |
| **best-checkpoint 协议** | stage-3 训练期平均 reward 为噪声（seed1 平均 −48k 但 best +69k）；评估一律 `--checkpoint *best*.pt` |
| **历史口径** | R0 前所有车钩力绝对值（训练产物/评估 JSON/fig3-6 数值）作废；引用须附建模版本声明（`docs/rules/EXECUTION_RULES.md`） |

## 3. 未完成 / 待做（按优先级）

### 3.1 分层 platoon 线全量重训重评（最大缺口，P1）

受影响模型（全部 R0 前物理产出）：第 1 层规则控速 MAPPO（`train_cyclic_braking.py`，L1 线）、M1/M3 共用第 2 层 MAPPO、M4、fair-DQN、CoorDQN。评估入口 `evaluate_m1_m3_long.py`（m1/m3/m4/mdqn_fair/fairmpc 模式）依赖这些 ckpt。建议顺序：

```sh
# ① 第 1 层重训（长，约数小时/seed）
python src/trainer/train_cyclic_braking.py --episodes 300 --grade shuozhou_23800
# ② 3 列 platoon M1 重训（3 seed，协议同 run_full_training_100pct_etcs_5seed.sh：200ep、curriculum 1000:66,3000:132、--hierarchical --adj_coef 0.1 --enable_etcs）
# ③ fair-DQN / CoorDQN 同理重训
# ④ evaluate_m1_m3_long.py 全模式重评（15000 步完整时域 + 35km 泛化线）
```

注意：R0 物理下单机单控基线 reward 转负（−7.4k、band 77.3%），分层线的绝对数会与论文旧表差异较大，**这是物理真实化而非回归**，论文叙事需重写对照基线段。

### 3.2 ITSC 论文数值同步（P1）

`docs/ITSC_PAPER.md/.tex` 全部车钩力/reward/对比表为 R0 前口径；git status 里 `ITSC_PAPER.tex` 有未提交改动（用户手工），改前先与用户确认。数值来源：本文件 §1.5 表 + `VALIDATION_BASELINE.md` R0 节 + `outputs/results_decompose/*_r0*.json`。需补"建模版本声明"段（R0 改版：Stribeck+QKX100+段间衰减+两段式缓解）。

### 3.3 E4-H 异构 held-out（P2）

```sh
python src/evaluation/evaluate_decompose.py --mode decompose_m1 \
  --checkpoint outputs/checkpoints_r0_dec/mappo_fleet_best_dec_ad2__cp_seed0.pt \
  --hetero --hetero_seed 1000 --n_seed 3 --max_steps 15000 --decision_interval 10 --out_suffix _r0_hetero
```

### 3.4 可选（P3）

- MPC 完整 3000 步协议（`--max_steps 3000`，逐步 SLSQP ~4h，Lim-2 数据 300 步版已够用）；
- 35km/50km 剖面泛化线在 R0 物理下重跑；
- `plot_profile_validation.py` 输出文件名中文化（与 fig1-7 一致）。

## 4. 命令与复现

```sh
cd /mnt/d/Code/MultiAgent/traffic_rl_project
source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
python -m pytest tests/ -q                                   # 171 passed
python src/evaluation/plot_physical_curves.py                # fig1-7（终版物理）
python src/evaluation/plot_profile_validation.py             # 纵断面 + 35/50km
# decompose 主实验（已完成，留档）
python src/trainer/train_fleet.py --episodes 60 --num_trains 1 --preset 10kt_1plus1 \
  --grade shuozhou_23800 --max_steps 15000 --curriculum 1000:0,3000:20,15000:40 \
  --init_speed_kmh 80 --entropy 0.002 --decompose loco_ed_ab --decision_interval 10 \
  --seed {0,1,2} --enable_etcs --checkpoint_dir outputs/checkpoints_r0_dec --results_dir outputs/results_r0_dec
# 评估（已完成，留档）
python src/evaluation/evaluate_decompose.py --mode all --checkpoint <best>.pt \
  --n_seed 3 --max_steps 15000 --decision_interval 10 --out_suffix _r0
# MPC（已完成，留档）
python src/evaluation/evaluate_m1_m3_long.py mpc_rule --etcs --num_trains 3 --max_steps 300 --grade shuozhou_23800 --n_seed 1
```

## 5. 权威出处（数据/判据 SSOT）

- R0 标定与历史口径：`docs/VALIDATION_BASELINE.md`「地基级建模体检 R0」节（2026-09-06）
- 重跑汇总表：`docs/records/DIAGNOSTICS.md` 2026-09-06 R0 两节
- 文献：`docs/papers/重载列车车钩缓冲装置纵向动力学精细化模型_于宗泽.pdf`（式(1)-(4)、图4/7/9）、`重载组合列车纵向力优化的联合制动分析及研究_李蔚.pdf`（表1：QKX100 2500kN / MT-2 2270kN / 行程 83mm）、`Zhao2022`（表5-5 C_β）、`刘博阳2022`（L1 拉钩力锚）
- 测试门禁：`tests/test_coupler_model_refined.py`（18 项）+ `tests/test_field_benchmarks.py`（D1/S3/S4/L1）
- 决策：`docs/records/DECISIONS.md`（ADR-009/010）；commits `4a9b9bd`（模型改版）、`a504c66`（重跑汇总）
