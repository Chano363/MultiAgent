# 可复现性说明（ITSC 2026 投稿附）

> 本文档汇总论文 `ITSC_PAPER.md/.tex` 所有实验的确切运行命令、随机种子、checkpoint 与数据文件，保证审稿与读者可复现。

---

## 一、环境

- **平台**：WSL2 Ubuntu 24.04 + Conda (miniconda3) + Python 3.10 + NVIDIA GPU
- **激活**：`source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl`
- **依赖**：torch、numpy、gym、scipy（MPC 求解用）。仅使用专业仿真器（自封装多体动力学，NeTrainSim 公式），禁止 mock 环境。
- **代码**：仓库根 `traffic_rl_project/`。

## 二、仿真器验证（论文 Section III/G）

| 验证项 | 命令 | 数据 |
|:--|:--|:--|
| 动力学/环境/安全层测试（83） | `python -m pytest tests/ -q` | 83 passed |
| 缓解波传播 6.1s (1.0x) | `pytest tests/ -k brake` | 61 步 = 理论 6.1s |
| 制动减压-压钩力单调 | `pytest tests/ -k coupler` | Zhang2025 规律 |
| 车钩间隙-车钩力 52.14kN | `pytest tests/test_coupler_gap.py` | 杨敏规律 |
| 车钩力上限 1000/2250kN | `pytest tests/test_safety_layer.py` | Fu2019 |

## 三、核心实验（论文 Section V，主场景 shuozhou_23800）

**主 checkpoint**：`outputs/checkpoints/mappo_fleet_best_cp_seed0_orig.pt`（3列，固定初态65，M1 +36,446）

| 实验 | 命令 | seed/配置 | checkpoint |
|:--|:--|:--|:--|
| M1 训练（分层阈值协同） | `python src/trainer/train_fleet.py --hierarchical --episodes 200 --num_trains 3 --adj_coef 0.3 --grade shuozhou_23800 --max_steps 300` | seed 0, 300步 horizon | `mappo_fleet_best_cp_seed0_orig.pt` |
| M1 vs M3 vs M4 vs 惰行（主结果） | `python src/evaluation/evaluate_m1_m3_long.py all <ckpt>` | 固定65, 3000步 | — |
| 鲁棒性（10 seed 随机化初态） | `python src/evaluation/evaluate_m1_m3_long.py all <ckpt> --randomize_init --n_seed 10` | init 58-66 km/h | — |
| 压力消融（gap 100→40m） | `python src/evaluation/evaluate_m1_m3_long.py m1 <ckpt> --target_gap 40 --n_seed 1`（逐 gap） | 复用100m训练 | — |
| 5列扩展（shuozhou） | `train_fleet.py --hierarchical --num_trains 5 --grade shuozhou_23800 --checkpoint_dir outputs/checkpoints/shuozhou_5train`（重训）+ `evaluate_m1_m3_long.py --num_trains 5` | seed 0 | `outputs/checkpoints/shuozhou_5train/mappo_fleet_best_cp_seed0.pt` |
| 5列扩展（20km 第二剖面） | 训练于 `--grade long_downhill_20km --num_trains 5` | seed 0 | `outputs/checkpoints/w5_20km_s0/mappo_fleet_best_cp_seed0.pt` |

## 三、统计检验（50-seed 可靠性，论文 Sec. V-C）

```
# 分段收集 50-seed 追尾数据（M1/M3 各 5 段×10）
python src/evaluation/stat_collect_collision.py m1 0 10 outputs/diagnostics/m1_coll.txt   # seed 0-9, 10-19, ..., 40-49
python src/evaluation/stat_collect_collision.py m3 0 10 outputs/diagnostics/m3_coll.txt
# 统计分析（Fisher/卡方/Mann-Whitney + 效应量）
python src/evaluation/stat_analyze_collision.py
# M1 vs M3 reward 统计（10-seed）
python src/evaluation/stat_test_m1_m3.py
```
- **结果**：M1 0/50 追尾(0%) vs M3 17/50(34%)，**Fisher p<0.00001**，Cohen's h=1.25，风险差 0.34 (95% CI [0.21,0.47])
- 数据：`outputs/diagnostics/{m1,m3}_coll.txt`、`collision_stats_50seed.txt`

