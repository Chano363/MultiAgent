***

title: 云服务器操作规范（远程算力采购 / 开通 / 训练托管 / 关机复核）
date: 2026-10-22
status: active
owner: Owner
supersedes: 新建（首次系统性沉淀；原散落在会话中的云主机操作经验迁入本文件）
----------------------------------------------------

# 云服务器操作规范（SERVER_OPS）

> **适用**：任何"在远程服务器/云主机上跑本项目代码"的操作——选型、开通、装环境、传代码、跑训练、回收。
> **何时读**：动手前**必读**；AGENTS.md 已将其列为服务器操作的强制前置。
> **不适用**：本机 WSL 的日常开发（见 AGENTS.md「Environment」与 `EXECUTION_RULES.md`）。

> **边界声明**：本文件只规定**怎么安全省钱地用服务器**，**不规定训练口径**
> （集数 / 每集步数 / n_env / 奖励权重等）。训练口径仍处于讨论与验证中，
> 以 Owner 的明确指令与 `docs/logs/decisions/DECISIONS.md` 的 ADR 为准，
> **任何配置文件里的注释都不构成本文件的依据**。

---

## 一、八条铁律（违反任一条即判操作失败）

| # | 铁律 | 原因 / 后果 |
|---|---|---|
| 1 | **最省钱原则：能本地做的绝不上服务器** | 诊断、调参、冒烟、出图、评估一律本地跑（免费）。服务器**只跑产出论文资产的正式训练**（有 metadata、checkpoint、结果 JSON）。在服务器上做诊断 = 纯烧钱 |
| 2 | **凭据不进对话、不进 git** | AK/密码一旦贴聊天记录即视为泄露，须当天轮换。AK 只写 `~/.aliyun_ak.txt`（工作区外），脚本从文件读 |
| 3 | **按量付费 + 节省停机模式，禁包年包月** | 按分钟计费、随开随停；本项目是"短时突发 + 大量空档"的形态，包月只会产生沉没成本 |
| 4 | **跑完就关机，不释放** | `StoppedMode=StopCharging` 下关机**不收 vCPU/内存费，但磁盘照收**：ESSD PL0 40 GiB 实查 **0.084 元/小时 ≈ 2 元/天 ≈ 60 元/月**。短期（≤1 周）保留；长期不用应「做镜像后释放」 |
| 5 | **关机必须二次复核** | 单次 `StopInstance` 调用**不算关机完成**。必须回查 `Status=Stopped` 且 `StoppedMode=StopCharging`，并把回执贴出来（见 §十一） |
| 6 | **物理核才是并行上限，vCPU 要÷2** | 超线程实测收益仅 +5%（N=8→10）。"32 vCPU"实际只有 16 核可用 |
| 7 | **首跑必须实测 s/ep 再决定租期** | 任何估算都不可信（见 §七）；未校准就长租 = 烧钱 |
| 8 | **两侧物理同源** | 服务器与本地必须是同一份代码、同一物理配置；禁"一边改物理一边对比" |

---

## 二、开通前检查清单

动手前逐项确认，**任何一项不满足都不要下单**：

- [ ] **实名认证**完成（未认证无法创建 ECS）
- [ ] **按量付费已开通**，账户「**现金余额 + 代金券**」总值 **≥ 100 元**
      （阿里云官方硬门槛，见 ECS「使用限制」；不足则无法创建按量实例，可提交工单申请提升限额。
      官方口径仅约束「创建按量付费资源时」，其他操作是否同样校验**不以推断代替核实**）
- [ ] **RAM 子账号权限**齐备（见下表），**不要用主账号 AK**
- [ ] **目标规格在该地域有库存**（用 `probe_aliyun_ecs.py` 查，不要只看控制台一个地域）
- [ ] **SSH 密钥对**已在本机生成（`~/.ssh/cloud_traffic`，ed25519，无口令）
- [ ] 明确本轮**预算上限**与**停机点**

### RAM 最小权限集（阿里云）

| 策略 | 用途 | 必需 |
|---|---|---|
| `AliyunECSFullAccess` | 实例/安全组/密钥对/镜像/询价 | ✅ |
| `AliyunVPCFullAccess` | **CreateVpc / CreateVSwitch**（新地域必用） | ✅ |
| `AliyunBSSReadOnlyAccess` | 查余额、账单 | 建议 |

> 坑：`AliyunECSFullAccess` **不含** VPC 写权限，`CreateVpc` 会返回 `Forbidden.RAM`。

---

## 三、规格选择

### 3.1 硬性排除项

