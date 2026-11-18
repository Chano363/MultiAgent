# 服务器端 closer 可行性评估（把收账从本地搬到云上）

> 状态：**评估 + 建议，未改动现有机制**。触发：owner 2026-11-18
> "检索 closer 最佳工程实践；评估能否把 closer 放到服务器端、任务完成自动关机"。
> 现有机制 = 本地 Windows `schtasks` → ssh 进实例看日志 → 本地 AK 调 API 停机
> （`SERVER_OPS.md` 铁律 12、`scripts/cloud/closer_aliyun_ecs.py`）。
> **证据分层**：一手 = 阿里云/AWS 官方文档（本次 WebFetch/检索逐条核实）；推断 =
> 基于一手对本项目的适配判断；建议 = 待 owner 拍板，不自动生效。

## 一、结论先行

**可行，且明显优于现状**。阿里云一手文档同时提供了三块拼图，刚好补齐现状两个结构性弱点：

| 现状弱点 | 一手的机制 | 效果 |
|---|---|---|
| 本地存 AK 明文（`.aliyun_ak.txt`），closer 依赖本地机器在线 | **ECS 实例 RAM 角色**：实例内经元数据服务（IMDS/IMDSv2）自动取 STS 临时凭证，**无需 AccessKey**（help.aliyun.com/zh/ecs/user-guide/attach-an-instance-ram-role…） | 云上不再有任何 AK；本地关机不影响收账 |
| closer 是本地轮询，会话/机器一死就断 | **实例内 systemd 服务 + `aliyun ecs StopInstance`**：任务进程退出 → 实例自己停自己；**OOS 定时关机**做硬顶兜底 | 收账触发源与任务同生命周期，不依赖外部在线 |

推荐形态：**"实例内自停机（主）+ OOS 定时硬顶（兜底）+ 本地看门狗降级为可选"** 三层，而不是把现有 closer 原样搬上云。理由见 §三/§四。

## 二、一手机制核实（逐条可追溯）

1. **省钱停机模式（Economical Mode / StopCharging）**——阿里云 ECS 帮助中心（Updated 2026-09-17）：停机后释放且**不再计费**的资源 = vCPU、内存、静态公网 IP、镜像许可；**仍计费** = 云盘、EIP、快照；前提 = 按量或抢占式实例。与本项目 `StoppedMode=StopCharging` 口径一致。
   URL: `help.aliyun.com/en/ecs/user-guide/use-the-scheduled-startup-or-shutdown-feature-to-reduce-costs`
2. **OOS 定时开关机**——免费、按标签批量、service-linked role、底层动作 `StopInstance`；支持 Economical Mode 停机。一手明确 OOS 是 "free Alibaba Cloud O&M service … event-driven, scheduled"。
   URL: `help.aliyun.com/en/oos/getting-started/start-or-shut-down-ecs-instances-at-a-scheduled-time`、`help.aliyun.com/en/ecs/user-guide/overview-3`
3. **实例 RAM 角色免 AK**——"无需在 ECS 上的代码或配置文件中保存 AccessKey，通过实例元数据服务（IMDS）自动获取 STS 临时凭证 … 降低 AccessKey 泄露的风险"；支持 IMDSv2 加固模式、自动轮换临时凭证。
   URL: `help.aliyun.com/zh/ecs/user-guide/attach-an-instance-ram-role-to-an-ecs-instance`
4. **CLI 的 EcsRamRole 凭证模式**——`aliyun configure --mode EcsRamRole`（CLI ≥3.3.0），"本地开发环境不支持此凭证类型"（即只能在实例内用）；`aliyun ecs StopInstance --RegionId … --InstanceId … --StoppedMode …` 可在实例内直接停自己。
   URL: `help.aliyun.com/zh/cli/ecs-ram-role`、`help.aliyun.com/en/ecs/developer-reference/create-and-manage-an-ecs-instance-by-using-cli-commands`
5. **OOS 事件/告警触发**——`ACS::AlarmTrigger` 监听云监控指标，越阈触发模板；`ACS-OOS-ExecuteTemplateByAlarm` 把告警转成模板执行。一手限制：**一个模板只能有一个 trigger 且必须是首任务**、不能在子模板用。
   URL: `help.aliyun.com/en/oos/user-guide/acs-alarmtrigger`、`…/acs-oos-execute-template-byalarm`
6. **AWS Well-Architected 同源最佳实践**（跨云对照，非阿里云特有）——MLCOST04-BP08 "Stop resources when not in use"：把"未设自动关机机制"列为反模式，主张监控+自动停机+账单告警；SageMaker idle shutdown 以"无活跃 kernel/terminal"判空闲。
   URL: `docs.aws.amazon.com/wellarchitected/machine-learning-lens/mlcost04-bp08.html`

## 三、关键判断：事件源必须是"任务自己的完成信号"，不是 CPU 阈值

**这是本次评估最重要的一条，直接决定方案成败。**

