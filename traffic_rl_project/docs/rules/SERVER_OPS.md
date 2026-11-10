***

title: 云服务器操作手册（本机环境 / 命令 / 凭据 / 计费 / 释放）
date: 2026-10-23
updated: 2026-11-08
status: active
owner: Owner
supersedes: 新建（原散落在会话中的云主机操作经验迁入；2026-11-08 按实测补全本机环境、资源台账与释放全流程）
----------------------------------------------------

# 云服务器操作手册（SERVER_OPS）

> **适用**：所有涉及远程服务器 / 云主机的操作——查库存、开通、装环境、传代码、跑训练、回收、释放。
> **边界**：本文件只规定**怎么安全省钱地用服务器**，**不规定训练口径**（集数 / 每集步数 / `n_env` / 奖励权重）。
> 训练口径以 Owner 明确指令与 `docs/logs/decisions/DECISIONS.md` 的 ADR 为准，**配置文件注释不构成本文件依据**。

---

## 零、按场景速查（先看这里）

| 我要做什么 | 去 §几 | 一句话 |
|---|---|---|
| 机器关了，要接着跑训练 | **§六** | 一条 `provision --image` 命令，1 分钟到位 |
| 不知道自己还有哪些资源在花钱 | **§三** | `inventory_aliyun_ecs.py --cost` |
| 暂时不用，先省点钱 | **§十三.1** | 只关机：约 2 元/天 |
| 长期不用（>1 周） | **§十三.2** | 打镜像 → 释放：约 5.5 元/月 |
| 彻底不做了 | **§十三.3** | 按顺序删：实例→镜像→快照→安全组→交换机→VPC→密钥对 |
| 第一次从零开一台 | **§七** | 权限检查 → dry-run → 开通 |
| 开机后环境坏了 | **§八** | 重装（约 20 分钟）或改用镜像重开 |

---

## 一、十条铁律

| # | 铁律 | 原因 / 后果 |
|---|---|---|
| 1 | **最省钱原则：能本地做的绝不上服务器** | 诊断、调参、冒烟、出图、评估一律本地（免费）。服务器**只跑产出论文资产的正式训练** |
| 2 | **凭据不进对话、不进 git** | AK 写 `C:\Users\chano\.aliyun_ak.txt`（工作区外）；贴过对话就当泄露，当天轮换 |
| 3 | **按量付费 + 节省停机，禁包年包月** | 本项目是"短时突发 + 大量空档"，包月只有空转时才划算 |
| 4 | **跑完就关机；长期不用则镜像化后释放** | 关机只收磁盘（实查 **0.084 元/h ≈ 2 元/天**）；镜像化后约 5.5 元/月 |
| 5 | **关机/释放必须二次复核** | 单次 `StopInstance` 不算数，必须回查 `Status=Stopped` + `StoppedMode=StopCharging` 并贴回执 |
| 6 | **物理核 = vCPU ÷ 2** | 超线程实测收益仅 +5%；"32 vCPU"只有 16 核可用 |
| 7 | **首跑必须实测 s/ep 再决定租期** | 任何估算都不能替代真机实测（§十） |
| 8 | **两侧物理同源** | 服务器与本地同一份代码、同一物理配置；禁"一边改物理一边对比" |
| 9 | **云上长任务/watchdog 先演练再上线** | 判活自指、保真参数错配、产物判据过浅——2026-11-09 一天烧 12 元学费，清单见 §15.1；演练不过不上线 |
| 10 | **开实例前必须过用户审批（2026-11-10 用户硬约束）** | 云服务器（阿里云或任何实例）**只在正式规模训练那一步**、且用户**明确批复规格与预算**之后才能开。开之前必须先给出：**实例规格 / 单价 / 预估总价 / 预计墙钟**。**询价、probe、试开实例一律算需要审批**，禁止自行发起。违反 = 未经授权的付费动作 |

---

## 二、本机环境清单（2026-11-08 实测）

| 组件 | 实测值 | 用途 | 验证命令（PowerShell） |
|---|---|---|---|
| **Windows OpenSSH** | `OpenSSH_for_Windows_9.5p2` | 连服务器、`scp` 传文件 | `ssh -V` |
| **WSL 发行版** | `Ubuntu-24.04`（WSL 2，默认发行版） | 跑项目、`rsync` | `wsl -l -v` |
| **conda 环境** | `traffic_rl`（Python 3.10） | 项目依赖 | `wsl -d Ubuntu-24.04 -e bash -lc "conda activate traffic_rl && python -V"` |
| **Windows Anaconda** | `D:\Anaconda\python.exe`（Python 3.13） | 跑云 API 脚本（已装 `aliyun-python-sdk-ecs`） | `D:\Anaconda\python.exe -c "import aliyunsdkecs"` |
| **SSH 私钥** | `C:\Users\chano\.ssh\cloud_traffic`（399 B，ed25519） | 登录云主机 | `Get-ChildItem $env:USERPROFILE\.ssh\cloud_traffic*` |
| **SSH 公钥** | `C:\Users\chano\.ssh\cloud_traffic.pub`（93 B） | 导入云平台密钥对 | 同上 |
| **WSL 侧密钥副本** | `~/.ssh/cloud_traffic`（chmod 600） | 给 WSL 里的 `rsync` 用 | `wsl -d Ubuntu-24.04 -e ls -l ~/.ssh/cloud_traffic` |
| **阿里云 AK 文件** | `C:\Users\chano\.aliyun_ak.txt`（2 行 58 B，2026-11-08 实测存在；**在工作区外，换机 / 重装系统 / 换用户后须手工重建**，git 里没有备份） | 所有云脚本读取 | `(Get-Content $env:USERPROFILE\.aliyun_ak.txt).Count`（应得 2） |
| **项目路径（Windows）** | `d:\Code\MultiAgent\traffic_rl_project` | — | — |
| **项目路径（WSL）** | `/mnt/d/Code/MultiAgent/traffic_rl_project` | — | — |

