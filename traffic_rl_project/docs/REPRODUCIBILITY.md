# 可复现性说明（原论文稿附；论文稿已删除，本文档保留作历史复现参考）

> 本文档汇总原论文稿（已删除）所有实验的确切运行命令、随机种子、checkpoint 与数据文件，保证审稿与读者可复现。

> **【superseded 声明（2026-09-22，ADR-013）】**：本文档正文（二\~九节）对应的实验体系为**已下线的编队层阈值 RL 方案**（`train_fleet.py --hierarchical`，M1/M3、M-DQN、50-seed，R0 旧物理）——该"编队层（列车级）RL + 列内层（机车级）RL 两层叠加"框架已于 **ADR-013（2026-09-08）废止**，相关历史数值不作当前主结果引用。历史命令/数值/seed 全部原样保留，仅供回溯与复现旧方案。**现行方案（formation-aware 机车级 ED/AB 分工，唯一 RL 落位）的复现命令见文末「十、现行方案复现」一节**。权威出处：`docs/logs/decisions/DECISIONS.md` ADR-013。

> **【删除关联声明（2026-10-19）】**：原论文稿 `ITSC_PAPER.md/.tex/.pdf` 已删除（目标会议更换，不再是 ITSC）；本文档保留作历史实验复现参考，论文重写后重建复现文档。权威出处：`docs/logs/decisions/DECISIONS.md`。

***

## 一、环境

- **平台**：WSL2 Ubuntu 24.04 + Conda (miniconda3) + Python 3.10 + NVIDIA GPU

- **激活**：`source ~/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl`

- **依赖**：torch、numpy、gym、scipy（MPC 求解用）。仅使用专业仿真器（自封装多体动力学，NeTrainSim 公式），禁止 mock 环境。

- **代码**：仓库根 `traffic_rl_project/`。

## 二、仿真器验证（论文 Section III/G）

| 验证项               | 命令                                  | 数据             |
| :---------------- | :---------------------------------- | :------------- |
| 动力学/环境/安全层测试（83）  | `python -m pytest tests/ -q`        | 83 passed      |
| 缓解波传播 6.1s (1.0x) | `pytest tests/ -k brake`            | 61 步 = 理论 6.1s |
| 制动减压-压钩力单调        | `pytest tests/ -k coupler`          | Zhang2025 规律   |
| 车钩间隙-车钩力 52.14kN  | `pytest tests/test_coupler_gap.py`  | 杨敏规律           |
| 车钩力上限 1000/2250kN | `pytest tests/test_safety_layer.py` | Fu2019         |

<br />

## 三、核心实验（论文 Section V，主场景 shuozhou\_23800）

> ⚠️ **本节的命令链已失效（2026-10-01，ADR-022）——保留作历史记录，勿照抄执行。**
> 原因：① 评估入口 `src/evaluation/evaluate_m1_m3_long.py` 及其依赖脚本
> （`make_m1m3_figures.py` / `make_5train_fig.py` / `eval_phys2_*` / `eval_dqn_multitrain.py`）
> **已删除**；② `FairMPCController` / 简化 `MPCController` **已删除**，MPC 基线唯一化
> 为 `NMPCController`（`evaluate_decompose.py --mpc_type nmpc`）；③ M1/M3/M4 语义代号
> 已废止（ADR-013 起）、主场景改为 `shuozhou_ningwuxi_beidaniu_49km`（2026-10-12 换统一线路表重建；ADR-017/021 时为 `shuozhou_real_53km`，已删除）。
> **现行入口** = §十（主训练）与 `evaluate_decompose.py`；历史结果文件原样保留在 `outputs/`。

**主 checkpoint**：`outputs/checkpoints/mappo_fleet_best_cp_seed0_orig.pt`（3列，固定初态65，M1 +36,446）

