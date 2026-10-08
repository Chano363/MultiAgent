"""
Multi-Agent Proximal Policy Optimization (MAPPO)
Shared policy + centralized critic for multi-agent control (trains/drones).

复用阶段一验证过的 MAPPO 架构，阶段二迁移到重载列车群组控制：
每节车厢 = 智能体（共享策略），集中式 Critic 观测全列状态。
"""

import torch
import torch.nn as nn
import torch.optim as optim
import numpy as np
from typing import List, Dict, Tuple, Optional
import logging

from .base_agent import BaseRLAgent


class RunningMeanStd:
    def __init__(self, shape=()):
        self.mean = np.zeros(shape, dtype=np.float32)
        self.var = np.ones(shape, dtype=np.float32)
        self.count = 0

    def update(self, x):
        batch_mean = np.mean(x, axis=0)
        batch_var = np.var(x, axis=0)
        batch_count = len(x)
        self.mean, self.var, self.count = self._update_mean_var_count(
            self.mean, self.var, self.count, batch_mean, batch_var, batch_count
        )

    @staticmethod
    def _update_mean_var_count(mean, var, count, batch_mean, batch_var, batch_count):
        total_count = count + batch_count
        delta = batch_mean - mean
        new_mean = mean + delta * batch_count / total_count
        m_a = var * count
        m_b = batch_var * batch_count
        M2 = m_a + m_b + delta**2 * count * batch_count / total_count
        new_var = M2 / total_count
        return new_mean, new_var, total_count


class ValueNorm:
    """value 目标归一化（PopArt 简化版）。

    问题：多智能体累计回报 |returns| 可达 1e4~1e5，value 网络初始输出 ~0，
    导致 value_loss ~1e8 量级 → 数值不稳定、梯度被 clip 吞没、Loss 阈值误杀。
    解决：value 网络拟合"归一化 returns"（O(1) 尺度），
    推理/GAE 时用 denormalize 还原为真实尺度，保证与奖励回报同量纲。
    """

    def __init__(self, eps: float = 1e-8, decay: float = 1.0):
        self.mean = 0.0
        self.std = 1.0
        self.count = 0
        self.eps = eps
        # decay < 1 时退化为"指数遗忘"统计：每次 update 先把历史有效样本数乘以 decay，
        # 使归一化尺度跟随**近期**回报而非被早期极端回报永久锁定（诊断-2026-10-03：
        # 全程 Welford 下 ep<50 的暴力 AB 极端负回报把 std 从 ~4k 抬到 ~11.5k 后不再回落，
        # 与"脏回合占比随训练上升"同步）。decay=1.0 = 旧行为（零回归）。
        self.decay = float(decay)

    def update(self, returns: np.ndarray):
        """用一批 returns 增量更新 running mean/std（Welford，可选指数遗忘）。"""
        x = np.asarray(returns, dtype=np.float64)
        n = len(x)
        if n == 0:
            return
        batch_mean = float(np.mean(x))
        batch_var = float(np.var(x))
        batch_count = n
        prior_count = self.count * self.decay
        total_count = prior_count + batch_count
        delta = batch_mean - self.mean
        new_mean = self.mean + delta * batch_count / total_count
        m_a = self.std**2 * prior_count
        m_b = batch_var * batch_count
        M2 = m_a + m_b + delta**2 * prior_count * batch_count / total_count
        new_var = M2 / total_count if total_count > 0 else 1.0
        self.mean = new_mean
        self.std = float(np.sqrt(new_var))
        self.count = total_count

    def normalize(self, x) -> np.ndarray:
        return (np.asarray(x) - self.mean) / (self.std + self.eps)

    def denormalize(self, x) -> np.ndarray:
        return np.asarray(x) * (self.std + self.eps) + self.mean


