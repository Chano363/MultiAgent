"""fleet decompose（机车级 ED/AB 分工，6 智能体编队）领域符号：BC warm start。

【2026-09-10 新增】针对诊断-2026-09-10：53km 主训练 6 机车编队 MAPPO 在
horizon >=1500 步时 on-policy 随机探索踩进"暴力 AB 吸态"且 value 污染无法回退，
5 个微杠杆（相对锚定/coupler惩罚/回滚/AB门控/curriculum退火）全部失败。

对策 = 行为克隆热启动自**确定性规则基线**（MultiLocoController.get_action_cyclic_braking，
53km 全程车钩力峰值仅 793kN<1000kN，已证明安全）：
- 策略输出 [ed_mod, ab_mod]∈[-1,1]²，输出 [0,0] 时 final=baseline（不调制即复现规则基线，
  get_action_decomposed 定义）。
- 故 BC 采集规则基线 rollout 的 (obs, [0,0])，预训练策略 mean→0、log_std→~-2.3(std~0.1)，
  使 RL 从安全域小扰动出发微调编队协同，避免长时程随机探索破坏安全底线。
- 与 ADR-013 分层（安全规则层确定性执行 + RL 只学编队协同）自洽。
"""

import json
import logging
import time
from datetime import datetime
from pathlib import Path

import numpy as np

from src.algorithms.mappo_agent import MAPPOAgent

logger = logging.getLogger('FleetSpec')

# 【2026-11-08】BC 均值收敛硬阈值：|mean| 均值必须 < 0.02（≈2% 动作量程）。
# 旧阈值 0.1 太松：0.089 的均值偏差在闭环里等于"比规则基线多 ~9% ED"，3000 步即
# 8.4% 车·步超速（而零动作偏离参考速度仅 0.11 km/h）。判据不过 ⇒ 直接抛错。
BC_MEAN_ABS_TOL = 0.02
# 【2026-11-08】BC 探索方差目标 log_std = -3.0（std ≈ 0.05）。
# 旧目标 -2.3（std 0.1）实测有系统性偏置：`ed_mod` 负半轴被"ED 不能为负"截断、
# 正半轴照常加牵引 ⇒ 对称噪声在闭环里变成**净加牵引**，3000 步就把均速从 ≈65 km/h
# 顶到 74.9 km/h（18% 车·步超速、speed_band −9.82/步、整集 R −26 199，而零动作 +28 227）。
# 故起步方差减半，交由 RL 的熵项自行放大。
BC_LOG_STD_TARGET = -3.0