| 实验                        | 命令                                                                                                                                                                      | seed/配置              | checkpoint                                                         |
| :------------------------ | :---------------------------------------------------------------------------------------------------------------------------------------------------------------------- | :------------------- | :----------------------------------------------------------------- |
| M1 训练（分层阈值协同）             | `python src/trainer/train_fleet.py --hierarchical --episodes 200 --num_trains 3 --adj_coef 0.3 --grade shuozhou_23800 --max_steps 300`                                  | seed 0, 300步 horizon | `mappo_fleet_best_cp_seed0_orig.pt`                                |
| M1 vs M3 vs M4 vs 惰行（主结果） | `python src/evaluation/evaluate_m1_m3_long.py all <ckpt>`                                                                                                               | 固定65, 3000步          | —                                                                  |
| 鲁棒性（10 seed 随机化初态）        | `python src/evaluation/evaluate_m1_m3_long.py all <ckpt> --randomize_init --n_seed 10`                                                                                  | init 58-66 km/h      | —                                                                  |
| 压力消融（gap 100→40m）         | `python src/evaluation/evaluate_m1_m3_long.py m1 <ckpt> --target_gap 40 --n_seed 1`（逐 gap）                                                                              | 复用100m训练             | —                                                                  |
| 5列扩展（shuozhou）            | `train_fleet.py --hierarchical --num_trains 5 --grade shuozhou_23800 --checkpoint_dir outputs/checkpoints/shuozhou_5train`（重训）+ `evaluate_m1_m3_long.py --num_trains 5` | seed 0               | `outputs/checkpoints/shuozhou_5train/mappo_fleet_best_cp_seed0.pt` |
| 5列扩展（20km 第二剖面）           | 训练于 `--grade long_downhill_20km --num_trains 5`                                                                                                                         | seed 0               | `outputs/checkpoints/w5_20km_s0/mappo_fleet_best_cp_seed0.pt`      |

## 四、统计检验（50-seed 可靠性，论文 Sec. V-C）

```
# 分段收集 50-seed 追尾数据（M1/M3 各 5 段×10）
python src/evaluation/stat_collect_collision.py m1 0 10 outputs/diagnostics/m1_coll.txt   # seed 0-9, 10-19, ..., 40-49
python src/evaluation/stat_collect_collision.py m3 0 10 outputs/diagnostics/m3_coll.txt
# 统计分析（Fisher/卡方/Mann-Whitney + 效应量）
python src/evaluation/stat_analyze_collision.py
# M1 vs M3 reward 统计（10-seed）
python src/evaluation/stat_test_m1_m3.py
```

- **结果**：M1 0/50 追尾(0%) vs M3 17/50(34%)，**Fisher p<0.00001**，Cohen's h=1.25，风险差 0.34 (95% CI \[0.21,0.47])

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

**朴素 DQN（M-DQN，忽略车钩力+无协同）**：`src/trainer/train_dqn_cyclic.py` + 评估入口 `eval_dqn_multitrain.py`（**已按 ADR-022 删除**，对齐 Zhang2024 单列 DQN 的评估链随之失效）

**简化 MPC（M-MPC，探索性，不写入主表）**：⚠️ **已删除**（ADR-022：`src/controllers/mpc_controller.py` 全仓从未启用；现行 MPC 基线 = `NMPCController`）。

```
# 历史命令（已失效，仅供追溯）
python src/evaluation/evaluate_m1_m3_long.py mpc --n_seed 1
```

## 五、第二剖面探索（论文 Limitations）

| 剖面                   | 说明                    | 命令                                                                          |
| :------------------- | :-------------------- | :-------------------------------------------------------------------------- |
| long\_downhill\_20km | 构造 20km，-9.5‰\~-11.5‰ | `train_fleet.py --grade long_downhill_20km --curriculum 300-1000-2000-3000` |
| 诊断掉速                 | M3 step3000-3500 掉速到0 | `evaluate_m1_m3_long.py m3 --grade long_downhill_20km --max_steps 10000`    |

- checkpoint：`mappo_fleet_best_cp_seed{3,4,5,8}.pt`

## 六、图表生成

| 图表                 | 命令                                                                   | 输出                                                                                       |
| :----------------- | :------------------------------------------------------------------- | :--------------------------------------------------------------------------------------- |
| 架构图（Fig.1）         | `python src/evaluation/make_architecture_fig.py`                     | `outputs/figures/fig1_architecture.png`                                                  |
| 压力消融图（Fig.2）       | `python src/evaluation/make_pressure_fig.py`                         | `outputs/figures/fig_pressure_ablation.png`                                              |
| 5列间距图（Fig.3）       | `python src/evaluation/make_5train_fig.py`（需 shuozhou 5列 checkpoint） | `outputs/figures/fig_5train_gap_trajectory.png`                                          |
| M1/M3/惰行 对比图 + csv | `python src/evaluation/make_m1m3_figures.py`                         | `outputs/figures/m1m3_{gap,coupler,speed}_trajectory.png` + `outputs/deprecated/m1m3_comparison.md` |

