# 云端停费权限请求（2026-11-18，owner 口头"全部权限放开"后的 API 探测结果）

## 〇、授权总清单（先看这节：要什么角色 / 谁挂什么授权）

三层停费涉及 **1 个用户 + 2 个角色**。把它们的关系和每方需要的授权一次列清（下文第一至六节是探测过程与留痕）。

> **当前状态（2026-11-18 21:35）**：owner 已完成 RAM 授权 → `OOSServiceRole` 由 owner 控制台建好 → **OOS 硬顶已 arm 成功**（执行 `exec-ce9089bc4f674c789ee4`，Status=Waiting，deadline 2026-11-19T04:00:00Z = 12:00 北京时间，RamRole=OOSServiceRole）。下方表格中"❌"是授权前的历史快照，以本节状态为准。实例当前 Stopped+StopCharging。**本文件在 docs/ 根目录，不属于 rules/ 规则正本。**

### 0.1 要创建的两个角色

| 角色                                   | 用途                                   | 信任主体（谁能扮演它）            | 状态                 |
| ------------------------------------ | ------------------------------------ | ---------------------- | ------------------ |
| **`OOSServiceRole`**                 | OOS 定时执行"戴"它，到点调用 StopInstance 停训练实例 | 云服务 `oos.aliyuncs.com` | ✅ 已由 owner 控制台建好（21:29，信任策略核实为 oos.aliyuncs.com） |
| `ecs-training-selfstop`（可选，实例内自停启用时） | 绑到 ECS 实例，实例内免 AK 取 STS 凭证停自己        | 云服务 `ecs.aliyuncs.com` | ❌ 不存在（当前实例内自停未启用）  |

> 当前只**必须**建 `OOSServiceRole`——它是 OOS 云端硬顶的前提，也是"本地全死也停费"的唯一缺口。`ecs-training-selfstop` 属实例内自停机制（第三层增强），可在 OOS 硬顶跑通后再建。

### 0.2 每个角色要挂的授权（权限策略）

角色本身**没有权限**，建完必须挂策略；挂的策略决定"戴上这张工牌能干什么"。

| 角色                          | 挂什么权限策略                                                          | 内容                                         | 资源范围                                                                     |
| --------------------------- | ---------------------------------------------------------------- | ------------------------------------------ | ------------------------------------------------------------------------ |
| `OOSServiceRole`            | 自定义 `TrainingHardDeadlineMinimal`（或系统 `AliyunECSFullAccess` 图省事） | `ecs:StopInstance`、`ecs:DescribeInstances` | 限定到 `acs:ecs:cn-heyuan:1749554754126152:instance/i-f8zcp6vvis4rnztw0p9y` |
| `ecs-training-selfstop`（可选） | 同上的最小 ECS 停机策略                                                   | 同上两项                                       | 同上，限定目标实例                                                                |

最小权限策略 JSON（`TrainingHardDeadlineMinimal`，两个角色共用这一份）：

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ecs:StopInstance", "ecs:DescribeInstances"],
      "Resource": "acs:ecs:cn-heyuan:1749554754126152:instance/i-f8zcp6vvis4rnztw0p9y"
    }
  ]
}
```

角色信任策略 JSON（`OOSServiceRole`，创建角色时"信任主体类型=云服务 / 名称=OOS"即自动生成同款；脚本编辑时填）：

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Principal": {"Service": ["oos.aliyuncs.com"]},
      "Action": "sts:AssumeRole"
    }
  ]
}
```

（`ecs-training-selfstop` 把上面 `oos.aliyuncs.com` 换成 `ecs.aliyuncs.com`。）

### 0.3 用户 `ecs-ops` 要挂的授权（这个 AK 就是你手里的）

用户是"身份"，挂的策略决定**它能直接干什么、以及能不能把角色递给服务**。

| 授权                             | 类型    | 为什么需要                                          | 状态                    |
| ------------------------------ | ----- | ---------------------------------------------- | --------------------- |
| `AliyunOOSFullAccess`          | 系统策略  | 建 OOS 模板、启动/取消定时执行                             | ✅ 已挂（21:10 复验 200 OK） |
| ECS 读写（现有）                     | 已有    | closer 调 `StopInstance`/`DescribeInstances` 收账 | ✅ 已有                  |
| `TrainingRoleManager`（自定义，须补挂） | 自定义策略 | **建角色 + 给角色挂策略 + 把角色递给 OOS（PassRole）**         | ✅ 已挂（21:30 复验 RAM ListRoles=200，硬顶已 arm） |