| 排除 | 原因 |
|---|---|
| **突发性能型 t 系列 / 共享型** | CPU 积分耗尽后频率砍到基准 10~20%，训练凭空慢 5~10 倍，且日志看不出异常 |
| **GPU 机型** | 本项目瓶颈是 CPU 串行物理步进；实测策略前向/PPO 更新在 GPU 上**比 CPU 慢 4~8 倍**（小 batch） |
| **u1 等老 Xeon（2.5 GHz）** | 单价看似低，但单核性能差 30~40%，有效核时成本更高 |
| **包年包月** | 见铁律 3 |

### 3.2 买多大：不做预设，按实测反推

每个训练进程占 1 个物理核；`n_env_parallel=true` 时单个 seed 需要 `n_env` 个 worker + 1 个父进程。

**不要在文档里找"该买 8 核还是 32 核"的答案**——正确顺序是：

1. 先在**本地**把训练口径与配置确认清楚（口径未定就上服务器 = 白烧钱）
2. 上服务器后先跑 §七 的 s/ep 校准
3. 用 `核时 = 集数 × 每集步数 × 单步耗时 ÷ worker 数` 与 `墙钟 = 核时 ÷ 物理核数` 反推需要几台、多大

### 3.3 库存查询（必用脚本，不要一页页翻控制台）

```sh
# 列出该地域所有按量可用规格 + 单价（只读，不下单）
python scripts/cloud/probe_aliyun_ecs.py cn-heyuan --min-cpu 8 --price
python scripts/cloud/probe_aliyun_ecs.py cn-wulanchabu --min-cpu 16
```

热门地域（华北2北京 / 华东1杭州）大规格常年售罄，**优先试冷门地域**：华南2河源、华北6乌兰察布、华北3张家口、西北2中卫、西南1成都。

---

## 四、计费与成本控制

| 项 | 规范 |
|---|---|
| 计费模式 | `InstanceChargeType=PostPaid` + `StoppedMode=StopCharging` |
| 公网 | `InternetChargeType=PayByTraffic`（按流量），**不要买固定带宽** |
| 系统盘 | ESSD PL0 40 GiB 足够（代码 + 环境 + checkpoint 均很小） |
| 数据盘 | 与系统盘分离，关机保留 |
| 充值 | 按官方 ≥100 元门槛与实际进度**分批充**，不一次压大额 |

**成本口径**：`核时 = 集数 × 每集步数 × 单步耗时 ÷ worker 数`，`费用 = 墙钟 × 单价`。
写论文排期时必须用**实测**数值替换，不得沿用任何文档里的旧估算。

> 按量 vs 包年的差价随机型与活动浮动，**不在文档里记死数字**；
> 下单前用 `probe_aliyun_ecs.py --price` 取实时价按需对比。

---

## 五、凭据与密钥管理

```sh
# AK（工作区外，禁止提交 git）
~/.aliyun_ak.txt        第 1 行 AccessKeyId / 第 2 行 Secret / 第 3 行（可选）默认地域

# SSH 密钥（ed25519，无口令，仅用于本项目云主机）
~/.ssh/cloud_traffic        私钥（绝不外传、绝不打印）
~/.ssh/cloud_traffic.pub    公钥（可粘贴到云控制台或由脚本 ImportKeyPair 导入）
```

- **禁止**把私钥内容、AK、账户密码贴进任何对话/issue/文档。
- AK 用完（或发现已泄露）**当天在 RAM 控制台禁用并删除**，不要"以后再清"。
- WSL 访问 `/mnt/c` 的私钥权限恒为 0777，SSH 会拒绝 → 先 `cp` 到 `~/.ssh/` 并 `chmod 600`。

---

## 六、一键开通（推荐路径）

```sh
# 只检查依赖、建免费网络资源、打印下单参数（不产生费用）
python scripts/cloud/provision_aliyun_ecs.py --dry-run

# 真正开通（开始计费）
python scripts/cloud/provision_aliyun_ecs.py --type <实例规格>
```

脚本行为（幂等，重复运行不会重复建资源）：

1. 建/复用 VPC `traffic-rl-vpc`(10.0.0.0/8) + 交换机 `10.0.1.0/24`（指定可用区）
2. 导入公钥为密钥对 `cloud_traffic`
3. 建/复用安全组 `traffic-rl-sg`，**只放行 TCP 22，源限本机公网出口 IP/32**（自动探测）
4. `RunInstances`：Ubuntu 24.04 + ESSD 40G + 按量 + 节省停机 + 按流量公网
5. 轮询至 Running 并打印公网 IP 与 SSH 命令

---

## 七、首跑校准（**必做，不可跳过**）

绝对耗时在不同机器上可差 3~5 倍，**任何估算都不能替代真机实测**。
校准用**当前确定的实验配置**（不要用文档里的示例配置名，配置口径以 Owner 指令为准）：

```sh
python run_training.py --experiment configs/experiments/<当前确定的配置>.yaml \
  --seed 0 --episodes 2 --override device=cpu \
  --checkpoint_dir outputs/smoke/cloud/ckpt \
  --results_dir outputs/smoke/cloud/results \
  --override dirs.figures_dir=outputs/smoke/cloud/figures
```