## 七、论文编译

```
cd traffic_rl_project/docs
conda activate traffic_rl   # 环境含 tectonic 0.17.0
tectonic ITSC_PAPER.tex     # → ITSC_PAPER.pdf（6页，0 Overfull；源稿已删除，命令仅存档）
```

> 原"唯一权威"论文稿 `docs/ITSC_PAPER.md / .tex / .pdf` 已于 2026-10-19 全部删除（目标会议更换），见 git 历史。

## 八、关键参数（论文 Table I）

- 编组：10,000t，1机+100货（\~4km）；剖面 shuozhou\_23800（-10.9‰）；限速\[40,80]km/h

- 目标间距 100m（headway 5s）；训练 horizon 300步 / 评估 3000步

- MAPPO：200ep，lr=5e-5，entropy=0.001，adj\_coef=0.3

- 动力学 dt=0.1s；制动/缓解波速 200m/s；车钩力上限 1000/2250kN

## 九、数据归档（outputs/）

> **【2026-10-02 更新】** 本节列举的是**历史归档路径**（多为已下线旧方案的产物，部分已不存在）。现行 `outputs/` 布局与命名**唯一规范**见 `rules/EXECUTION_RULES.md`「产物目录规范（outputs/ 布局）」。

- `outputs/deprecated/m1m3_comparison.md`：M1/M3/惰行/公平DQN/MPC 完整对比表

- `outputs/diagnostics/m1m3_traj_*.csv`：轨迹原始数据（逐列）

- `outputs/figures/`：论文全部图表

- `outputs/checkpoints/`：全部模型 checkpoint

- `outputs/train_logs/`：训练日志（可追溯）

## 十、现行方案复现（formation-aware 机车级 ED/AB，ADR-013 唯一 RL 落位）

> **现行主方案**（2026-09-08 ADR-013 起唯一 RL 落位）：formation-aware 机车级 ED/AB 分工（每台机车=智能体，ED 连续 / AB 离散档位，以编队为上下文）；底层列内规则循环制动 + 车钩力安全层（`enforce_coupler` ≤1000kN）确定性执行。上方二\~九节为已下线旧方案（编队层阈值 RL）复现，不作当前主结果。

**主训练（5 seed）**：

```
python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml --seed {0..4}
```

- 配置：`configs/experiments/formation_ed_ab_3train_1plus1.yaml`（3 列×1+1=6 agent，49.6km `shuozhou_ningwuxi_beidaniu_49km`，curriculum 上限 1200 步，MAPPO）

- **主训练口径（ADR-017 达标，2026-10-01 已对齐并验证）**：本 YAML 直接写达标值 —— `episodes: 1400`（总训练量达标）+ `n_env: 4` / `parallel_traj_len: 0`（并行 4 条独立短轨迹，≤1200 步）+ `warm_start: true`（BC 热启动）+ `long_eval_interval: 50` / `long_eval_steps: 36000`（每 50 ep 完整剖面确定性评估选优）。物理与分析口径同节下文。
  - ⚠️ **快速迭代不要改本值**：用 CLI 覆盖 `--episodes N`（如 `--episodes 2`），YAML 保持 1400；否则主训练又落在不足量上。
  - ⚠️ `env_cfg.max_steps: 36000` 是 **env 截断上限 / 评估口径**，不是训练时域 —— `TrainRunner` 每集用 `env.max_steps = parallel_len`（curriculum horizon ≤1200）覆盖它。

- 每次训练自动落 `metadata.json`（git\_commit / physics\_version / simulator\_model / 超参 / seed / checkpoint）；**不进此入口的训练结论不认可、不得引用**（`docs/rules/EXECUTION_RULES.md`）

**重训里程碑（ADR-023 口径，2026-10-02 重启 seed0）**：

