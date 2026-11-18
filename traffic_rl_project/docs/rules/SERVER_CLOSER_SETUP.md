# 服务器端 closer 启用手册（控制台一次性操作，需 owner 批）

> 配套：`docs/CLOSER_SERVER_SIDE_ASSESSMENT.md`（为什么这样做）、
> `scripts/cloud/self_stop_ecs.sh`（实例内自停机主机制）、
> `scripts/cloud/instance_watchdog.sh`（三结局判据，已接入自停机）、
> `scripts/cloud/oos_hard_deadline_template.yml`（云端硬顶兜底）。
> **状态：代码就绪、离线 mock 测试 9/9 通过；云端配置尚未执行（需 owner 批准变更操作）。**
> 本手册只写"一次性做什么"，不自动改任何云端资源。

## 前置确认（owner 批）

- 目标实例 `i-f8zcp6vvis4rnztw0p9y` 为**按量付费**（省钱模式前提）；当前为 Stopped+StopCharging。
- AK 是 RAM 子账号 `ecs-ops`（主账号 1749554754126152）。**建 RAM 角色需要更高权限或主账号操作**——本手册第一步即需 owner 确认由谁执行。
- 云端角色/模板变更命中硬红线第 1 条（云实例与权限变更须先批），未批不执行。

## 步骤一：建 RAM 角色并绑到实例（一次性，控制台）

一手依据：`help.aliyun.com/zh/ecs/user-guide/attach-an-instance-ram-role-to-an-ecs-instance`

1. RAM 控制台 → 身份管理 → 角色 → 创建角色：
   - 信任主体类型 = **云服务**；信任主体名称 = **云服务器 ECS / ECS**
   - 角色名建议 `ecs-training-selfstop`
   - 信任策略（文档原文）：`{"Statement":[{"Action":"sts:AssumeRole","Effect":"Allow","Principal":{"Service":["ecs.aliyuncs.com"]}}],"Version":"1"}`
2. 给该角色授权**最小权限**：自定义策略只含
   - `ecs:StopInstance`（自停机必需）
   - `ecs:DescribeInstances`（停机后复核必需）
   - 资源范围限定到目标实例 ARN（不要 `*`）
3. ECS 控制台 → 实例 → 更多 → 实例设置 → **授予/更换 RAM 角色** → 选 `ecs-training-selfstop`。
4. 验证（实例内）：`curl -s http://100.100.100.200/latest/meta-data/ram/security-credentials/ecs-training-selfstop` 能拿到 STS 临时凭证（字段含 AccessKeyId/AccessKeySecret/SecurityToken）。

> 安全收益：云上不再存 AK 明文；临时凭证自动轮换（STS）。本地 `.aliyun_ak.txt` 在迁移期保留，稳定后可收紧（单独批）。

## 步骤二：实例内装 CLI 并配 EcsRamRole 凭证（开机后一次性）

一手依据：`help.aliyun.com/zh/cli/ecs-ram-role`

在实例内（非本地）：
```bash
# 装 aliyun CLI >= 3.3.0（版本不够则升级）
aliyun version
# 配 EcsRamRole 凭证 profile（profile 名要与 self_stop_ecs.sh 的 ALIYUN_PROFILE 默认 ecs-self 一致）
aliyun configure --mode EcsRamRole --profile ecs-self
# 依次输入：RAM 角色名 ecs-training-selfstop / 默认地域 cn-heyuan / 语言 en / 输出格式 json
# 验证：能列出本实例即凭证通
aliyun ecs DescribeInstances --RegionId cn-heyuan --profile ecs-self
```

## 步骤三：部署脚本到实例（随代码同步）

`self_stop_ecs.sh` 与 `instance_watchdog.sh` 已在仓库 `scripts/cloud/`，随 rsync 上云。
确认 watchdog 启动参数里 `SELF_STOP_SCRIPT` 指向实例内路径（默认 `/root/traffic_rl_project/scripts/cloud/self_stop_ecs.sh`，无需改）。

## 步骤四：OOS 定时硬顶兜底（一次性，控制台）

一手依据：`help.aliyun.com/en/oos/user-guide/acs-ecs-stopinstance`、`help.aliyun.com/en/oos/getting-started/start-or-shut-down-ecs-instances-at-a-scheduled-time`

1. OOS 控制台 → 模板管理 → 创建模板 → 粘贴 `scripts/cloud/oos_hard_deadline_template.yml`。
2. 用该模板建**定时执行**任务：设定 deadline 时间（建议 = 本次训练开机时刻 + 预算墙钟，如 +6 h），目标实例填 `i-f8zcp6vvis4rnztw0p9y`，地域 `cn-heyuan`，权限 `OOSServiceRole`（默认服务关联角色）。
3. 这种定时任务**每次开训前按本次 deadline 更新时间/新建一次**——与本地 closer 的 `--deadline-min` 同定位（必停兜底），不依赖本地在线。

> 注意：OOS 告警触发（CPU 阈值）**不用于停机**，只适合自愈重启；本项目已因"间接信号"误杀过一次（2026-11-18 00:24 ssh 不可达误停健康实例），CPU 低≠任务完成，理由见评估文档 §三。

## 步骤五：验收（启用前必须全过）