判据（不设人为阈值，按实际情况判断）：

- 实测明显比预期慢 → **停机改配或先做代码侧优化，不要硬跑**
- 实测明显比预期快 → 降配省钱
- 冒烟时必须同时检查**物理指标是否正常**（车钩力峰值 / 超限步数 / 速度带占比）。**物理崩坏的冒烟不得用来估算机时**——崩坏状态下安全层每步重算 ETCS 曲线，会把单步耗时放大 5~6 倍
- 拿到结论后**立即关机**，不要开着机器等决策

---

## 八、环境搭建标准流程

```sh
apt update && apt install -y build-essential git tmux htop rsync curl
curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/mc.sh
bash /tmp/mc.sh -b -p /root/miniconda3
source /root/miniconda3/etc/profile.d/conda.sh
conda create -y -n traffic_rl python=3.10
conda activate traffic_rl

# 关键：装 CPU 版 torch（省内存、避免无谓 CUDA 上下文）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu
pip install -r requirements.txt      # 含 numba（车钩力 JIT 内核）
pip install pytest                   # requirements.txt 未包含，但跑测试要
```

> 新版 conda 需先接受 Anaconda 频道 ToS，否则非交互 `conda create` 报 `CondaToSNonInteractiveError`：
> `conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main`

### 8.1 numba 编译缓存预热（并行前必做）

`train.py` 的车钩力内核为 `njit(cache=True)`。多个 worker **同时**首次编译会互相抢缓存锁、并让首集慢数十秒。标准做法：

```sh
# 先单进程跑一次，把编译产物写进 __pycache__
python -c "import src.train_dynamics.train as t; print('numba', t._HAS_NUMBA)"
python run_training.py ... --episodes 1 --override n_env=1 --override n_env_parallel=false
# 再启动正式的并行训练
```

若 numba 装不上，设 `TRAIN_RL_NO_NUMBA=1` 回退 numpy 分支（数值等价，慢约 16%）。

---

## 九、代码上传规范

```sh
# 在本机 WSL 执行；必须排除产物与凭据
rsync -avz --progress \
  --exclude 'outputs/' --exclude '.git/' --exclude '__pycache__/' \
  --exclude '*.pyc' --exclude '.codebuddy/' \
  /mnt/d/Code/MultiAgent/traffic_rl_project/ root@<IP>:/root/traffic_rl_project/
```

- **禁止**整包上传 `outputs/`（历史产物可达数 GB，且会污染云端"最新=权威"的判断）。
- 需要历史 checkpoint 续训时，单独 `scp` 那几个 `.pt`。
- 排除 `outputs/` 后，部分「历史归档一致性」测试会因缺文件失败（`FileNotFoundError: outputs/sim_validation/...`）——那是**预期行为**，不代表代码有问题；这类测试在本地跑。
- `.codebuddy/` 含 API key（已 gitignore），**任何情况下不上传**。

---

## 十、训练启动规范

```sh
tmux new -s train
conda activate traffic_rl && cd /root/traffic_rl_project
mkdir -p outputs/logs/cloud

for s in 0 1 2 3 4; do
  python run_training.py --experiment configs/experiments/<当前确定的配置>.yaml \
    --seed $s --episodes <N> --override device=cpu \
    --override n_env_parallel=true \
    --checkpoint_dir outputs/checkpoints/<run>/seed$s \
    --results_dir    outputs/checkpoints/<run>/seed$s/results \
    --override dirs.figures_dir=outputs/checkpoints/<run>/seed$s/figures \
    > outputs/logs/cloud/seed$s.log 2>&1 &
done
wait
```

强制项：

1. **`--override device=cpu`**：`ExperimentConfig.device=None` 会自动选 cuda，若有 GPU 会切过去且更慢。
2. **三个输出目录同时重定向**（`--checkpoint_dir` / `--results_dir` / `dirs.figures_dir`），否则会覆写历史产物（LRN-20261001-009）。
3. **`n_env_parallel=true`** 才真正用满多核；否则 `n_env=4` 是单核串行循环。
4. 用 `tmux` 保活，断开 SSH 不中断；日志块缓冲属正常，判活用 `tail + ps -o etime,pcpu`。
5. 集数 / 每集步数等**训练口径以 Owner 指令为准**，本文档不提供默认值。

---

## 十一、产物回收与关机（**含二次复核**）

```sh
# 1) 关键产物拉回本机（results / metadata / checkpoint / 日志）
rsync -avz root@<IP>:/root/traffic_rl_project/outputs/checkpoints/<run>/ \
  /mnt/d/Code/MultiAgent/traffic_rl_project/outputs/checkpoints/<run>_cloud/

# 2) 确认没有后台任务
tmux ls; pgrep -af run_training.py

# 3) 关机（不释放，保留环境与磁盘）
python scripts/cloud/instance_state_aliyun_ecs.py --stop <InstanceId>
```