- ⚠️ **为何重启（ADR-023）**：ED 调制带宽放宽为全幅（`ed_mod_coef` 0.5 → **1.0**）⇒ **动作空间语义变更**（同一 ckpt 行为不同）⇒ 旧带宽（0.5）下产出的 ckpt 与评估数值对新口径失效。旧运行 `outputs/checkpoints/formation/adr021_1400ep_seed0`（启动器 `scripts/launchers/launch_retrain_adr021_seed0.sh`）跑至 **ep55/1400（elapsed 5h22m，viol 0，pkCpl ≤906 kN）** 后主动停掉，其 55 集产物**原样保留**（不覆盖、不删除），仅作"旧带宽口径"留痕，**不得引用**。
- 启动器：`scripts/launchers/launch_retrain_adr023_seed0.sh`（`set -e` + conda 激活 + `exec python run_training.py …`）。
- 🔁 **再重启（ADR-024 口径，2026-10-02）**：ADR-023 的带宽放宽经完整剖面 A/B 判为"**对 MPC 无收益、对 RL 有害**"，ADR-024 遂回退 `ed_mod_coef` 1.0→0.5 ⇒ **又一次动作语义变更**，`adr023_1400ep_seed0`（ep205/1400 停）作废并原样保留。新启动器 = `scripts/launchers/launch_retrain_adr024_seed0.sh`；新目录 = `outputs/checkpoints/formation/adr024_1400ep_seed0`；日志 = `outputs/logs/diagnostics/log_retrain_adr024_seed0_20261002.txt`；恢复命令同下，目录整体替换 `adr023` → `adr024`。**主表只引用 `adr024` 及以后的 ckpt**（`adr021` 旧结构、`adr023` 1.0 口径仅作留痕）。
- ⚠️ **执行方式（实测教训，LRN-20261001-014）**：IDE 的 Shell 工具**在调用返回时会回收本次调用派生的全部进程** —— `nohup setsid … &` 不能让它跨调用存活（存活探针 `nohup setsid sleep 90 … &` 下次调用即查不到进程与文件）。可行两条：① `run_in_background: true`（进程与调用同生命周期，会话内可用）；② 用户自己的 WSL 终端执行下方命令（脱离 IDE 会话，适合数天级）：
  ```
  cd /mnt/d/Code/MultiAgent/traffic_rl_project
  nohup setsid bash scripts/launchers/launch_retrain_adr023_seed0.sh > outputs/logs/diagnostics/log_retrain_adr023_seed0_20261002.txt 2>&1 < /dev/null &
  ```
- 输出（**全新目录，不覆盖任何历史产物**）：`outputs/checkpoints/formation/adr023_1400ep_seed0/{,results,figures}`；日志 `outputs/logs/diagnostics/log_retrain_adr023_seed0_20261002.txt`。启动实证：`pgrep` 到 `run_training.py … --checkpoint_dir …/adr023_1400ep_seed0`、`results/metadata.json` 已落盘（`episodes=1400` / `critic=per_agent` / `reward_schema=v2-bounded-overlimit-section-force` / **`ed_mod_coef=1.0`** / `simulator_model … simcase=official … grade=shuozhou_real_53km`）。
  - ⚠️ **未提交改动的溯源边界**：本次重启时工作树仍含**未提交**改动（ADR-021/022/023 的代码与文档改动尚未 `git commit`），故 `metadata.json.git_commit`（`ff745cf`）**不覆盖**这些改动 —— ckpt 与工作树的对应依赖"先提交再引用"；正式出主表前须提交并复核 commit 一致性（**待用户指令**）。
- 中断恢复（ADR-019：`--episodes` = **总目标集数**，非增量）：
  ```
  python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus1.yaml --seed 0 --episodes 1400 --resume latest --checkpoint_dir outputs/checkpoints/formation/adr023_1400ep_seed0 --results_dir outputs/checkpoints/formation/adr023_1400ep_seed0/results --override dirs.figures_dir=outputs/checkpoints/formation/adr023_1400ep_seed0/figures
  ```