### 2.1 一个必须知道的坑：私钥不能从 `/mnt/c` 直接给 WSL 用

WSL 访问 Windows 盘的权限恒为 `0777`，SSH 会拒绝（`UNPROTECTED PRIVATE KEY FILE`）。所以 WSL 侧要单独复制一份：

```sh
# WSL 内执行一次即可
mkdir -p ~/.ssh && cp -f /mnt/c/Users/chano/.ssh/cloud_traffic ~/.ssh/cloud_traffic && chmod 600 ~/.ssh/cloud_traffic
```

Windows 侧 `ssh` 直接读 `C:\Users\chano\.ssh\cloud_traffic` 没问题，不需要这一步。

### 2.2 云脚本清单（`traffic_rl_project/scripts/cloud/`）

| 脚本 | 作用 | 是否产生费用 |
|---|---|---|
| `inventory_aliyun_ecs.py` | **资源全景盘点**（实例/镜像/快照/VPC/安全组/密钥对 + 费用估算） | 只读，免费 |
| `probe_aliyun_ecs.py` | 查某地域**有货规格 + 实时单价** | 只读，免费 |
| `preflight_aliyun_ecs.py` | 下单前检查 VPC/交换机/安全组/密钥对/镜像是否齐备 | 只读，免费 |
| `provision_aliyun_ecs.py` | **一键开通**（幂等：建 VPC/交换机/安全组/密钥对 + RunInstances） | **下单后开始计费** |
| `instance_state_aliyun_ecs.py` | 查状态 / 停止 / **二次复核** / 释放 | 停止/释放无额外费用 |
| `probe_tencent_cvm.py` | 腾讯云备选（同 probe 用途） | 免费 |

全部用 `D:\Anaconda\python.exe` 跑（Windows 侧），**不需要进 WSL**。

---

## 三、云资源台账（2026-11-08 实测）

跑 `D:\Anaconda\python.exe scripts\cloud\inventory_aliyun_ecs.py --cost` 可随时刷新下表。

| 资源 | ID | 状态 | 计费 |
|:--|:--|:--|:--|
| **自定义镜像** | **`m-f8z1kh9ph7am18g02bra`**（`traffic-rl-ubuntu2404-20261023`） | Available / 40 GiB | 按快照数据量，**上限 5.5 元/月** |
| **快照**（镜像底层） | `s-f8z1kh9ph7am18g7fqoi`（`Created_from_i-f8z3gn50g75e532qiqz9`） | accomplished | 同上（镜像引用它） |
| **VPC** | `vpc-f8z998xwzr56x79vxdvc9`（`traffic-rl-vpc`，10.0.0.0/8） | Available | 免费 |
| **交换机** | `vsw-f8zdnovt921s93f70o9us`（`traffic-rl-vsw`，10.0.1.0/24 @ `cn-heyuan-c`） | 可用 | 免费 |
| **安全组** | `sg-f8z5ncw5tu8zqy0cz4iy`（`traffic-rl-sg`，仅放行 22/22） | 可用 | 免费 |
| **密钥对** | `cloud_traffic`（指纹 `a46e525f880ca7321ad39dbd1a38c0d6`） | 可用 | 免费 |
| **ECS 实例** | 原 `i-f8z3gn50g75e532qiqz9` | **已于 2026-10-23 释放** | **0** |
| **地域 / 可用区** | `cn-heyuan` / `cn-heyuan-c`（华南2 河源） | — | — |

> **当前每小时 ≈ 0 元、每月 ≈ 5.5 元（上限）**，只有镜像/快照在计费。
> VPC、交换机、安全组、密钥对都是免费资源，留着不影响费用，下次开机能直接复用。

---

## 四、凭据与密钥

### 4.1 阿里云 AccessKey

```
C:\Users\chano\.aliyun_ak.txt
第 1 行  AccessKeyId
第 2 行  AccessKeySecret
第 3 行  （可选）默认地域，如 cn-heyuan；不写则脚本默认 cn-heyuan
```