**公平 DQN baseline（M-DQN-fair）**：
```
# 训练（40ep 即收敛）
python src/trainer/train_fleet_dqn.py --episodes 40 --seed 1 --num_trains 3 --adj_coef 0.3 --target_gap 100 --max_steps 300
# 评估（固定65 / 随机化初态10seed）
python src/evaluation/evaluate_m1_m3_long.py mdqn_fair --dqn_seed 1 --dqn_dir outputs/checkpoints
python src/evaluation/evaluate_m1_m3_long.py mdqn_fair --dqn_seed 1 --dqn_dir outputs/checkpoints --randomize_init --n_seed 10
```
- checkpoint：`outputs/checkpoints/coor_dqn_best_seed1_train{0,1,2}.pt`

**朴素 DQN（M-DQN，忽略车钩力+无协同）**：`src/trainer/train_dqn_cyclic.py` + `eval_dqn_multitrain.py`（对齐 Zhang2024 单列 DQN）

**简化 MPC（M-MPC，探索性，不写入主表）**：
```
python src/evaluation/evaluate_m1_m3_long.py mpc --n_seed 1
```
- 代码：`src/controllers/mpc_controller.py`

## 四、第二剖面探索（论文 Limitations）

| 剖面 | 说明 | 命令 |
|:--|:--|:--|
| long_downhill_20km | 构造 20km，-9.5‰~-11.5‰ | `train_fleet.py --grade long_downhill_20km --curriculum 300-1000-2000-3000` |
| 诊断掉速 | M3 step3000-3500 掉速到0 | `evaluate_m1_m3_long.py m3 --grade long_downhill_20km --max_steps 10000` |

- checkpoint：`mappo_fleet_best_cp_seed{3,4,5,8}.pt`

## 五、图表生成

| 图表 | 命令 | 输出 |
|:--|:--|:--|
| 架构图（Fig.1） | `python src/evaluation/make_architecture_fig.py` | `outputs/figures/fig1_architecture.png` |
| 压力消融图（Fig.2） | `python src/evaluation/make_pressure_fig.py` | `outputs/figures/fig_pressure_ablation.png` |
| 5列间距图（Fig.3） | `python src/evaluation/make_5train_fig.py`（需 shuozhou 5列 checkpoint） | `outputs/figures/fig_5train_gap_trajectory.png` |
| M1/M3/惰行 对比图 + csv | `python src/evaluation/make_m1m3_figures.py` | `outputs/figures/m1m3_{gap,coupler,speed}_trajectory.png` + `outputs/m1m3_comparison.md` |

## 六、论文编译

```
cd traffic_rl_project/docs
conda activate traffic_rl   # 环境含 tectonic 0.17.0
tectonic ITSC_PAPER.tex     # → ITSC_PAPER.pdf（6页，0 Overfull）
```

> 2026-09-08：旧循环制动方案/存档已清理——旧中文对照 `docs/ITSC_PAPER_中文对照.md` 及其产物 `ITSC_PAPER_CN.tex/.pdf`、`build_cn.sh` 均已删除，唯一权威 = `docs/ITSC_PAPER.md / .tex / .pdf`。

## 七、关键参数（论文 Table I）

- 编组：10,000t，1机+100货（~4km）；剖面 shuozhou_23800（-10.9‰）；限速[40,80]km/h
- 目标间距 100m（headway 5s）；训练 horizon 300步 / 评估 3000步
- MAPPO：200ep，lr=5e-5，entropy=0.001，adj_coef=0.3
- 动力学 dt=0.1s；制动/缓解波速 200m/s；车钩力上限 1000/2250kN

## 八、数据归档（outputs/）

- `outputs/m1m3_comparison.md`：M1/M3/惰行/公平DQN/MPC 完整对比表
- `outputs/diagnostics/m1m3_traj_*.csv`：轨迹原始数据（逐列）
- `outputs/figures/`：论文全部图表
- `outputs/checkpoints/`：全部模型 checkpoint
- `outputs/train_logs/`：训练日志（可追溯）