- ⚠️ **机时预期（2026-10-01 实测更正）**：**≈11.7 天/seed**（先前登记的"≈3.4 天"**低估约 3.4×**，勿再引用）。推导：
  - **实测基准（seed0 长训自身的进度条，非外推猜值）**：500 步课时下 **271 / 276 / 274 / 278 s/集**（`n_env=4` 并行 4 条轨迹 ⇒ 约 0.137 s/env-step）；BC 热启动另耗 **≈11 min**（`Fleet BC warm start: 采集 27000 条 … 30 epochs`）。
  - **课时折算**（curriculum `500:0,1000:10,1200:20`，每集耗时随时域近似线性）：ep1–10 ≈275 s；ep11–20 ≈550 s；ep21–1400 ≈660 s ⇒ **合计 ≈919 000 s ≈ 10.6 天**。
  - 叠加 `long_eval_interval=50` 的 **28 次**完整剖面评估（36000 步 ≈0.095 s/步 ⇒ ≈57 min/次）≈ **1.1 天** ⇒ **总计 ≈11.7 天/seed**。
  - ⚠️ **tqdm 自身 ETA 会低估**：它按当前（500 步）速率线性外推，给出 `105~108 h`（≈4.5 天），**不随 curriculum 升到 1000/1200 步调整** ⇒ 别拿它排期。2026-10-01 的"≈3.4 天"正是同类低估的产物。
  - ⚠️ **排期含义**：`1400 ep × 5 seed` 单机串行 ≈ **58 天**，须先决定是减课时/减集数、还是并行多机/多卡。
  - GPU 在 BC 阶段基本空闲（CPU 密集），训练阶段才用 GPU。
  - ⚠️ **【2026-10-07 更正】上列 ≈11.7 天/seed 系高估，勿再用于排期**：`routecov_1400ep_seed0` 串行 run 的周期性 checkpoint 墙钟间隔实测 —— ep10→20 **30.2 min**、ep20→30 **39.7 min**、ep30→40 **38.6 min**、ep60→70 **31.0 min**、ep70→80 **27.3 min** ⇒ **horizon 1200 稳态 ≈165–190 s/ep**（≈0.04–0.05 s/env-step，比上列 0.137 s/env-step 快 ≈3×）；long_eval 每次实耗 **≈33 min**（非 57 min）。⇒ **串行全量 ≈ 1400×180 s + 28×33 min ≈ 3.5 天/seed**。上列 11.7 天所依据的"500 步课时 271–278 s/集"疑为当时伴随其他作业的 CPU 争用产物；**以本更正为准**。
  - ⚠️ **并行 rollout 可用**（2026-10-07 新增）：`--override n_env_parallel=true` 把 n_env 条轨迹改走进程级并行（见 `src/trainer/parallel_rollout.py`），预期 ≈3× 提速；**并行与串行数值不逐位相同**，同一次 5-seed 对比必须统一走同一条路径。
- ⚠️ 日志为 `>` 重定向 ⇒ **块缓冲**，分钟级延迟属正常；判活用 `pgrep -af run_training.py` + `ps -o etime,pcpu -p <pid>`。

**评估（主对比三行 D-RL / D-Rule / MPC @49.6km）**：

```
python src/evaluation/evaluate_decompose.py --mode all --checkpoint <best.pt 或 last_ep1400.pt 路径> \
  --mpc_type nmpc --n_seed 3
```