- 用 **RAM 子用户**（当前 `ecs-ops`），**不要用主账号 AK**。
- 权限集：`AliyunECSFullAccess`（实例/安全组/密钥对/镜像/询价/下单）+ `AliyunVPCFullAccess`（建 VPC/交换机）+ 可选 `AliyunBSSReadOnlyAccess`（查余额账单）。
- **轮换**：RAM 控制台 → 用户 → 创建新 AK → 覆盖写入文件 → 验证脚本能跑 → 删旧 AK。
- 文件权限建议：`icacls "$env:USERPROFILE\.aliyun_ak.txt" /inheritance:r /grant:r "$env:USERNAME:(R)"`

### 4.2 SSH 密钥

```
C:\Users\chano\.ssh\cloud_traffic       私钥（399 B，ed25519，无口令）—— 绝不外传、绝不打印
C:\Users\chano\.ssh\cloud_traffic.pub   公钥（93 B）—— 可粘贴到控制台，或由 provision 脚本 ImportKeyPair
```

- 云平台侧的 `cloud_traffic` 密钥对就是这把公钥的登记，指纹 `a46e525f880ca7321ad39dbd1a38c0d6`。
- **私钥丢了不要紧**：重新 `ssh-keygen` 生成一对，导入为新密钥对，用新密钥开新机即可（旧镜像不含密钥，密钥是登录时注入的）。
- 重新生成的命令：

```powershell
ssh-keygen -t ed25519 -f "$env:USERPROFILE\.ssh\cloud_traffic" -N '""' -C "traffic-rl"
```

### 4.3 绝对不能做

- 把 AK / 私钥 / 控制台密码贴进对话、文档、commit、截图。
- 用主账号 AK。
- 把 `.codebuddy/`（含 API key）同步到服务器。

---

## 五、费用模型（每一分钱怎么来的）

### 5.1 实查单价（`cn-heyuan`，按量，含 ESSD 系统盘基准）

| 项目 | 单价 | 折算 |
|:--|--:|:--|
| `ecs.c9i.2xlarge`（8 vCPU / 4 物理核 / 16 GiB） | **1.436 元/h** | ≈34 元/天 |
| `ecs.c9i.4xlarge`（16 vCPU / 8 物理核 / 32 GiB） | **2.831 元/h** | ≈68 元/天 |
| `ecs.c9i.8xlarge`（32 vCPU / 16 物理核 / 64 GiB） | **5.619 元/h** | ≈135 元/天 |
| ESSD PL0 系统盘 40 GiB | **0.084 元/h** | ≈2.02 元/天、≈61 元/月 |
| 自定义镜像 / 快照 | **0.1385 元/GB·月** | 40 GiB 上限 ≈5.5 元/月 |
| 公网流量（按流量计费） | 0.8 元/GB | 只 SSH+传代码，通常 <1 元 |

> 单位算力单价基本线性（约 0.176 元/vCPU·h），**总成本只取决于总核时，与机器大小无关**。

### 5.2 三种处置的成本对比

| 处置 | 计算费 | 存储费 | 恢复代价 | 适用 |
|:--|:--|--:|:--|:--|
| **开机运行** | 1.436~5.619 元/h | 含在实例内 | 0 | 正在训练 |
| **只关机**（`StopCharging`） | **0** | 磁盘 **0.084 元/h ≈2 元/天** | 开机 30 秒 | 几天内继续用 |
| **镜像化 + 释放** | **0** | 镜像/快照 **≈1~5.5 元/月** | 用镜像开新机 1 分钟 | 一周以上不用 |

**盈亏平衡**：关机 2 元/天 vs 镜像 5.5 元/月 → **只要停超过 3 天，镜像化就更省**。

### 5.3 成本口径（写论文排期时必须用实测值）

```
核时 = 集数 × 每集步数 × 单步耗时 ÷ worker 数
墙钟 = 核时 ÷ 物理核数（再乘 1.1~1.3 的并行损耗系数）
费用 = 墙钟 × 单价
```

---

## 六、场景 A：用现有镜像重开（最常用）

```powershell
cd d:\Code\MultiAgent\traffic_rl_project

# 1) 先看资源还在不在（免费）
D:\Anaconda\python.exe scripts\cloud\inventory_aliyun_ecs.py

# 2) 用自定义镜像开一台（开始计费）
D:\Anaconda\python.exe scripts\cloud\provision_aliyun_ecs.py `
  --image m-f8z1kh9ph7am18g02bra `
  --type ecs.c9i.2xlarge
```

输出末尾会给出公网 IP 与 SSH 命令。**镜像内已带**：Ubuntu 24.04.5、miniconda、conda 环境 `traffic_rl`（Python 3.10）、CPU 版 torch 2.14.1、numba 0.68、全部依赖、`/root/traffic_rl_project` 代码、numba 编译缓存。

开机后直接跳到 **§九（传代码）** 或 **§十（校准）**，**不需要装环境**。

常用规格选择：

| 用途 | 规格 | 单价 |
|:--|:--|--:|
| 单 seed 验证 / 冒烟 | `ecs.c9i.2xlarge` | 1.436 元/h |
| 2~3 seed 并行 | `ecs.c9i.4xlarge` | 2.831 元/h |
| 5 seed 全量并行 | `ecs.c9i.8xlarge` | 5.619 元/h |

