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

import logging
import time

import numpy as np

from src.algorithms.mappo_agent import MAPPOAgent

logger = logging.getLogger('FleetSpec')


def warm_start_decompose_bc(
    agent: MAPPOAgent,
    env,
    episodes: int = 3,
    bc_epochs: int = 5,
    lr: float = 1e-3,
    max_steps: int = 1500,
    init_speed: float = 80.0 / 3.6,
):
    """用规则基线 rollout 采集 (obs, [0,0]) 并预训练策略：mean→0 + std→~0.1。

    参数约定：env 为 decompose 模式的 TrainFleetEnv（num_agents=6，每机车 obs 11 维、
    act 2 维）。采集时以全零调制 step（复现规则基线，含列内规则循环制动 + 车钩力
    安全层 + 列间协调偏置），标签即零调制 → 学成"复现安全规则基线"。
    """
    import torch
    from torch import distributions as D

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
    logger.info(
        f"Fleet BC warm start: 采集 {obs_arr.shape[0]} 条 (obs, [0,0])，"
        f"预训练 {bc_epochs} epochs"
    )
    obs_t = torch.as_tensor(obs_arr, dtype=torch.float32, device=agent.device)
    act_t = torch.as_tensor(act_arr, dtype=torch.float32, device=agent.device)

    # BC has its own learning rate and policy-only optimizer. Leave the RL
    # optimizer's learning rate and moment estimates untouched.
    opt = torch.optim.Adam(agent.policy.parameters(), lr=lr)
    for epoch in range(bc_epochs):
        mean, log_std = agent.policy(obs_t)                # [N*6, 2]
        dist = D.Normal(mean, log_std.exp())
        nll = -dist.log_prob(act_t).sum(dim=-1).mean()     # 拉 mean→0（复现规则基线）
        std_reg = (log_std - (-2.3)).pow(2).mean()         # 拉 log_std→-2.3 (std~0.1)，
        loss = nll + 0.5 * std_reg                          # 探索小扰动且不破坏安全域
        opt.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(agent.policy.parameters(), 0.5)
        opt.step()
    logger.info(f"Fleet BC warm start 完成，BC loss={loss.item():.3f}")
    return obs_arr.shape[0]