- ⚠️ **2026-10-01 修复说明**：`--mode all` 此前因 `--enable_mpc` 默认 `store_true=False` 而**静默只出 2 行（缺 MPC）** —— 与本节"三行"口径不符，且三行 Δ 摘要（`len(results)>=3`）会同步静默跳过。现已归一为 `all/mpc ⇒ enable_mpc=True`（见 `LEARNINGS.md` LRN-20261001-011 / `DIAGNOSTICS_2026-10.md`「修复-2026-10-01b」）。
- ⚠️ **`--decision_interval` 已改为自动读取（2026-10-01）**：该参数此前默认写死 **1**，而训练用 **10** ⇒ 上面的命令（**未显式传参**）会让 D-RL 行以"每原始步重新决策"跑，与训练的半 MDP 失配。现默认 `None` = **自 ckpt 内嵌 metadata 读取**（读不到退回训练标准值 10 并打印提示）；显式传 `--decision_interval N` 行为不变。**上表命令无需再手动加该参数**（LRN-20261001-015）。
- ⚠️ **成本提示（实测，NMPC=唯一基线）**：`NMPC(IPOPT)` 实测 **74 ms/步均值 / 1693 ms 峰值**（3 列 1+1，300 步窗口，峰值在首步符号构建）⇒ 49.6km（36000 步）**MPC 行 ≈0.74 h/seed**，`--n_seed 3` 时**仅 MPC 一行 ≈2.2 h**（比已删除的 fair/SLSQP 快约 9×）。D-RL/D-Rule 行各 ≈57 min（实测 400 步 ≈38 s 外推）。排期时请分开估算。
- MPC 的「求解失败次数」口径 = **求解器自身收敛标志**（NMPC：IPOPT 状态，非 `optimal` 记 `fail:<msg>`），见 LRN-20261001-013。
- ✅ **MPC 基线唯一化为 NMPC（2026-10-01，ADR-022）**：`--mpc_type` 只留 `nmpc`（旧 `fair`=FairMPCController / `--mpc_simple` 及其控制器文件**已删除**；`--mpc_enforce_coupler` 随之移除）。主表命令**请显式带 `--mpc_type nmpc`**。`inner_rule_cyclic` 由硬编码改为显式 `--mpc_inner_rule_cyclic`（**默认 False = like-for-like**：decompose 通道里 env 本来就无条件施加规则基线，置 True 等于 MPC 叠两层护盾，仅复现历史 `mpc_rule` 用）。⚠️ **2026-10-13 ADR-034：主表角色修订**——NMPC 退出主表（转 related work 文本），主表 MPC 行 = Formation-MPC（Song2026 架构 + 关车钩约束；实现与评估命令待实验设计时另行登记）。
- ✅ **MPC 行"动作桥接量纲错配"已修复（2026-10-01，甲方=反解加性关系，用户裁定）**：原 `mpc_act` 经 `get_action_accel` 产生**绝对 ED 深度 ∈[0,1]**（且永不为负），却喂给 decompose 的**加性 `ed_mod` 通道**（`final_ed = clip(baseline_ed + 0.5·ed_mod)`）⇒ ① 指令不被兑现（实测指令 0.75 → 实际 ED 打满 1.0，与 `meanED=1.000` 观测一致）；② **MPC 结构上不能减闸/施加牵引**；③ AB 通道恒 0（落在 ±0.15 死区）= 无 AB 权限。**现改为**：`mpc_act` 先复算规则基线（`_rule_baseline_edab`，保存/还原闩锁）再反解 `ed_mod = clip((desired_ed − baseline_ed)/0.5, ±1)`，并按 MPC 意图给 `ab_mod`（想停/加速→抑制；需求 `desired_ed ≥ 0.7` →预触发兜底）⇒ **MPC 与 D-RL 动作权限完全一致**，唯一差异 = 决策来源（ADR-016 不失公允）。
  - ⚠️ **已知近似（有界、可审计）**：规则基线以**未协调**带边复算（env 内部对 follower 会叠 `coordination_adj`，其依赖"前一列已 step 后的位置"，在 `env.step` 之前不可复现）⇒ follower 处于带边附近时基线估计有偏差（≤0.5 ED 深度）。**不影响安全性**（env 侧 clip + SafetyLayer + ETCS 全程生效），只影响请求的交付精度。要精确需改闭包内 env ⇒ 需停训。
  - ⚠️ **MPC 行历史数值全部作废，须重跑**（控制器更换 + 桥接口径已修）。详见 `DIAGNOSTICS_2026-10.md`「修复-2026-10-01d」/「删除-2026-10-01」+ `DECISIONS.md` ADR-022。
  - **验证（实跑，nmpc-only 口径）**：
    ```
    python src/evaluation/evaluate_decompose.py --mode mpc --max_steps 300 --n_seed 1 --mpc_type nmpc \
      --out_suffix _nmpc_only_check
    ```
    ⇒ `MPC(NMPC 集中质量多体+MT-2+IPOPT): reward +2221 | peak 318kN | viol 0 | meanED 0.512 |
    band 100.00% | 末速 73.3km/h | MPC求解 74ms均值/1693ms峰值 | fail 0 | 桥接越权请求 455 步·机车`。
    （历史 fair 口径为 `meanED 0.744`；修复前为 1.000 饱和，仅作桥接正确性旁证。）
  - ⚠️ **实测暴露的第二类权限约束（须与 `accel_lo` 一并裁决）**：`桥接越权请求 455 步·机车`
    = NMPC 有 455 次"期望 ED 与规则基线之差 > ±0.5"被 clip 截断 ⇒ **±0.5 的 ED 调制权限带
    对 NMPC 偏窄**（fair 行该计数为 0）。注意该带宽与 D-RL **完全相同**（like-for-like 的设计
    结果），故这不是"MPC 被单独削弱"，而是"**动作权限带本身**是否够用"的问题——
    与 `accel_lo=-0.75 ⇒ 期望 ED 上限 0.75 < 规则/RL 的 1.0` 是**同一族**（控制器/接口侧对
    MPC 制动深度的双重上限）。放宽任一项都需同步评估 D-RL 的同一限制，避免造出新的不对称。