> 库存没了就换规格族（`c9i` → `c8i` → `c7` → `g8i`）或换地域；用 `probe_aliyun_ecs.py <region> --min-cpu 8 --price` 查。

---

## 七、场景 B：全新开通（镜像不可用 / 换地域时）

### 7.1 先把权限和余额确认掉

| 检查项 | 怎么查 |
|:--|:--|
| 实名认证 | 控制台右上角账号信息 |
| 按量付费可用额度 ≥100 元 | 控制台 → 费用 → 可用额度；或 `AliyunBSSReadOnlyAccess` + `QueryAccountBalance` |
| RAM 权限 | 需 `AliyunECSFullAccess` + `AliyunVPCFullAccess` |

> 缺 VPC 权限的症状：`CreateVpc` 返回 `Forbidden.RAM`（ECS 权限不含 VPC 写权限）。
> 余额不足的症状：`RunInstances` 返回 `NotEnoughBalance`。

### 7.2 查库存与价格

```powershell
D:\Anaconda\python.exe scripts\cloud\probe_aliyun_ecs.py cn-heyuan --min-cpu 8 --price
D:\Anaconda\python.exe scripts\cloud\probe_aliyun_ecs.py cn-chengdu --min-cpu 16 --price
```

热门地域（华北2北京 / 华东1杭州）大规格常年售罄，优先试：华南2河源、华北6乌兰察布、华北3张家口、西北2中卫、西南1成都。

### 7.3 dry-run → 真开

```powershell
# dry-run：只建/复用免费网络资源并打印下单参数，不产生费用
D:\Anaconda\python.exe scripts\cloud\provision_aliyun_ecs.py --dry-run

# 真开（开始计费）
D:\Anaconda\python.exe scripts\cloud\provision_aliyun_ecs.py --type ecs.c9i.2xlarge
```

脚本是**幂等**的：VPC / 交换机 / 安全组 / 密钥对已存在就复用，不会重复创建。

---

## 八、首次装环境（仅当用**官方镜像**开机时；用自定义镜像跳过本节）

全部在服务器上执行（先 SSH 登录）：

```sh
# 0) 登录（Windows PowerShell 里跑）
#    ssh -i C:\Users\chano\.ssh\cloud_traffic root@<IP>

# 1) 基础软件
apt update && apt install -y build-essential git tmux htop rsync curl wget bzip2 unzip

# 2) miniconda
curl -fsSL https://repo.anaconda.com/miniconda/Miniconda3-latest-Linux-x86_64.sh -o /tmp/mc.sh
bash /tmp/mc.sh -b -p /root/miniconda3
source /root/miniconda3/etc/profile.d/conda.sh

# 3) conda 环境（新版 conda 必须先接受 ToS，否则非交互 create 报 CondaToSNonInteractiveError）
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/main
conda tos accept --override-channels --channel https://repo.anaconda.com/pkgs/r
conda create -y -n traffic_rl python=3.10
conda activate traffic_rl

# 4) CPU 版 torch（务必 CPU 版：GPU 版对本项目慢 4~8 倍，还白占 372 MB 内存）
pip install torch torchvision torchaudio --index-url https://download.pytorch.org/whl/cpu

# 5) 项目依赖（含 numba）
cd /root/traffic_rl_project && pip install -q -i https://pypi.tuna.tsinghua.edu.cn/simple -r requirements.txt

# 6) 测试依赖（requirements.txt 未含）
pip install -q pytest
```

### 8.1 numba 编译缓存预热（并行前必做）

车钩力内核是 `njit(cache=True)`。多个 worker 同时首次编译会抢缓存锁，首集慢数十秒：

```sh
python -c "import src.train_dynamics.train as t; print('numba', t._HAS_NUMBA)"
python run_training.py ... --episodes 1 --override n_env=1 --override n_env_parallel=false
# 再启动正式并行
```

装不上 numba 时设 `TRAIN_RL_NO_NUMBA=1` 回退 numpy 分支（数值等价，慢约 16%）。

### 8.2 装完立刻做镜像（避免以后重装）

```powershell
# 在本机跑：把当前实例打包成镜像（Stopped 状态也能做，不产生计算费）
python -c "..."   # 或参考 .codebuddy/memory/2026-10-23.md 里的 CreateImage 调用
```

---

## 九、传代码（本机 → 服务器）

**在 WSL 里执行**（Windows 侧没有 rsync）：

```sh
wsl -d Ubuntu-24.04

# 首次：把 Windows 私钥复制进 WSL 并收紧权限（见 §2.1）
mkdir -p ~/.ssh && cp -f /mnt/c/Users/chano/.ssh/cloud_traffic ~/.ssh/ && chmod 600 ~/.ssh/cloud_traffic

rsync -avz --info=stats1 \
  --exclude 'outputs/' --exclude '.git/' --exclude '__pycache__/' \
  --exclude '*.pyc' --exclude '.codebuddy/' \
  --exclude 'docs/papers/' --exclude 'reference/' --exclude 'history/' \
  -e "ssh -i $HOME/.ssh/cloud_traffic -o StrictHostKeyChecking=no" \
  /mnt/d/Code/MultiAgent/traffic_rl_project/ root@<IP>:/root/traffic_rl_project/
```