def warm_start_decompose_bc(
    agent: MAPPOAgent,
    env,
    episodes: int = 3,
    bc_epochs: int = 5,
    lr: float = 5e-3,
    max_steps: int = 1500,
    init_speed: float = 80.0 / 3.6,
    save_dir: str = None,
    metadata: dict = None,
):
    """用规则基线 rollout 采集 (obs, [0,0]) 并预训练策略：mean→0 + std→~0.1。

    参数约定：env 为 decompose 模式的 TrainFleetEnv（每 agent = 一台机车，obs 12 维、
    act 2 维）。采集时以全零调制 step（复现规则基线，含列内规则循环制动 + 车钩力
    安全层 + 列间协调偏置），标签即零调制 → 学成"复现安全规则基线"。

    【2026-11-08 产物落盘】save_dir 非空时，训练完立刻把**完整 agent checkpoint**
    （policy + value + model_signature，走 BaseRLAgent.save 协议）落到
    `<save_dir>/bc_warmstart.pt`，并写判据文件 `<save_dir>/bc_warmstart_judge.json`。
    落"完整"而非"仅 policy"是硬要求：`--resume-weights-only` 走
    `MAPPOAgent._restore_checkpoint`，那里必然读 `value_state_dict`，只存 policy 会直接
    KeyError。10-21 那轮的教训是 BC/RL 全程没有 `.pt`（ADR-058），故此处把
    "文件存在 + 字节非 0 + loss 有限" 作为硬判据写进 json，供交接时验证。
    """
    import torch

    if episodes <= 0:
        return
    env.max_steps = max(env.max_steps, max_steps)
    # 【2026-10-21 治本｜静默训练】BC 采集阶段此前全程无日志（单核前台），
    # 每次都要几分钟到十几分钟，与"卡死"无法区分。此处开跑即打印，并逐集回报进度。
    t_bc = time.time()
    logger.info(f"[BC] 规则基线演示采集开始：{episodes} 集 × ≤{max_steps} 步/集"
                f"（采集期间无进度条属正常，下面逐集打印）")
    bc_obs, bc_acts = [], []
    for ep in range(episodes):
        obs, _ = env.reset(options={'speed': init_speed})   # (num_agents, obs_per_drone)
        done = False
        step = 0
        while not done and step < max_steps:
            action = np.zeros((env.num_agents, 2), dtype=np.float32)  # [0,0]=复现规则基线
            bc_obs.append(np.asarray(obs, dtype=np.float32).reshape(env.num_agents, -1))
            bc_acts.append(action.reshape(-1))
            next_obs, r, term, trunc, info = env.step(action)
            done = bool(term or trunc)
            obs = next_obs
            step += 1
        logger.info(f"[BC] 采集 {ep + 1}/{episodes} 集完成：本集 {step} 步，"
                    f"累计 {len(bc_obs)} 步，已耗时 {time.time() - t_bc:.0f}s")

    num_agents = int(env.num_agents)
    obs_arr = np.asarray(bc_obs, dtype=np.float32).reshape(-1, agent.obs_per_drone)  # [N*6, 11]
    act_arr = np.asarray(bc_acts, dtype=np.float32).reshape(-1, agent.act_per_drone)  # [N*6, 2]
    assert not np.any(act_arr), 'BC 标签必须全零调制（否则不再是"复现规则基线"）'
    logger.info(
        f"Fleet BC warm start: 采集 {obs_arr.shape[0]} 条 (obs, [0,0])，"
        f"预训练 {bc_epochs} epochs"
    )
    obs_t = torch.as_tensor(obs_arr, dtype=torch.float32, device=agent.device)

    # BC has its own learning rate and policy-only optimizer. Leave the RL
    # optimizer's learning rate and moment estimates untouched.
    opt = torch.optim.Adam(agent.policy.parameters(), lr=lr)
    for epoch in range(bc_epochs):
        mean, log_std = agent.policy(obs_t)                # [N*6, 2]
        # 【2026-11-08 修订】标签是**确定性**动作（全零调制），故 BC 用"确定性回归 + 方差整形"，
        # 不用高斯 NLL：NLL 对均值的梯度 ∝ 1/std²，σ 一旦收小就与 std_reg 互相拉扯，
        # 实测 30/200 epochs 后 |mean| 仍 0.046/0.052（且 σ 被拉低到 0.04，偏离目标 0.1）。
        # 改成 MSE 后梯度尺度恒定，均值能真正收敛（BC 常用做法：对动作头做 L2 回归）。
        mean_mse = mean.pow(2).mean()
        std_reg = (log_std - BC_LOG_STD_TARGET).pow(2).mean()   # 拉 log_std→-3.0 (std≈0.05)
        loss = mean_mse + 0.5 * std_reg
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(agent.policy.parameters(), 0.5)
        opt.step()
    logger.info(f"Fleet BC warm start 完成，BC loss={loss.item():.3f}")
    with torch.no_grad():
        mean_s, log_std_s = agent.policy(obs_t)
    std_mean = float(log_std_s.mean().exp())
    logger.info(f"[BC] 拟合结果：|mean| 均值 {float(mean_s.abs().mean()):.4f}"
                f"（目标 0），std 均值 {std_mean:.4f}（目标 ≈0.10）")

    if save_dir:
        out = Path(save_dir)
        out.mkdir(parents=True, exist_ok=True)
        pt = out / 'bc_warmstart.pt'
        meta = {
            'kind': 'bc_warmstart',
            'created_at': datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            'obs_dim': int(agent.obs_per_drone),
            'act_dim': int(agent.act_per_drone),
            'num_agents': int(env.num_agents),
            'episodes': int(episodes),
            'max_steps': int(max_steps),
            'bc_epochs': int(bc_epochs),
            'bc_lr': float(lr),
            'n_samples': int(obs_arr.shape[0]),
            'bc_loss': float(loss.item()),
            'policy_abs_mean': float(mean_s.abs().mean()),
            'policy_std_mean': std_mean,
            'policy_mean_abs_threshold': float(BC_MEAN_ABS_TOL),
            'label': '[0,0]（零调制 = 复现规则基线）',
        }
        if metadata:
            meta.update(metadata)
        agent.save(str(pt), metadata=meta)
        judge = dict(meta)
        judge.update({
            'checkpoint_path': str(pt),
            'checkpoint_bytes': int(pt.stat().st_size),
            # 判据：文件存在且非 0、样本充足、loss 有限、动作均值已收敛到规则基线附近
            'pass': bool(pt.is_file() and pt.stat().st_size > 0
                         and obs_arr.shape[0] > 0
                         and np.isfinite(loss.item())
                         and float(mean_s.abs().mean()) < BC_MEAN_ABS_TOL),
            'reuse': f"python run_training.py --experiment <yaml> --resume {pt} "
                     f"--resume-weights-only",
        })
        (out / 'bc_warmstart_judge.json').write_text(
            json.dumps(judge, ensure_ascii=False, indent=2), encoding='utf-8')
        logger.info(f"[BC] checkpoint 落盘 {pt}（{pt.stat().st_size} B），判据 "
                    f"{out / 'bc_warmstart_judge.json'}，pass={judge['pass']}")
        if not judge['pass']:
            raise RuntimeError(f'BC warm start 判据未通过，详见 {out / "bc_warmstart_judge.json"}')

    return obs_arr.shape[0]