**第 4 步不可省——二次复核**：

```sh
# 回查状态，必须看到 Status=Stopped 且 StoppedMode=StopCharging
python scripts/cloud/instance_state_aliyun_ecs.py <InstanceId>
```

复核同时要确认：

- `Status = Stopped`
- `StoppedMode = StopCharging`（否则关机仍在收计算费）
- 公网 IP 已释放（`PublicIp = []`）
- 把上述回执贴进对话/日志，作为"已停费"的证据

> 只发一次 `StopInstance` 就宣称"已关机"= 违规（可能是 Stopping 中间态，或 ForceStop 失败）。

---

## 十二、已知坑速查（均为实测复现）

| 现象 | 根因 | 处置 |
|---|---|---|
| `InvalidOperation.NotSupportedEndpoint` | ECS API endpoint 未带地域 | 用 `ecs.{region}.aliyuncs.com`，不要用 `ecs.aliyuncs.com` |
| `InvalidSystemDiskCategory.ValueNotSupported`（DescribePrice，如河源） | 询价未显式给系统盘类型 | 传 `SystemDisk.Category=cloud_essd` |
| `DescribeImages` 按 `ImageFamily` 过滤返回 0 | 该过滤参数不生效 | 用 `ImageOwnerAlias=system` 拉全量后本地按 `ImageId` 过滤 |
| `IncorrectVpcStatus`（CreateVSwitch 紧跟 CreateVpc） | VPC 创建后需数秒才 `Available` | 轮询 `DescribeVpcs` 直到 `Status=Available` |
| `CreateVpc` → `Forbidden.RAM` | ECS 权限不含 VPC 写权限 | 加 `AliyunVPCFullAccess` |
| `QueryAccountBalance` → `NotAuthorized` | 缺 BSS 权限 | 加 `AliyunBSSReadOnlyAccess`，或控制台自查 |
| `RunInstances` → `NotEnoughBalance` | 账户额度不足 | 充值（官方 ≥100 元门槛） |
| 大规格"无货" | 只看热门地域 | 换冷门地域 + 换规格族（c→c9i→g） |
| `conda create` → `CondaToSNonInteractiveError` | 新版 conda 需接受频道 ToS | `conda tos accept --override-channels --channel ...` |
| `ModuleNotFoundError: No module named 'gym'` | `requirements.txt` 曾缺 `gym`（代码 `from gym import spaces`） | 已补入 requirements；或 `pip install gym==0.26.2` |
| `ModuleNotFoundError: pytest` | requirements 未含测试依赖 | `pip install pytest` |
| SSH 拒绝私钥（Permissions 0777） | WSL 下 `/mnt/c` 权限无法收紧 | `cp` 到 `~/.ssh/` 后 `chmod 600` |
| PowerShell 调 WSL/SSH 报语法错误 | 多层引号转义 | 命令写进 `.sh` 文件再 `bash file.sh`（`sed -i 's/\r$//'` 去 CRLF） |
| 首集特别慢（数十秒） | numba 首次编译 + 多 worker 抢缓存锁 | 先单进程预热（§8.1） |
| 单步耗时忽快忽慢（3 倍波动） | 笔记本热降频 / 云主机噪声 | 只看 cProfile 相对比值；绝对耗时以服务器多次取最小值为准 |

> **诊断脚本陷阱**：`TrainFleetEnv` 的 `info` 里**没有** `speed` 键（只有单列 env 有）。
> 写 `info.get('speed', 0.0)` 会恒得 0，误判为"列车停住"；应读 `env.trains[i].dynamics.vel[0]`。

---

## 十三、禁止事项清单

1. **在服务器上做诊断/调参/冒烟**（只准跑正式训练，见铁律 1）。
2. 用主账号 AccessKey 操作云资源。
3. 把 AK / 私钥 / 密码写进对话、文档、commit、截图。
4. 只调一次 `StopInstance` 就宣称已关机（必须二次复核，见铁律 5）。
5. 为"省事"选包年包月，或让实例开着等决策。
6. 在训练口径未确定时开机试跑。
7. 改动 `n_env`、物理参数、奖励来"适配服务器"（两侧物理同源铁律）。
8. 整包同步 `outputs/` 或 `.codebuddy/`。
9. 绕过 `run_training.py` 用临时脚本在云端跑正式实验（metadata 缺失 → 结论不成立）。

---

> 本文件是**规范**，不承载实验数据；实测记录进 `docs/logs/diagnostics/DIAGNOSTICS_YYYY-MM.md`，
> 踩坑教训进 `docs/logs/learnings/LEARNINGS.md`，重大采购/架构决策进 `docs/logs/decisions/DECISIONS.md`。
