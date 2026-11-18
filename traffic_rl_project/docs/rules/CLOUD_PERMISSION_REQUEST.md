# 云端停费权限请求（2026-11-18，owner 口头"全部权限放开"后的 API 探测结果）

## 一、探测事实（一手，2026-11-18 20:30）

用当前 AK（RAM 子账号 `ecs-ops`，主账号 1749554754126152）经 HTTPS + 区域端点实测：

| API | 结果 | 含义 |
|---|---|---|
| ECS `DescribeInstances` | 200 OK | 现有 ECS 读写权限（含 StopInstance）可用 |
| RAM `ListRoles` | **403 NoPermission** | 不能建/查 RAM 角色 ⇒ 实例内免 AK 自停机无法部署 |
| OOS `ListTemplates` / `ListExecutions` | **401 User.NoPermission** | 不能建 OOS 模板/定时执行 ⇒ 云端硬顶无法部署 |

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