云监控/OOS 告警天然用 CPU 阈值判空闲，但本项目 2026-11-18 已有一次**同型误杀事故**：closer 旧版把"ssh 连续 3 次不可达"当停机触发，网络抖动把健康实例停掉（00:24，已修为"不可达永不触发"）。"CPU 低于阈值"是同一类间接信号——训练中的评估间隙、断点写盘、numba 预热都可能低 CPU，用它停机 = 把误杀风险从本地搬到云端，问题没解决。

- **一手依据**：AWS SageMaker idle shutdown 的空闲定义是"无活跃 kernel/terminal"（会话级信号），不是低 CPU；阿里云 OOS 示例用 CPU 90% 是**重启**自愈，不是停机省钱——把告警触发用于"停费"在本项目场景下缺一手先例。
- **推断（非一手）**：可靠的完成信号只能由任务自身发出——进程退出码、done marker、产物三件齐（`result.json`+`trajectory.npz`+`intervals.json`，EXECUTION_RULES §长跑）。这三者本项目已具备，是现成的事件源。

## 四、候选方案对比（三选一，待 owner 拍板）

| 方案 | 事件源 | 依赖本地机器 | 消除 AK | 改动面 | 误杀风险 | 适配度 |
|---|---|---|---|---|---|---|
| **甲：实例内自停机（推荐）** | 训练脚本退出/done marker/产物齐 → systemd 服务调 `StopInstance --StoppedMode StopCharging` | **否** | **是**（实例 RAM 角色） | 中：实例内加 1 个 systemd unit + 1 个脚本；本地 closer 保留为可选 | 低：只用直接完成信号，同现有三道触发纪律 | ★★★ 直击现状两弱点 |
| **乙：OOS 事件/告警触发** | 云监控 CPU 阈值 → OOS 模板 StopInstance | 否 | 是（OOS service role） | 中：建告警规则+模板+标签 | **高**：CPU 低≠任务完成，重复 00:24 误杀模式 | ★ 只适合做硬顶兜底 |
| **丙：维持现状 + 定时硬顶** | 本地 schtasks closer（现状）+ OOS 定时关机兜底 | **是**（本地轮询） | 否（AK 仍在本地） | 小：只加一条 OOS 定时规则 | 低（现状已修误杀） | ★★ 改进有限，AK/本地依赖没解决 |

**推荐 = 甲 + 乙/丙的定时部分做硬顶**：实例内自停机负责"任务完成即停"（省钱、快），OOS 定时关机负责"到点必停"（防实例内机制也挂掉的最终兜底，与现有硬 deadline 同定位）。三者职责不重叠：**完成信号管"早停"，定时硬顶管"必停"**——与本项目铁律 12"三道触发 + 硬 deadline"的分工一致，只是把执行点从本地移到云上。

## 五、若采纳甲的落地清单（预估，未执行）

1. **云控制台一次性配置**（需 owner 批准/操作）：建 RAM 角色（信任 ECS 服务）、只授 `ecs:StopInstance` + `ecs:DescribeInstances` 最小权限、绑定到实例；确认实例为按量付费、省钱停机模式已开。
2. **实例内**（自定义镜像或开机脚本）：装 aliyun CLI ≥3.3.0 → `aliyun configure --mode EcsRamRole` → 加 systemd unit：监控训练 pid/done marker/产物三件齐，触发 `aliyun ecs StopInstance --StoppedMode StopCharging --ForceStop false`。
3. **保留本地 closer 为可选**：迁移期双保险；稳定后本地不再存 AK（符合"明文禁止进本地"的收紧方向，但改凭据存放需 owner 单独批）。
4. **验收**：同 ckpt 同 seed 复跑不受影响（不改物理/不改训练）；断网模拟（本地关机）实例仍能自停；误杀测试（评估间隙低 CPU 不停机）；停机回执 `Stopped`+`StopCharging`。

## 六、纪律边界

- 本报告**不改任何现有机制**：铁律 12、closer 脚本、schtasks 注册流程保持原样，直到 owner 拍板采纳。
- 任何云端配置（尤其开/关实例、改 RAM 角色）命中硬红线第 1 条，须先批规格/预算；本报告不含任何实操。
- 一手/推断/建议已分层：§二是官方文档明写，§三的判断基于一手+本项目事故记录，§四/§五是建议非决议。

## 七、一手链接汇总

- 省钱停机 + OOS 定时：https://help.aliyun.com/en/ecs/user-guide/use-the-scheduled-startup-or-shutdown-feature-to-reduce-costs
- OOS 定时开关机入门：https://help.aliyun.com/en/oos/getting-started/start-or-shut-down-ecs-instances-at-a-scheduled-time
- ECS RAM 角色免 AK：https://help.aliyun.com/zh/ecs/user-guide/attach-an-instance-ram-role-to-an-ecs-instance
- CLI EcsRamRole 凭证：https://help.aliyun.com/zh/cli/ecs-ram-role
- StopInstance API（含 StoppedMode）：https://help.aliyun.com/en/ecs/developer-reference/create-and-manage-an-ecs-instance-by-using-cli-commands/
- OOS 告警触发：https://help.aliyun.com/en/oos/user-guide/acs-alarmtrigger
- AWS ML 成本最佳实践：https://docs.aws.amazon.com/wellarchitected/latest/machine-learning-lens/mlcost04-bp08.html