class ContinuousPolicyNetwork(nn.Module):
    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_sizes: List[int] = [256, 128],
        use_layer_norm: bool = True,
        log_std_min: float = -4.0,
        log_std_max: float = 2.0,
    ):
        super(ContinuousPolicyNetwork, self).__init__()
        self.use_layer_norm = use_layer_norm
        # 【2026-10-07 治熵失控】log_std 上下限改为可配（默认 -4.0/2.0 = 旧行为，零回归）。
        # 旧上限 2.0 ⇒ σ=e²≈7.39，对 clip 到 [-1,1] 的动作等于近似均匀噪声 ⇒ 策略无法收敛。
        self.log_std_min = float(log_std_min)
        self.log_std_max = float(log_std_max)
        layers = []
        input_dim = state_dim

        for hidden_size in hidden_sizes:
            layers.append(nn.Linear(input_dim, hidden_size))
            if use_layer_norm:
                layers.append(nn.LayerNorm(hidden_size))
            layers.append(nn.Tanh())
            input_dim = hidden_size

        self.backbone = nn.Sequential(*layers)
        self.mean_layer = nn.Linear(input_dim, action_dim)
        self.log_std_layer = nn.Linear(input_dim, action_dim)
        self._initialize_weights()

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.orthogonal_(m.weight, gain=np.sqrt(2))
                nn.init.constant_(m.bias, 0)

    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        features = self.backbone(state)
        mean = torch.tanh(self.mean_layer(features))
        log_std = self.log_std_layer(features)
        # log_std 下限收紧到 -4（std≈0.018）：
        # E4 诊断——log_prob 重算（安全层修正动作后）时，若 log_std 崩到 -20（std~2e-9），
        # 任何动作 log_prob 极端负值，`(new_log_probs - old_log_probs)²` KL 爆炸到 7e4（观测到 27174/74261），
        # 破坏策略更新。收紧下限保证 std 有合理下限，避免确定性崩塌导致的数值不稳定。
        # 只影响训练，不影响推理（deterministic 用 mean）。
        log_std = torch.clamp(log_std, min=self.log_std_min, max=self.log_std_max)
        return mean, log_std


class CentralizedValueNetwork(nn.Module):
    def __init__(
        self,
        state_dim: int,
        hidden_sizes: List[int] = [512, 256, 128],
        use_layer_norm: bool = True,
        output_dim: int = 1
    ):
        super(CentralizedValueNetwork, self).__init__()
        self.use_layer_norm = use_layer_norm
        # 【ADR-021 方向 B】output_dim>1 时输出 per-agent 价值头（每 agent 一个标量），
        # 默认 1 完全等价旧行为/旧 checkpoint（末层形状不变）。
        self.output_dim = output_dim
        layers = []
        input_dim = state_dim

        for hidden_size in hidden_sizes:
            layers.append(nn.Linear(input_dim, hidden_size))
            if use_layer_norm:
                layers.append(nn.LayerNorm(hidden_size))
            layers.append(nn.Tanh())
            input_dim = hidden_size

        layers.append(nn.Linear(input_dim, output_dim))
        self.network = nn.Sequential(*layers)
        self._initialize_weights()

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.orthogonal_(m.weight, gain=np.sqrt(2))
                nn.init.constant_(m.bias, 0)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.network(state)