必须补挂的自定义策略 JSON（`TrainingRoleManager`，命名可自定）：

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ram:CreateRole", "ram:GetRole", "ram:ListRoles",
                 "ram:CreatePolicy", "ram:AttachPolicyToRole",
                 "ram:ListRolePolicies", "ram:PassRole"],
      "Resource": "*"
    }
  ]
}
```

> **关键说明**：`ram:PassRole` 是核心——`StartExecution` 时调用者（`ecs-ops`）必须有权限把 `OOSServiceRole` 这个角色"传递"给 OOS 服务，否则即使角色存在也会报 `AssumeRoleNotExist`/无权限。上一节探测里这一步全 403，就是缺这条策略。上表用 `Resource: "*"` 是最省事写法；若要最小权限，可拆成两条——建/查/挂策略类限定到 `acs:ram:*:1749554754126152:role/OOSServiceRole`，`ram:PassRole` 单独限定到同一角色 ARN（提前写好角色名即可）。
>
> 若图省事：直接给用户挂系统策略 `AdministratorAccess`（含以上全部），但权限过宽，不推荐。

### 0.4 补挂完成后的动作链（我来做）

1. 复验 `ram:ListRoles` = 200；
2. 建 `OOSServiceRole` + 挂 `TrainingHardDeadlineMinimal`；
3. `oos_hard_deadline.py --arm` 建到点停机执行，实测进入 Waiting；
4. 用**已停机**的实例做一次到点停机回执验证（零成本、零风险，停机态重复 Stop 幂等）；
5. 把 arm/disarm 纳入窗口启动检查单（G1 第 6 问）。

## 一、探测事实（一手，2026-11-18 20:30）

用当前 AK（RAM 子账号 `ecs-ops`，主账号 1749554754126152）经 HTTPS + 区域端点实测：

| API                                    | 结果                        | 含义                             |
| -------------------------------------- | ------------------------- | ------------------------------ |
| ECS `DescribeInstances`                | 200 OK                    | 现有 ECS 读写权限（含 StopInstance）可用  |
| RAM `ListRoles`                        | **403 NoPermission**      | 不能建/查 RAM 角色 ⇒ 实例内免 AK 自停机无法部署 |
| OOS `ListTemplates` / `ListExecutions` | **401 User.NoPermission** | 不能建 OOS 模板/定时执行 ⇒ 云端硬顶无法部署     |

"放开全部权限"目前只在对话层生效；**阿里云 RAM 控制台给子账号挂的策略没变**，所以 API 层仍然 403/401。这一步我无法从本地自助提权（提权本身就要 RAM 权限）。

## 二、请你在 RAM 控制台做一次（约 2 分钟）

RAM 控制台 → 身份管理 → 用户 → `ecs-ops` → 权限管理 → **新增授权**，挂两条：

1. 系统策略：**`AliyunOOSFullAccess`**（OOS 模板/定时执行/执行历史的读写）
2. 自定义策略（角色管理最小权限，命名如 `TrainingSelfStopRoleManager`）：

```json
{
  "Version": "1",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": ["ram:CreateRole", "ram:GetRole", "ram:ListRoles",
                 "ram:CreatePolicy", "ram:AttachPolicyToRole",
                 "ram:DetachPolicyFromRole", "ram:ListRolePolicies"],
      "Resource": ["acs:ram:*:1749554754126152:role/ecs-training-selfstop",
                   "acs:ram:*:1749554754126152:policy/TrainingSelfStopMinimal"]
    }
  ]
}
```

> 若你更省事，临时挂 `AdministratorAccess` 也行——但**推荐最小权限**，脚本用完不会碰其他资源。授权完成后回一句"加好了"，我用同一探测脚本复验 200 OK 再继续。

## 三、权限到位后我全自动化的三件（无需你再点控制台）

1. **实例内免 AK 自停机**：建角色 `ecs-training-selfstop`（信任 ECS、最小权限只含 `ecs:StopInstance`/`ecs:DescribeInstances` 且资源限定目标实例）→ 绑实例 → 开机后装 aliyun CLI ≥3.3.0 → `aliyun configure --mode EcsRamRole --profile ecs-self` → 实测能 `StopInstance` 自己。AK 明文不进云盘（云上只有 STS 临时凭证自动轮换）。
2. **OOS 云端硬顶**：用 `oos_hard_deadline_template.yml` 建模板；**每次开窗自动创建一次性定时执行**（deadline = 开机 + 本次预算墙钟，如 +7 h），训练收工后自动删除。这一层不依赖本地 Windows、不依赖实例内 CLI——即使 WorkBuddy 与本地机器全死，到点云端自己 StopCharging。
3. **开机自检脚本化**：把以上两步纳入窗口启动检查单（G1 第 6 问）：角色凭证可用 + OOS 任务已建 + 本地双活 closer 心跳 rc=0，三者齐才开机。

## 四、不依赖云权限的本地冗余已先做完（2026-11-18）

- `closer_wrapper_resilient.ps1`：**崩溃自愈**（python 非正常退出 20 s 后重启，deadline 按绝对时刻重算——崩溃不能延长计费窗口）；**只在 self-log 出现 CLOSEOUT_OK 才退出**，未确认 StopCharging 绝不收工。
- `register_closer_pair.ps1`：一次注册 **primary + backup 双活**计划任务，共用配置、各自独立心跳/产物目录；`stop_instance()` 幂等（已停费直接成功），任一存活即可收账。
- `closer_aliyun_ecs.py`：`--abort-glob` 失败标记触发 + 停机未确认时持续重试（不收工）。
- 实机 dry-run 演练：双任务并行心跳、手动杀 primary python → 20 s 自愈且剩余 deadline 从 2 min 重算为 1 min、两者最终 CLOSEOUT_OK 退出（演练任务已清理）。单测 13/13 + 机制缺口 20 项全绿。

## 五、目标状态

三层停费：**实例内自停机（主）→ OOS 云端硬顶（中）→ 本地双活 closer（辅）**。任意一层独立都能 StopCharging + 回执复核；本地会话/机器全死也不烧钱。

## 六、2026-11-18 21:10 复验结果（owner 说"已完成授权"后实测）

| 探测                                                           | 结果                      | 结论                           |
| ------------------------------------------------------------ | ----------------------- | ---------------------------- |
| OOS `ListTemplates`/`ListExecutions`                         | **200 OK**              | `AliyunOOSFullAccess` 已挂成功 ✅ |
| RAM `ListRoles`/`GetRole`/`CreateRole`/`ListPoliciesForUser` | **全部 403 NoPermission** | 自定义 RAM 策略**没挂上/没生效** ❌      |

**已部署产物**：OOS 模板 `TrainingHardDeadlineStop`（t-b4040f69606f4734aba3，TimerTrigger(at) + ACS::ECS::StopInstance stoppedMode=StopCharging）已建好；脚本 `scripts/cloud/oos_hard_deadline.py` 就绪（arm/disarm/list/dry-run 全实现）。

**但 arm 实测失败，根因链条（三步一手实证）**：

1. `StartExecution` 指定模板名 → `AssumeRoleNotExist: role/OOSServiceRole`（账号从没用过 OOS，该角色不存在）；
2. 去掉 RamRole 用内联 `TemplateContent` → `TemplateValidationError: RamRole property is required in trigger template`（**OOS 平台硬约束**：含 TimerTrigger 的模板必须带 RamRole，无绕开路径）；
3. 试 API 建角色（CreateRole/GetRole/ListRoles）→ **全部 RAM 403** ⇒ 建不了角色 ⇒ OOS 硬顶暂时无法 arm。

**结论**：`AliyunOOSFullAccess` 到位了，但**缺的是 RAM 角色管理权限**。请补挂下面任一项（推荐第 1 项，最小权限）：

1. 自定义策略给 `ecs-ops` 增加：`ram:CreateRole`、`ram:GetRole`、`ram:CreatePolicy`、`ram:AttachPolicyToRole`、`ram:PassRole`，资源 `acs:ram:*:1749554754126152:role/OOSServiceRole`（`PassRole` 是关键——StartExecution 时调用者必须能传递角色给 OOS）；
2. 或直接给 `ecs-ops` 挂 `AdministratorAccess`（最省事，但权限过宽）。

挂完回一句"补好了"，我复验 ListRoles=200 → 建 `OOSServiceRole`（信任 oos.aliyuncs.com，最小权限 ECS Stop+Describe）→ arm 硬顶执行 → 实测 Waiting 状态 + 到点 StopCharging 回执（用已停机实例验证，零成本零风险）。

**当前状态**：本地双活 closer（primary/backup + 崩溃自愈 + 幂等停机）仍是唯一可靠停费机制，实例已停机（Stopped+StopCharging），不烧钱；云端硬顶是"再上一层保险",未 arm 不影响当前安全。