- **禁止**传 `outputs/`（可达数 GB，且会污染云端"最新=权威"的判断）。
- 需要历史 checkpoint 续训时，单独 `scp` 那几个 `.pt`。
- `.codebuddy/` 含 API key，**任何情况不上传**。
- 排除 `outputs/` 后，部分「历史归档一致性」测试会因缺文件失败（`FileNotFoundError: outputs/sim_validation/...`）——**预期行为，不是代码问题**；这类测试在本地跑。

---

## 十、首跑校准（必做，不可跳过）

```powershell
ssh -i $env:USERPROFILE\.ssh\cloud_traffic root@<IP>
```

```sh
source /root/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
cd /root/traffic_rl_project
python -m pytest tests/ -q          # 物理/环境类应全过

python run_training.py --experiment configs/experiments/formation_ed_ab_3train_1plus108.yaml \
  --seed 0 --episodes 2 --override device=cpu \
  --checkpoint_dir outputs/smoke/cloud/ckpt \
  --results_dir outputs/smoke/cloud/results \
  --override dirs.figures_dir=outputs/smoke/cloud/figures
```

判据：

- 从日志读出 **s/ep**，据此重算租期（§5.3）
- **同时检查物理指标**（车钩力峰值 / 超限步数 / 速度带占比）。**物理崩坏的冒烟不得用来估算机时**——崩坏时安全层每步重算 ETCS 曲线，单步耗时会被放大 5~6 倍
- 拿到结论**立即关机**，不要开着机器等决策

---

## 十一、正式训练

```sh
tmux new -s train
source /root/miniconda3/etc/profile.d/conda.sh && conda activate traffic_rl
cd /root/traffic_rl_project
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

1. **`--override device=cpu`**：`ExperimentConfig.device=None` 会自动选 cuda，有 GPU 的机器会切过去且更慢。
2. **三个输出目录同时重定向**（`--checkpoint_dir` / `--results_dir` / `dirs.figures_dir`），否则覆写历史产物（LRN-20261001-009）。
3. **`n_env_parallel=true`** 才真正多进程；否则 `n_env=4` 是单核串行循环。
4. 用 `tmux` 保活：`Ctrl+B` 再 `D` 脱离；`tmux attach -t train` 回来。
5. 训练口径（集数/步数）**以 Owner 指令为准**，本文不提供默认值。

---

## 十二、产物回收

```sh
# 服务器 → 本机（WSL 里跑）
rsync -avz -e "ssh -i $HOME/.ssh/cloud_traffic" \
  root@<IP>:/root/traffic_rl_project/outputs/checkpoints/<run>/ \
  /mnt/d/Code/MultiAgent/traffic_rl_project/outputs/checkpoints/<run>_cloud/
```

先确认没有后台任务：

```sh
tmux ls; pgrep -af run_training.py
```

---

## 十三、三种收尾方式（**关键，别搞混**）

### 13.1 只关机（几天内还要用）

```powershell
D:\Anaconda\python.exe scripts\cloud\instance_state_aliyun_ecs.py --stop <InstanceId>
```

脚本会**自动二次复核**并打印：

```
[复核] Status=Stopped  StoppedMode=StopCharging
✅ 已停费（仅收磁盘费）
```

**必须同时满足**：`Status=Stopped` **且** `StoppedMode=StopCharging`。只发一次 `StopInstance` 就宣称关机 = 违规。
成本：**0.084 元/h ≈ 2 元/天**。

开机（继续用）：

```powershell
# 用 API
# 或控制台"启动"
```

### 13.2 打镜像 + 释放（一周以上不用，推荐）

**步骤 1：确认环境已就绪，然后打镜像**（实例 Stopped 状态即可，不产生计算费）

```powershell
# 参考 .codebuddy/memory/2026-10-23.md 的 CreateImage 调用，或：
# 控制台 → 实例 → 更多 → 云盘和镜像 → 创建自定义镜像
```

等 `DescribeImages` 显示 `Status=Available`（通常 1~10 分钟）。

**步骤 2：释放实例**（不可逆，镜像保留）

```powershell
D:\Anaconda\python.exe scripts\cloud\instance_state_aliyun_ecs.py --stop <InstanceId> --release
```

**步骤 3：复核**

```powershell
D:\Anaconda\python.exe scripts\cloud\inventory_aliyun_ecs.py --cost
```

应看到：`[实例] 0 台`、`[自定义镜像] 1 个 Status=Available`。

成本：**约 1~5.5 元/月**（只有镜像/快照）。

**下次重开**：§六那条命令（`--image m-xxxx`），1 分钟到位。

### 13.3 彻底清理（项目结束）

**顺序很重要**（有依赖关系，顺序错会失败）：

```powershell
cd d:\Code\MultiAgent\traffic_rl_project

# 1) 确认实例已全部释放
D:\Anaconda\python.exe scripts\cloud\inventory_aliyun_ecs.py