class MAPPOAgent(BaseRLAgent):
    """Multi-Agent PPO with shared policy and centralized critic."""

    def __init__(
        self,
        num_drones: int,
        obs_per_drone: int,
        act_per_drone: int,
        learning_rate: float = 3e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_epsilon: float = 0.15,
        entropy_coef: float = 0.001,
        value_coef: float = 0.5,
        epochs: int = 10,
        batch_size: int = 128,
        max_grad_norm: float = 0.5,
        device: str = 'cpu',
        use_gae: bool = True,
        use_clipped_value_loss: bool = True,
        critic: str = 'centralized_scalar',
        decision_interval: int = 1,
        physics_dt: float = 0.1,
        value_norm_decay: float = 0.98,
        log_std_min: float = -4.0,
        log_std_max: float = 2.0,
    ):
        # 【ADR-021 方向 B】critic 必须为枚举字符串（禁止布尔开关）：
        #   'centralized_scalar' = 集中式单标量价值头（旧行为，零回归）
        #   'per_agent'          = 每 agent 一个价值头 → per-agent advantage（修复信用分配断裂）
        if critic not in ('centralized_scalar', 'per_agent'):
            raise ValueError(
                f"critic 必须为 'centralized_scalar' 或 'per_agent'，实际为 {critic!r}")
        self.num_drones = num_drones
        self.obs_per_drone = obs_per_drone
        self.act_per_drone = act_per_drone
        self.total_obs_dim = num_drones * obs_per_drone
        self.total_act_dim = num_drones * act_per_drone
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.critic_mode = critic
        # 决策间隔 = 每个 RL 决策步对应的**原始环境步数**（由 registry 从 cfg.decision_interval
        # 注入）。注意：它是"步数"而非"秒"——物理秒数须再乘 `physics_dt`。
        self.decision_interval = int(decision_interval)
        # 环境物理步长（秒）；由 registry 从 env.dt 注入，用于把 RL 决策步换算成物理秒。
        self.physics_dt = float(physics_dt)
        self.decision_interval_s = self.decision_interval * self.physics_dt
        self.clip_epsilon = clip_epsilon
        self.entropy_coef = entropy_coef
        self.value_coef = value_coef
        self.epochs = epochs
        self.batch_size = batch_size
        self.max_grad_norm = max_grad_norm
        self.use_gae = use_gae
        self.use_clipped_value_loss = use_clipped_value_loss
        self.target_kl = 0.01

        self.device = torch.device(device)
        logging.info(f"MAPPO设备: {self.device}")

        self.policy = ContinuousPolicyNetwork(
            obs_per_drone, act_per_drone,
            hidden_sizes=[256, 128],
            log_std_min=log_std_min,
            log_std_max=log_std_max,
        ).to(self.device)

        self.value = CentralizedValueNetwork(
            self.total_obs_dim,
            hidden_sizes=[512, 256, 128],
            output_dim=(self.num_drones if self.critic_mode == 'per_agent' else 1),
        ).to(self.device)

        # 【ADR-021 方向 B / 信用视界对齐】有效信用视界 = 1/(1-γλ) 个 **RL 决策步**；
        # 换算物理秒 = 决策步数 × decision_interval(原始步) × physics_dt(秒/步)。
        # 诊断-2026-09-30：AB 首现 → 车钩力首破远期 ≈90 s 物理滞后，训练默认
        # γ=0.99/λ=0.95（≈17 决策步 × 10 步 × 0.1 s = 16.8 s）远不足以覆盖；
        # 须 γ=0.999/λ=0.99（≈91 决策步 ≈91 s）才能对齐。打印对照便于选型。
        self.effective_horizon_steps = 1.0 / max(1e-9, 1.0 - self.gamma * self.gae_lambda)
        self.effective_horizon_s = self.effective_horizon_steps * self.decision_interval_s
        _physical_lag_s = 90.0
        _covered = self.effective_horizon_s >= _physical_lag_s
        logging.info(
            f"[信用视界] gamma={self.gamma} gae_lambda={self.gae_lambda} | "
            f"1/(1-γλ)={self.effective_horizon_steps:.1f} 决策步 | "
            f"决策间隔 {self.decision_interval} 原始步 × dt={self.physics_dt}s "
            f"= {self.decision_interval_s:.2f}s/决策步 → "
            f"有效视界 {self.effective_horizon_s:.1f}s | "
            f"对照物理滞后≈{_physical_lag_s:.0f}s → "
            f"{'覆盖' if _covered else '不足：未覆盖'}"
        )

        self.optimizer = optim.Adam(
            list(self.policy.parameters()) + list(self.value.parameters()),
            lr=learning_rate,
            betas=(0.9, 0.999),
            weight_decay=1e-5
        )

        self.buffer_states = None
        self.buffer_actions = None
        self.buffer_log_probs = None
        self.buffer_rewards = None
        self.buffer_dones = None
        self.buffer_values = None

        # value 目标归一化（解决多智能体累计回报量级过大导致的 value_loss 爆炸）
        self.value_norm = ValueNorm(decay=value_norm_decay)
        # reward running 统计（保留字段以兼容旧 checkpoint，更新逻辑已迁移至 value_norm）
        self.reward_rms = RunningMeanStd()
        self.training_step = 0

    def _batch_obs(self, global_state: np.ndarray) -> torch.Tensor:
        """把 flatten 的全局状态 reshape 成 [num_drones, obs_per_drone] 张量。

        共享策略下每车 obs 维度相同，整批一次前向替代 N 次 batch=1 循环，
        GPU 利用率从 ~5% 提升到 ~80%+（性能优化核心）。
        """
        obs = np.asarray(global_state, dtype=np.float32).reshape(self.num_drones, self.obs_per_drone)
        return torch.FloatTensor(obs).to(self.device)

    def _batch_actions(self, actions: np.ndarray) -> torch.Tensor:
        """把 flatten 动作 reshape 成 [num_drones, act_per_drone] 张量。"""
        act = np.asarray(actions, dtype=np.float32).reshape(self.num_drones, self.act_per_drone)
        return torch.FloatTensor(act).to(self.device)

    def select_actions(self, global_state: np.ndarray, deterministic: bool = False) -> Tuple[np.ndarray, np.ndarray]:
        # 整批一次前向（[num_drones, obs_per_drone]），替代 101 次 batch=1 循环
        obs_batch = self._batch_obs(global_state)
        mean, log_std = self.policy(obs_batch)  # [num_drones, act_per_drone]

        if deterministic:
            action = mean
        else:
            std = torch.exp(log_std)
            dist = torch.distributions.Normal(mean, std)
            action = dist.sample()
        action = torch.clamp(action, -1.0, 1.0)

        # per-agent log_prob（shape=[num_drones]），
        # 更新时逐 agent 算 ratio，避免 N 大时联合 log_prob 求和/平均导致的
        # ratio 压缩（平均→exp^(1/N)≈1→policy_loss≈0）或 KL 爆炸（求和→×N）
        log_prob = torch.distributions.Normal(mean, torch.exp(log_std)).log_prob(action).sum(dim=-1)

        return action.detach().cpu().numpy().flatten(), log_prob.detach().cpu().numpy().astype(np.float32)

    def get_log_prob(self, global_state: np.ndarray, actions: np.ndarray) -> np.ndarray:
        """用"实际执行动作"重算 per-agent log_prob（shape=[num_drones]）。

        安全层（SafetyLayer）可能修正动作后才喂给动力学，若仍存修正前动作的
        log_prob，则 实际执行策略 ≠ 学习策略，重要性采样失效 → 策略发散。
        必须在 step 后用 info['executed_actions'] 重算。
        """
        obs_batch = self._batch_obs(global_state)
        act_batch = self._batch_actions(actions)
        with torch.no_grad():
            mean, log_std = self.policy(obs_batch)
            std = torch.exp(log_std)
            dist = torch.distributions.Normal(mean, std)
            log_prob = dist.log_prob(act_batch).sum(dim=-1)
        return log_prob.cpu().numpy().astype(np.float32)

    def get_value(self, global_state: np.ndarray) -> "float | np.ndarray":
        """状态价值。

        centralized_scalar → float（旧行为）；per_agent → [num_drones] 数组，
        作为 GAE 的 per-agent 价值基线（buffer_values 堆叠为 [T, N]）。
        """
        with torch.no_grad():
            state_tensor = torch.FloatTensor(global_state).unsqueeze(0).to(self.device)
            raw = self.value(state_tensor)  # [1, output_dim]
            if self.critic_mode == 'per_agent':
                # 归一化尺度 → 反归一化为真实回报尺度（与 GAE 中 rewards 同量纲）
                flat = raw.squeeze(0).cpu().numpy()
                return self.value_norm.denormalize(flat).astype(np.float32)
            # value 网络输出为归一化尺度，反归一化为真实回报尺度（与 GAE 中 rewards 同量纲）
            norm_value = raw.item()
            return float(self.value_norm.denormalize(np.array([norm_value]))[0])

    def store_transition(
        self,
        global_state: np.ndarray,
        actions: np.ndarray,
        reward: float,
        log_probs: np.ndarray,
        done: bool,
        value: "float | np.ndarray",
    ):
        """log_probs 为 per-agent 数组（shape=[num_drones]）。
        value：centralized_scalar 为 float，per_agent 为 [num_drones] 数组（buffer 堆叠为 [T,N]）。"""
        if self.buffer_states is None:
            self.buffer_states = [global_state]
            self.buffer_actions = [actions]
            self.buffer_log_probs = [np.asarray(log_probs, dtype=np.float32)]
            self.buffer_rewards = [reward]
            self.buffer_dones = [done]
            self.buffer_values = [value]
        else:
            self.buffer_states.append(global_state)
            self.buffer_actions.append(actions)
            self.buffer_log_probs.append(np.asarray(log_probs, dtype=np.float32))
            self.buffer_rewards.append(reward)
            self.buffer_dones.append(done)
            self.buffer_values.append(value)

    def compute_gae(
        self,
        rewards: np.ndarray,
        values: np.ndarray,
        dones: np.ndarray
    ) -> Tuple[np.ndarray, np.ndarray]:
        advantages = []
        last_gae = 0

        for t in reversed(range(len(rewards))):
            if t == len(rewards) - 1:
                next_value = 0
            else:
                next_value = values[t + 1]

            delta = rewards[t] + self.gamma * next_value * (1 - dones[t]) - values[t]
            last_gae = delta + self.gamma * self.gae_lambda * (1 - dones[t]) * last_gae
            advantages.insert(0, last_gae)

        advantages = np.array(advantages)
        returns = advantages + values
        # E22 长轨迹数值稳定：returns 可能巨大（3000步累积），clip 防 value_loss 爆炸
        # （实测长距离多列 loss 4.7e12）。clip 到合理范围，保留正常 returns，只限极端。
        # 【2026-09-19 治本】①硬 clip 仅兜底数值，加 ②per-trajectory winsorization：
        # 按 done=1 切分轨迹，对每条轨迹内 returns 分位裁剪，抑制单条极端轨迹（爆发期
        # 谓深负的暴力 AB 轨迹）污染 value 网络——非单点突变，而是按轨迹粒度治理。
        returns = np.clip(returns, -2e5, 2e5)
        returns = self._winsorize_by_traj(returns, dones, lo_q=0.02, hi_q=0.98)
        # 【ADR-021 方向 B】per_agent：按 agent 维度各自标准化（每 agent 减自身均值除自身标准差），
        # advantage / returns 均为 [T, N]；centralized_scalar：与改造前完全一致，全局标准化 [T] 标量。
        if self.critic_mode == 'per_agent' and advantages.ndim == 2:
            advantages = ((advantages - advantages.mean(axis=0, keepdims=True))
                          / (advantages.std(axis=0, keepdims=True) + 1e-8))
        else:
            advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        return advantages, returns

    def _winsorize_by_traj(
        self,
        returns: np.ndarray,
        dones: np.ndarray,
        lo_q: float = 0.02,
        hi_q: float = 0.98,
    ) -> np.ndarray:
        """按 done=1 划轨迹边界，抑制单条极端轨迹对 value 目标的污染。

        n_env 并行轨迹在 buffer 里是"轨迹1全部步 + 轨迹2全部步 + ..."连续 append，
        轨迹结束步 done=1（该轨迹最后一步），故以 done>0 为切点分段。

        语义（精确治理"单条极端轨迹"）：对每条轨迹用其**累计 return** sample 判定是否
        为异常轨迹（超出全部轨迹累计 return 的 [lo_q, hi_q] 分位）。仅对异常轨迹整体
        用累计分位上限 clip，正常轨迹**完全不动**——这正是"抑制破线深负轨迹污染 value、
        不误伤正常梯度"的意图。段长 <4 视为样本太少跳过。
        """
        out = np.array(returns, dtype=np.float64, copy=True)
        traj_ends = np.where(np.asarray(dones) > 0)[0]
        starts = np.concatenate(([0], traj_ends + 1))
        ends = np.concatenate((traj_ends + 1, [len(returns)]))
        segs = [(s, e) for s, e in zip(starts, ends) if e - s >= 4]
        if len(segs) < 4:
            return out  # 轨迹太少，分位不稳，跳过
        cum = np.array([np.sum(out[s:e]) for s, e in segs], dtype=np.float64)
        lo = float(np.quantile(cum, lo_q))
        hi = float(np.quantile(cum, hi_q))
        for (s, e), c in zip(segs, cum):
            if c < lo:  # 异常深负累计（暴力AB破线轨迹）→ 均摊抬升到 lo 分位累计，
                out[s:e] += (lo - c) / (e - s)  # 保持段内相对形状，仅抑制整体污染
        return out

    def update(self) -> Dict[str, float]:
        if self.buffer_states is None or len(self.buffer_states) < self.batch_size:
            # 【2026-10-07 非静默】样本不足时原本直接 return 0 → 日志里只表现为“该集 loss=0”，
            # 无法区分“训练正常但指标接近 0”与“本集根本没更新”。改为显式记录：
            # DI×短窗导致 buffer<batch_size 时（如 DI=25×窗500×n_env4=80<128），
            # 本集跳过更新，样本**累积**到下次（buffer 不清空）→ 实测表现为“每两集更新一次”。
            n_buf = 0 if self.buffer_states is None else len(self.buffer_states)
            logging.info(
                f"[update 跳过] buffer 样本 {n_buf} < batch_size {self.batch_size}；"
                f"本集不更新，样本累积至下次")
            return {'total_loss': 0.0}

        states = torch.FloatTensor(np.array(self.buffer_states)).to(self.device)
        actions = torch.FloatTensor(np.array(self.buffer_actions)).to(self.device)
        # buffer_log_probs 是 per-agent 数组列表，先 np.array 堆叠成 [batch, num_drones]，
        # 避免 torch 直接对 list 构造触发 UserWarning + 慢路径
        old_log_probs = torch.FloatTensor(np.array(self.buffer_log_probs)).to(self.device)
        rewards = np.array(self.buffer_rewards)
        dones = np.array(self.buffer_dones)
        values = np.array(self.buffer_values)

        # 用原始奖励计算 GAE：advantages 内部已标准化（尺度无关），
        # returns = advantages + values 为真实回报尺度，供 value_norm 归一化。
        # E4 稳健性防御：若 rewards/returns 含 inf/NaN（reward 或 value 数值发散），
        # 跳过本次 update 保留旧策略，防止策略权重被推到 NaN（观测到 Ep60 后
        # Normal 分布 loc 变 NaN 崩溃）。
        if not np.all(np.isfinite(rewards)):
            logging.warning("rewards 含 inf/NaN，跳过本次更新")
            self._clear_buffer()
            return self._zero_stats()
        if not np.all(np.isfinite(values)):
            logging.warning("values 含 inf/NaN，跳过本次更新")
            self._clear_buffer()
            return self._zero_stats()
        self.reward_rms.update(rewards)
        advantages, returns = self.compute_gae(rewards, values, dones)
        if not np.all(np.isfinite(advantages)) or not np.all(np.isfinite(returns)):
            logging.warning("advantages/returns 含 inf/NaN，跳过本次更新")
            self._clear_buffer()
            return self._zero_stats()
        # value 目标归一化（PopArt 简化版）：value 网络拟合 O(1) 尺度的 returns，
        # 避免 |returns| ~ 1e4~1e5 时 value_loss ~1e8 导致数值爆炸 / 阈值误杀 / 梯度被 clip 吞没
        self.value_norm.update(returns)
        returns_norm = self.value_norm.normalize(returns)

        advantages = torch.FloatTensor(advantages).to(self.device)
        returns_norm = torch.FloatTensor(returns_norm).to(self.device)

        total_policy_loss = 0.0
        total_value_loss = 0.0
        total_entropy = 0.0
        total_grad_norm = 0.0
        approx_kl = 0.0  # 【2026-09-30 X2】末轮 KL（epochs=0/早停不触发时保持 0）

        for epoch in range(self.epochs):
            indices = np.random.permutation(len(states))

            for start in range(0, len(states), self.batch_size):
                end = start + self.batch_size
                batch_indices = indices[start:end]

                batch_states = states[batch_indices]
                batch_actions = actions[batch_indices]
                batch_old_log_probs = old_log_probs[batch_indices]
                batch_advantages = advantages[batch_indices]
                batch_returns = returns_norm[batch_indices]  # 归一化 returns 作为 value 训练目标

                # per-agent log_prob（shape [batch, num_drones]）→ per-agent ratio，
                # 避免联合 log_prob 求和(×N)/平均(exp^(1/N))导致 ratio 爆炸或坍缩。
                # 整批一次前向：把 [batch, num_drones*obs_per_drone] reshape 成
                # [batch*num_drones, obs_per_drone] 送入共享策略（替代 N 次逐车循环）
                flat_obs = batch_states.view(-1, self.obs_per_drone)       # [batch*N, obs_dim]
                flat_act = batch_actions.view(-1, self.act_per_drone)     # [batch*N, act_dim]

                mean, log_std = self.policy(flat_obs)                      # [batch*N, act_dim]
                # E4 稳健性防御：策略输出 NaN 时跳过（防止权重被推到 NaN 后崩溃，
                # 观测到 Ep60 后 policy 输出全部 NaN）
                if not torch.isfinite(mean).all() or not torch.isfinite(log_std).all():
                    logging.warning("策略输出含 NaN，跳过本次更新")
                    self._clear_buffer()
                    return self._zero_stats()
                std = torch.exp(log_std)
                dist = torch.distributions.Normal(mean, std)

                log_prob_flat = dist.log_prob(flat_act).sum(dim=-1)        # [batch*N]
                entropy_flat = dist.entropy().sum(dim=-1)                  # [batch*N]

                new_log_probs = log_prob_flat.view(len(batch_indices), self.num_drones)  # [batch, N]
                entropy = entropy_flat.mean()

                ratio = torch.exp(new_log_probs - batch_old_log_probs)  # [batch, num_drones]

                # 【ADR-021 方向 B】advantage 形状：
                #   per_agent → [batch, N]，每 agent 各自信用，直接相乘（不广播）；
                #   centralized_scalar → [batch] 标量，unsqueeze(-1) 广播到每个 agent（旧行为）。
                if self.critic_mode == 'per_agent' and batch_advantages.ndim == 2:
                    adv_term = batch_advantages  # [batch, N]
                else:
                    adv_term = batch_advantages.unsqueeze(-1)  # [batch, 1] → 广播
                surr1 = ratio * adv_term
                surr2 = torch.clamp(ratio, 1 - self.clip_epsilon, 1 + self.clip_epsilon) * adv_term
                # 在 batch × agents 上平均（per-agent surrogate，MAPPO 共享策略标准做法）
                policy_loss = -torch.min(surr1, surr2).mean()

                # 【ADR-021 方向 B】价值输出形状显式对齐（不用 .squeeze()：batch=1 时
                # squeeze 会把 [1,N] 压成 [N]，与 returns 广播出错）：
                #   per_agent → [batch, N]；centralized_scalar → [batch]。
                _raw_v = self.value(batch_states)
                if self.critic_mode == 'per_agent':
                    new_values = _raw_v.view(len(batch_indices), self.num_drones)
                else:
                    new_values = _raw_v.view(len(batch_indices))

                if self.use_clipped_value_loss:
                    clipped_values = batch_returns + torch.clamp(
                        new_values - batch_returns,
                        -self.clip_epsilon,
                        self.clip_epsilon
                    )
                    value_loss = 0.5 * torch.max(
                        (new_values - batch_returns) ** 2,
                        (clipped_values - batch_returns) ** 2
                    ).mean()
                else:
                    value_loss = 0.5 * (new_values - batch_returns).pow(2).mean()

                total_loss = policy_loss + self.value_coef * value_loss - self.entropy_coef * entropy

                if not torch.isfinite(total_loss):
                    logging.warning(f"Loss非有限值 ({total_loss.item():.2f})，跳过本次更新")
                    self._clear_buffer()
                    return self._zero_stats()

                self.optimizer.zero_grad()
                total_loss.backward()

                # E4 稳健性防御：梯度含 NaN/inf 时跳过 step（clip_grad_norm_ 对 NaN 无效，
                # 会把 grad clip 成 NaN 再写回权重 → 策略崩溃。观测到 Ep60 后权重 NaN）。
                grad_ok = True
                for p in list(self.policy.parameters()) + list(self.value.parameters()):
                    if p.grad is not None and not torch.isfinite(p.grad).all():
                        grad_ok = False
                        break
                if not grad_ok:
                    logging.warning("梯度含 NaN/inf，跳过本次 step")
                    self.optimizer.zero_grad()
                    self._clear_buffer()
                    return {'total_loss': 0.0}

                # 【2026-09-19 治本②】value 与 policy 梯度分离约束：
                # 先对 value 网络独立 clip 到更紧上限（max_grad_norm*0.5），再对整体 clip，
                # 防止单条极端 returns 让 value 大步漂移（终段 loss 爆 1.283 的直接源头）。
                value_sep_norm = torch.nn.utils.clip_grad_norm_(
                    list(self.value.parameters()), self.max_grad_norm * 0.5
                )
                grad_norm = torch.nn.utils.clip_grad_norm_(
                    list(self.policy.parameters()) + list(self.value.parameters()),
                    self.max_grad_norm
                )
                total_grad_norm += grad_norm.item()
                self.optimizer.step()

                total_policy_loss += policy_loss.item()
                total_value_loss += value_loss.item()
                total_entropy += entropy.item()

            # per-agent KL（batch × agents 平均），避免联合 log_prob 求和导致 KL 被 N 倍放大
            # 【2026-09-19 治本②】收紧早停阈值：1.5→1.2（0.015→0.012），终段不再放任
            # epoch 滑到 7~10 才触发，抑制 value 被极端轨迹带偏后的连波策略漂移。
            # 【诊断-2026-10-03 尺度解耦】原判据 `mean((Δlogp)²)` 是**平方差**而非 KL：
            # 量纲随 log-prob 尺度（受动作 std / 维度）漂移，同一次策略变化会因尺度不同
            # 判定不同 → 早停触发与否与"真实分布位移"脱钩。改用标准 PPO 一阶 KL 估计
            # `mean(Δlogp)`（近似 KL(π_old‖π_new)，尺度可比），阈值语义保持 target_kl。
            approx_kl = (batch_old_log_probs - new_log_probs).mean().item()
            if approx_kl > self.target_kl * 1.2:
                logging.info(f"KL早停: {approx_kl:.4f} > {self.target_kl * 1.2:.4f} (epoch {epoch + 1}/{self.epochs})")
                break

        self.training_step += 1
        self._clear_buffer()

        num_updates = self.epochs * max((len(states) + self.batch_size - 1) // self.batch_size, 1)
        return {
            'total_loss': (total_policy_loss + total_value_loss) / num_updates,
            'policy_loss': total_policy_loss / num_updates,
            'value_loss': total_value_loss / num_updates,
            'entropy': total_entropy / num_updates,
            'grad_norm': total_grad_norm / num_updates,
            # 【2026-09-30 X2】补落盘：让"训练后期 value 发散"可证伪/可证真。
            # approx_kl = 末轮 per-agent KL（早停阈值 target_kl*1.2 的判定量）；
            # value_norm_std = PopArt 归一化尺度，其异常收缩 = 价值尺度漂移的直接证据。
            'approx_kl': float(approx_kl),
            'value_norm_mean': float(self.value_norm.mean),
            'value_norm_std': float(self.value_norm.std),
        }

    @staticmethod
    def _zero_stats() -> dict:
        """跳过更新时的零值统计（字段与正常返回一致，避免下游 CSV/日志缺列）。"""
        return {'total_loss': 0.0, 'policy_loss': 0.0, 'value_loss': 0.0,
                'entropy': 0.0, 'grad_norm': 0.0, 'approx_kl': 0.0,
                'value_norm_mean': 0.0, 'value_norm_std': 1.0}

    def _clear_buffer(self):
        self.buffer_states = None
        self.buffer_actions = None
        self.buffer_log_probs = None
        self.buffer_rewards = None
        self.buffer_dones = None
        self.buffer_values = None

    # -- checkpoint 钩子（save/load 协议在 BaseRLAgent） ------------------
    def _checkpoint_payload(self) -> dict:
        import random as _random
        return {
            'policy_state_dict': self.policy.state_dict(),
            'value_state_dict': self.value.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'training_step': self.training_step,
            # value 归一化统计量（重要：推理时反归一化依赖它）
            'value_norm_mean': self.value_norm.mean,
            'value_norm_std': self.value_norm.std,
            'value_norm_count': self.value_norm.count,
            'reward_rms_mean': self.reward_rms.mean,
            'reward_rms_var': self.reward_rms.var,
            'reward_rms_count': self.reward_rms.count,
            # 【续训】RNG 状态：完整续训时恢复，使确定性 env 下续训可复现
            'np_rng_state': np.random.get_state(),
            'py_rng_state': _random.getstate(),
            'torch_rng_state': torch.get_rng_state(),
        }

    def _restore_checkpoint(self, checkpoint: dict) -> None:
        import random as _random
        self.policy.load_state_dict(checkpoint['policy_state_dict'])
        self.value.load_state_dict(checkpoint['value_state_dict'])
        # weights_only 续训时不含优化器状态（见 BaseRLAgent._WEIGHTS_ONLY_STRIP）
        if 'optimizer_state_dict' in checkpoint:
            self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.training_step = checkpoint.get('training_step', 0)
        if 'value_norm_mean' in checkpoint:
            self.value_norm.mean = checkpoint['value_norm_mean']
            self.value_norm.std = checkpoint['value_norm_std']
            self.value_norm.count = checkpoint.get('value_norm_count', 0)
        if 'reward_rms_mean' in checkpoint:
            self.reward_rms.mean = checkpoint['reward_rms_mean']
            self.reward_rms.var = checkpoint['reward_rms_var']
            self.reward_rms.count = checkpoint.get('reward_rms_count', 0)
        # RNG 状态恢复（旧版 checkpoint 无此键 → 跳过，保持 set_seed 后的状态）
        if 'np_rng_state' in checkpoint:
            np.random.set_state(checkpoint['np_rng_state'])
        if 'py_rng_state' in checkpoint:
            _random.setstate(checkpoint['py_rng_state'])
        if 'torch_rng_state' in checkpoint:
            # torch.load(map_location=device) 会把该 ByteTensor 也搬到 GPU，
            # 而 set_rng_state 只接受 CPU ByteTensor → 显式 .cpu()
            st = checkpoint['torch_rng_state']
            torch.set_rng_state(st.cpu() if torch.is_tensor(st) else st)