- [ ] 实例内 `aliyun ecs DescribeInstances --profile ecs-self` 成功（凭证通）
- [ ] mock 测试：`bash tests/test_self_stop_ecs.sh` 全 PASS（离线已验 9/9）
- [ ] 断网演练：本地机器关机/断网，训练正常结束后实例**仍自行 StopCharging**（看 `self_stop.log` 的 VERIFIED 行 + 云控制台 Stopped+StopCharging 回执）
- [ ] 误杀演练：训练中的评估间隙（低 CPU）**不触发**自停机（判据是心跳/进程退出，非 CPU）
- [ ] 回退演练：故意把 profile 名改错 → watchdog 应回退 OS poweroff，且本地 closer 补 API 停机（双保险）
- [ ] 物理零回归：同 ckpt 同 seed 复跑 peak 逐位一致（自停机不改物理/训练，此项应天然通过）

## 验证协议（2026-11-18 12:14 事故后新增，硬约束）

**事故**：对训练实例带真实参数跑 1min deadline 的 closer 验证 → deadline 兜底真实停机，
葬送进行中的训练（ep6/40，77 分钟机时报废）。owner 明确要求：验证不得再动训练实例的账。

**规则**：
1. **凡验证 closer 逻辑，一律 `--dry-run`**：完整走轮询 / ssh 探测 / 触发判定 / 产物回传
   链路，但跳过 StopInstance API。零成本，覆盖除"真停机"外的全部路径。
2. 需要验证**真实停机路径**时（极少，仅 StopInstance 语义变更才需要）：用
   `instance_state_aliyun_ecs.py` 的 stop 路径早已反复验证过 StopCharging 语义，
   默认不再单独开实例；确需开时**只准开最便宜规格**（按量最小型），几分钟内关停并贴回执，
   不得在训练实例上做任何会改变实例状态的实验。
3. 本地 mock（`tests/test_cover_quick_eval_watch.sh` 等）优先于一切真机验证。

## 与现有机制的关系（迁移期）

- **本地 closer 保留**：`scripts/cloud/closer_aliyun_ecs.py` + schtasks 仍注册，作为第二道（实例内自停机失败时补位）。G1 第 6 问"closer 在位"继续按本地 closer 判。
- **不删本地 AK**：迁移期本地仍需 AK 跑 closer/instance_state；云上侧已免 AK。待 owner 另批才考虑收紧本地凭据。
- **判据不变**：三结局（心跳超时/进程退出+exit_code/无退出码）+ 硬 deadline，与铁律 12 一致；只是执行点从"本地轮询"扩展为"实例内自停 + 云端硬顶 + 本地补位"三层。

## 失败标记立即停机（2026-11-18 nincr ep10 实弹补，**必填项**）

**缺口复盘**：ep10 快评 BREAK 后，快评脚本只调实例内 `self_stop_ecs.sh`——云端 RAM 角色/CLI 未部署 ⇒ `FAIL CLI_MISSING` ⇒ 训练继续跑、实例继续计费，直到人发现（多烧 ≈2 分钟）。同轮 watchdog 在无退出码死亡路径写 `DEAD_*.txt` 后 OS poweroff（**按量实例 OS 关机不等于节省停机，仍计费**），而本地 closer 只认 exit_code/exit pattern/deadline，看到 DEAD 标记也一直空等到点。

**闭环（现在起强制）**：

1. 快评 BREAK 分支：写 `BREAK_LINE.txt` → 调 self_stop → **pkill run_training.py 兜底**（self_stop 成功时为无害空操作）；bootstrap 捕获退出码落 `exit_code.txt` + `train_rc=` 台账行。
2. 本地 closer（wrapper 模板 `scripts/cloud/run_w4nincr_closer.ps1`）：除 `--marker`/`--log`/deadline 外，**必须传** `--abort-glob <run_tag目录>/BREAK_LINE.txt` 与 `--abort-glob '<run_tag目录>/DEAD_*.txt'`，轮询命中任一 ⇒ 先拉产物再 API 停机（StopCharging + 回执复核）。轮询间隔建议 `--poll-s 120`（默认 300 s 时最坏多烧 5 分钟）。
3. 触发器单测 `tests/test_closer_trigger.py`（9/9，含"ssh 不可达永不触发"和"退出码行数不足不触发"两条误杀红线）+ `tests/test_cover_quick_eval_watch.sh`（7/7，含 BREAK 后 pkill 兜底与 ep5 不误杀）为开训前必跑项。

**依赖结构诚实标注**：云端 RAM 角色/aliyun CLI/OOS 硬顶在 owner 批准前均未部署，实例内自停机路径全部为死路径；**当前唯一可靠的停费机制 = 本地 closer 的 API stop**。因此开训前 closer 注册（G1 第 6 问）+ abort-glob 参数完整性是硬前置；OS poweroff 只能止血不能停费，不得当作收账完成。

补充：实例内 watchdog 在 self_stop 失败后已**取消 OS poweroff 回退**（按量实例 OS 关机不停费，且 ssh 断让 closer 读不到标记），改为保持 OS 存活等本地 closer 读标记 → API 停机复核（mock 单测 `tests/test_instance_watchdog_no_poweroff.sh` 4/4）。