# 2) 删自定义镜像（m-开头）
#    控制台 → 镜像 → 删除；或用 DeleteImage API
# 3) 删镜像产生的快照（s-开头）
#    控制台 → 快照 → 删除
# 4) 删安全组（先确认没有实例在用）
# 5) 删交换机（必须先删安全组/实例）
# 6) 删 VPC（必须先删交换机）
# 7) 删密钥对（最后，免费资源，留着也无害）
```

依赖关系：**VPC → 交换机 → 安全组**，删除顺序必须反过来；有实例在用任何一环都会报 `DependencyViolation`。

> VPC / 交换机 / 安全组 / 密钥对 **全部免费**，不删也不花钱。只有**镜像和快照**在收钱，所以"省费用"的关键是**删镜像 + 删快照**，不是删网络。

---

## 十四、命令速查（全部在 Windows PowerShell 里跑）

```powershell
# 切到项目
cd d:\Code\MultiAgent\traffic_rl_project

# —— 盘点（免费）——
D:\Anaconda\python.exe scripts\cloud\inventory_aliyun_ecs.py --cost

# —— 查库存与价格（免费）——
D:\Anaconda\python.exe scripts\cloud\probe_aliyun_ecs.py cn-heyuan --min-cpu 8 --price

# —— 下单前检查（免费）——
D:\Anaconda\python.exe scripts\cloud\preflight_aliyun_ecs.py cn-heyuan

# —— 开通（开始计费）——
D:\Anaconda\python.exe scripts\cloud\provision_aliyun_ecs.py --image m-f8z1kh9ph7am18g02bra --type ecs.c9i.2xlarge

# —— 查状态 ——
D:\Anaconda\python.exe scripts\cloud\instance_state_aliyun_ecs.py <InstanceId>

# —— 关机（自动二次复核）——
D:\Anaconda\python.exe scripts\cloud\instance_state_aliyun_ecs.py --stop <InstanceId>

# —— 关机 + 释放（不可逆）——
D:\Anaconda\python.exe scripts\cloud\instance_state_aliyun_ecs.py --stop <InstanceId> --release

# —— SSH ——
ssh -i $env:USERPROFILE\.ssh\cloud_traffic root@<IP>