- ⚠️ **`--checkpoint` 该指哪个文件？先确认存在性再跑**（2026-10-01 审计，`train_runner.py:300-302 / 460-471`）：
  | 文件 | 产生条件 | 训到 1400 ep 时是否保证存在 |
  | :-- | :-- | :-- |
  | `mappo_fleet_last_ep{N}_{cp_tag}_seed{S}.pt` | 每 `log_interval`(=10) ep 一次，**且末集必写**（`_periodic`/`save_last`） | ✅ **保证存在**（`N=1400`） |
  | `mappo_fleet_ep{N}_{cp_tag}_seed{S}.pt` | 每 10 ep（periodic） | ✅ 存在（多份） |
  | `mappo_fleet_best_{cp_tag}_seed{S}.pt` | **仅当**某次 `long_eval`（每 50 ep）满足 `viol==0 ∧ 峰值≤1000 kN ∧ 末速∈[40,80] km/h` **且** reward 创新高才写 | ⚠️ **不保证**：一次都没达标 ⇒ 该文件**根本不存在** |
  - 原因：`long_eval > 0` 时 **`_maybe_save_best` 被跳过**（`:300-302`），训练窗口 reward 不再直接写 `best`；`best` 完全由 `long_eval` 的达标判据驱动。
  - ⇒ **跑主表前先 `ls` 确认**；`best` 不存在时不要以为训练失败，改用 `last_ep1400`。
  - ⚠️ **待裁决（影响主表口径，需用户确认）**：项目既有口径为"主结果用**完整训练后的 `last`**（1400 ep），不用训练 reward 选出的 `best`"（用户既定偏好）；但 ADR-017 §2 又要求 `long_eval` 用完整剖面**选优**。二者在"`best` 现由评估指标而非训练 reward 选出"之后**不再互斥** ⇒ 须明确：主表 D-RL 行取 `last_ep1400`（端态、无条件可复现），还是取 `best`（评估选优）。**裁决前不要只跑一行就下结论。**

**跨线评估（ADR-037 对比口径；2026-10-12 起 M2 储备）**：

```
# D-RL / D-Rule 行（跨线零微调）
python src/evaluation/evaluate_decompose.py --mode decompose_m1 --grade <20km或35km剖面> --checkpoint <last_ep1400.pt 路径>
# MPC 行（坡度为固有输入，同一环境/坡度数据；无逐线重喂/标定协议）
python src/evaluation/evaluate_decompose.py --mode mpc --mpc_type nmpc --grade <20km或35km剖面> --n_seed 1
```

> 注：`--mode` 的合法取值是 `all / decompose_m1 / decompose_m0 / mpc / single`（无 `decompose`；旧文档写 `--mode decompose` 属笔误，2026-10-01 更正）。

- 跨线协议（ADR-037，2026-10-16；2026-10-19 ADR-042 起升格为正式实验组别）：D-RL 跨线**严格零微调**（公开声明 "no fine-tuning on target line"）；MPC 用该线坡度数据（固有输入），**不设逐线重喂 `grade_at`/标定 b0 协议**（ADR-037 废止 Regime A；ADR-016 已废止 Regime B），不作成本叙事。核心 claim（2026-10-19 ADR-042）= **相对传统基线的编队指标收益**（主对比物理关闭车钩力，无独立消融列）。

**消融（杠杆隔离）**：`--mask_lever ed/ab`（ED-only / AB-only），留痕见 `docs/logs/diagnostics/`。

> 权威出处：`docs/PROJECT_PIPELINE.md`（任务清单）、根 `AGENTS.md`（现行命令）、`docs/logs/decisions/DECISIONS.md` ADR-013/ADR-016。

<!-- 该文档整理/压缩于 2026-10-01 -->