# —— 传代码（WSL）——
wsl -d Ubuntu-24.04 -e bash -lc "rsync -avz --exclude 'outputs/' --exclude '.git/' --exclude '__pycache__/' --exclude '.codebuddy/' -e 'ssh -i ~/.ssh/cloud_traffic' /mnt/d/Code/MultiAgent/traffic_rl_project/ root@<IP>:/root/traffic_rl_project/"
```

---

## 十五、已知坑速查（均为实测复现）

| 现象 | 根因 | 处置 |
|---|---|---|
| `InvalidOperation.NotSupportedEndpoint` | ECS API endpoint 未带地域 | 用 `ecs.{region}.aliyuncs.com` |
| `InvalidSystemDiskCategory.ValueNotSupported`（DescribePrice，如河源） | 询价未显式给系统盘类型 | 传 `SystemDisk.Category=cloud_essd` |
| `DescribeImages` 按 `ImageFamily` 过滤返回 0 | 该过滤参数不生效 | 用 `ImageOwnerAlias=system` 拉全量后本地过滤 |
| `IncorrectVpcStatus`（CreateVSwitch 紧跟 CreateVpc） | VPC 需数秒才 `Available` | 轮询 `DescribeVpcs` 直到 `Status=Available` |
| `CreateVpc` → `Forbidden.RAM` | ECS 权限不含 VPC 写权限 | 加 `AliyunVPCFullAccess` |
| `QueryAccountBalance` → `NotAuthorized` | 缺 BSS 权限 | 加 `AliyunBSSReadOnlyAccess` 或控制台自查 |
| `RunInstances` → `NotEnoughBalance` | 额度不足 | 充值（官方 ≥100 元门槛） |
| 大规格"无货" | 只看热门地域 | 换冷门地域 + 换规格族（c→c8i→c9i→g） |
| `conda create` → `CondaToSNonInteractiveError` | 新版 conda 需接受频道 ToS | `conda tos accept --override-channels --channel ...` |
| `ModuleNotFoundError: No module named 'gym'` | requirements 曾缺 `gym`（代码 `from gym import spaces`） | 已补入 requirements；或 `pip install gym==0.26.2` |
| `ModuleNotFoundError: pytest` | requirements 未含测试依赖 | `pip install pytest` |
| SSH 拒绝私钥（`Permissions 0777`） | WSL 下 `/mnt/c` 权限无法收紧 | `cp` 到 `~/.ssh/` 后 `chmod 600` |
| PowerShell 调 WSL/SSH 报语法错误 | 多层引号转义 | 命令写进 `.sh` 文件再 `bash file.sh`（`sed -i 's/\r$//'` 去 CRLF） |
| Windows 侧跑 Python 脚本输出中文乱码 / `UnicodeEncodeError` | Windows 控制台默认编码非 UTF-8 | 同一会话先 `$env:PYTHONIOENCODING='utf-8'` 再执行脚本（只对当前进程树有效，新开终端要重设） |
| 首集特别慢（数十秒） | numba 首次编译 + 多 worker 抢缓存锁 | 先单进程预热（§8.1） |
| 单步耗时忽快忽慢（3 倍波动） | 笔记本热降频 / 云主机噪声 | 只看 cProfile 相对比值；绝对耗时多次取最小值 |
| 排除 `outputs/` 后测试报 `FileNotFoundError` | 归档一致性测试缺历史数据 | 预期行为，这类测试在本地跑 |

> **诊断脚本陷阱**：`TrainFleetEnv` 的 `info` 里**没有** `speed` 键（只有单列 env 有）。
> 写 `info.get('speed', 0.0)` 会恒得 0，误判"列车停住"；应读 `env.trains[i].dynamics.vel[0]`。

### 15.1 云上长任务 / watchdog 防学费清单（2026-11-09 实战复盘，12 元学费固化）

> 六条全部为当天实测翻车复现。**上线前端到端演练一次**（人为 kill 目标进程，跑通"判活→回传→关机回执"全链）就能拦住其中四条。

1. **判活禁自指**：远程判活禁用 `ssh host "pgrep -f <pattern>"` / `bash -c 'pgrep -f ...'`——pattern 会匹配承载它自己的 bash 进程，**永远判"还在跑"**，watchdog 永不触发收账/关机（本条当天多烧 3.3 元）。改用：pid 文件 `kill -0` / 产物文件 mtime 增长判活 / `pgrep -f pat | grep -v $$`。
2. **watchdog 心跳自证**：每轮轮询必须 append 一行判活结果到本地日志；日志"只有 start 没有后续行"= 异常。禁用 12h 超时兜底代替心跳。
3. **完成判据用产物内容校验**：禁"文件存在 = 完成"（GA 崩溃残留的 `best_knobs.json` 曾会被误判 COMPLETE）。正确做法：校验内容（如 `history.csv` 行数 ≥ 目标代数 / result.json 含终态字段）。
4. **保真复现 = 基准协议逐字段搬运**：任何"复现基准归档"的自检路径必须带齐基准归档的**全部** override/起点/seed 参数（rel54 的 70 kPa / start-m / gap-offset 漏一项 → 复现峰值差 17%，防线拦截烧 9 元）。换基准时同步重新生成复现配置；超差 1% 硬失败。
5. **resume/续训前必须 pgrep 实证**：启动任何 resume 或重启链条前 `pgrep -f run_training` 核查，不凭口头状态（当天凭"已关机"假设启动 resume → 与存活进程双开抢核 40 min，险些 checkpoint 竞写）。
6. **费用封顶 + 心跳告警**：云任务开工前定预算（如 8 元），预算超时即告警并人工介入，不靠"任务跑完自动关机"单点（该单点当天失灵）。

---

## 十六、禁止事项

1. **在服务器上做诊断/调参/冒烟**（只跑正式训练，见铁律 1）。
2. 用主账号 AccessKey。
3. 把 AK / 私钥 / 密码写进对话、文档、commit、截图。
4. 只调一次 `StopInstance` 就宣称已关机（必须二次复核，铁律 5）。
5. 选包年包月，或让实例开着等决策。
6. 训练口径未确定就开机试跑。
7. 改 `n_env` / 物理参数 / 奖励来"适配服务器"（两侧物理同源）。
8. 整包同步 `outputs/` 或 `.codebuddy/`。
9. 绕过 `run_training.py` 用临时脚本在云端跑正式实验（metadata 缺失 → 结论不成立）。
10. **删 VPC/交换机前不先删实例**（会 `DependencyViolation`；正确顺序见 §13.3）。

---

## 十七、开机即跑／跑完即关 一键包（2026-11-10，准备就绪，未开通实例）

> 硬约束（用户 2026-11-10）：**绝不允许实例开机却空等计费**。本节的包就是为了满足它：
> 预检全过才开 → 第一条命令即训练 → 三种结局都自动关机 → **日志回传校验通过才释放**。

### 17.1 脚本清单

| 脚本 | 跑在哪 | 职责 | 关键判据 |
|---|---|---|---|
| `scripts/cloud/preflight_payload.sh` | 本地 WSL | payload 预检 8 项，全 PASS 才写 `.preflight_ok` | 任一 FAIL → exit 1 且删除 marker |
| `scripts/cloud/instance_bootstrap.sh` | 实例 | **第一条命令即训练**（只 conda activate，不安装）+ 落 `exit_code.txt` | 无 `.preflight_ok` → exit 90；环境失败 → 91 |
| `scripts/cloud/instance_watchdog.sh` | 实例 | 心跳超时 / 进程消失 → 写 `DEAD_*` + `poweroff` | 心跳龄 > `STALE_S`（默认 1800 s）；结束等 `.pull_done` 上限 `GRACE_S`（默认 900 s） |
| `scripts/cloud/pull_artifacts.sh` | 本地 WSL | rsync 回传 + 完成判据校验 → 通过才 `touch .pull_done` | CSV 行数 > 0 且心跳存在；exit=0 + `训练完成` = 正常结束 |
| `scripts/cloud/run_lifecycle.ps1` | 本地 Windows | 轮询状态 → 调回传 → API 停机 → **StopCharging 复核** → `-Release` 释放 → 记成本账本 | 未复核到 `StoppedMode=StopCharging` **禁止释放** |

### 17.2 预检 8 项（缺一不许开机）

1. 代码快照：commit + payload sha256（`src/ configs/ run_training.py scripts/`），工作区脏则 WARN 并列数；
2. 配置键值：`n_env` / `n_env_parallel=true` / **`env_cfg.reward_term_log=true`** / `coupler_force_limit_n=1.0e6` / `route_end_m` / `speed_band_shape=ref` / `decompose` / `log_interval=1`；
3. 参考速度表存在且 `np.load` 可读（`s_m`, `v_mps`）；
4. BC 权重 `bc_warmstart.pt` 存在且含 `value_state_dict`；
5. 续训 checkpoint 存在且能解析出 `done_ep`；
6. 依赖版本（py 3.10 / numpy / numba / torch）与镜像一致；
7. `instance_bootstrap.sh` / `instance_watchdog.sh` 存在且 `bash -n` 通过；
8. 退出码与完成判据：bootstrap 落 `exit_code.txt`、训练入口含「训练完成」、`device=cpu`、三输出目录重定向。

### 17.3 生命周期时序（谁在什么时候关机）

```
本地 preflight → PASS(.preflight_ok) → 用户批准后开通实例
  → rsync 代码（含 .preflight_ok）
  → bootstrap: 立即训练（pid + 心跳）→ watchdog 并行值守
  → 本地 run_lifecycle 每 60 s: 查状态 →（跑完则）pull_artifacts → 校验 → .pull_done
  → API stop → 复核 Stopped + StopCharging →（-Release）释放 → 写成本账本
```

| 结局 | 实例侧动作 | 本地动作 |
|---|---|---|
| 正常结束（exit=0 + 完成标记） | 等 `.pull_done` ≤900 s 后 `poweroff` | 回传→校验→放行→stop 复核→释放 |
| 异常退出（exit≠0） | 同上（产物仍可归档，标 ABORTED） | 同上，但**不当作结果引用** |
| 心跳超时（卡死） | 杀训练 → `DEAD_HEARTBEAT` → `poweroff` | 尽力拉日志 → API stop 复核 → 写 `DEAD` 标记 → 释放 |

> 停机两道保险：实例侧 `poweroff` 只是止血，**「已停费」以 API `StoppedMode=StopCharging` 回执为准**（铁律 5）。
> 回传失败（校验不过）时**禁止释放**——释放等于丢产物；此时仅停机，等人工决定是否开机取回。

### 17.4 断点续训

- 主配置 `log_interval: 1` ⇒ 每集都落 `last.pt`（`mappo_fleet_last_ep<N>_*.pt`），被回收最多损失当前这一集。
- 重开只补剩余集：`--resume <last.pt> --episodes <总目标>`，`plan_run_episodes` 自动算 `总目标 − done_ep`。
- **续训必关 BC**：`--resume` 分支内部已强制 `cfg.warm_start=False`，否则会覆盖 `bc_warmstart.pt`。

### 17.5 选型与成本（不询价、按已记录单价推算；单价以开通前 probe 复核为准）

瓶颈是 **numpy 物理仿真**（单进程 0.0432 s/步，4 进程并行 3.12×），不是网络训练 ⇒ **多核 CPU 实例，不用 GPU 机型**。

| 候选 | 规格 | 物理核 | 单价（已记录） | 适合 |
|---|---|---|---|---|
| `ecs.c9i.2xlarge` | 8 vCPU / 16 GiB | 4 | 1.436 元/h | 与本地同构，最省，跑 4 worker |
| `ecs.c9i.4xlarge` | 16 vCPU / 32 GiB | 8 | 2.831 元/h | 同口径双 worker 组，墙钟减半 |
| `ecs.c9i.8xlarge` | 32 vCPU / 64 GiB | 16 | 5.619 元/h | 大规模一次性跑完，墙钟最短 |

系统盘 ESSD PL0 40 GiB ≈ 0.084 元/h（≈2 元/天）。**总价 ≈ 核时 × 0.359 元/核时**，与机型无关；换大机器只压缩墙钟。

- **本次建议（20 集，ep41–60）**：`c9i.2xlarge`，按实测 920 s/集 ⇒ **≈5.1 h，≈7.5 元**（含盘 ≈8 元）。
- 参考（未批准）：1400 集在 4 worker 下 ≈ **358 h / ≈515 元**；提到 16 worker ≈ 89 h（含并行效率损失约 +20%）≈ **600 元**。**改 `n_env` 属训练口径变更，须单独批准**。


---

> 本文件是**规范**，不承载实验数据；实测记录进 `docs/logs/diagnostics/DIAGNOSTICS_YYYY-MM.md`，
> 踩坑教训进 `docs/logs/learnings/LEARNINGS.md`，重大采购/架构决策进 `docs/logs/decisions/DECISIONS.md`。
