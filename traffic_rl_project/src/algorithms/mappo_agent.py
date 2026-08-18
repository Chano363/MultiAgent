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

    def __init__(self, eps: float = 1e-8):
        self.mean = 0.0
        self.std = 1.0
        self.count = 0
        self.eps = eps

    def update(self, returns: np.ndarray):
        """用一批 returns 增量更新 running mean/std（Welford）。"""
        x = np.asarray(returns, dtype=np.float64)
        n = len(x)
        if n == 0:
            return
        batch_mean = float(np.mean(x))
        batch_var = float(np.var(x))
        batch_count = n
        total_count = self.count + batch_count
        delta = batch_mean - self.mean
        new_mean = self.mean + delta * batch_count / total_count
        m_a = self.std**2 * self.count
        m_b = batch_var * batch_count
        M2 = m_a + m_b + delta**2 * self.count * batch_count / total_count
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
        use_layer_norm: bool = True
    ):
        super(ContinuousPolicyNetwork, self).__init__()
        self.use_layer_norm = use_layer_norm
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
        log_std = torch.clamp(log_std, min=-4.0, max=2.0)
        return mean, log_std


class CentralizedValueNetwork(nn.Module):
    def __init__(
        self,
        state_dim: int,
        hidden_sizes: List[int] = [512, 256, 128],
        use_layer_norm: bool = True
    ):
        super(CentralizedValueNetwork, self).__init__()
        self.use_layer_norm = use_layer_norm
        layers = []
        input_dim = state_dim

        for hidden_size in hidden_sizes:
            layers.append(nn.Linear(input_dim, hidden_size))
            if use_layer_norm:
                layers.append(nn.LayerNorm(hidden_size))
            layers.append(nn.Tanh())
            input_dim = hidden_size

        layers.append(nn.Linear(input_dim, 1))
        self.network = nn.Sequential(*layers)
        self._initialize_weights()

    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.orthogonal_(m.weight, gain=np.sqrt(2))
                nn.init.constant_(m.bias, 0)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.network(state)


class MAPPOAgent:
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
    ):
        self.num_drones = num_drones
        self.obs_per_drone = obs_per_drone
        self.act_per_drone = act_per_drone
        self.total_obs_dim = num_drones * obs_per_drone
        self.total_act_dim = num_drones * act_per_drone
        self.gamma = gamma
        self.gae_lambda = gae_lambda
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
            hidden_sizes=[256, 128]
        ).to(self.device)

        self.value = CentralizedValueNetwork(
            self.total_obs_dim,
            hidden_sizes=[512, 256, 128]
        ).to(self.device)

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
        self.value_norm = ValueNorm()
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

    def get_value(self, global_state: np.ndarray) -> float:
        with torch.no_grad():
            state_tensor = torch.FloatTensor(global_state).unsqueeze(0).to(self.device)
            # value 网络输出为归一化尺度，反归一化为真实回报尺度（与 GAE 中 rewards 同量纲）
            norm_value = self.value(state_tensor).item()
            return float(self.value_norm.denormalize(np.array([norm_value]))[0])

    def store_transition(
        self,
        global_state: np.ndarray,
        actions: np.ndarray,
        reward: float,
        log_probs: np.ndarray,
        done: bool,
        value: float
    ):
        """log_probs 为 per-agent 数组（shape=[num_drones]）。"""
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
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        return advantages, returns

    def update(self) -> Dict[str, float]:
        if self.buffer_states is None or len(self.buffer_states) < self.batch_size:
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
            return {'total_loss': 0.0}
        if not np.all(np.isfinite(values)):
            logging.warning("values 含 inf/NaN，跳过本次更新")
            self._clear_buffer()
            return {'total_loss': 0.0}
        self.reward_rms.update(rewards)
        advantages, returns = self.compute_gae(rewards, values, dones)
        if not np.all(np.isfinite(advantages)) or not np.all(np.isfinite(returns)):
            logging.warning("advantages/returns 含 inf/NaN，跳过本次更新")
            self._clear_buffer()
            return {'total_loss': 0.0}
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
                    return {'total_loss': 0.0}
                std = torch.exp(log_std)
                dist = torch.distributions.Normal(mean, std)

                log_prob_flat = dist.log_prob(flat_act).sum(dim=-1)        # [batch*N]
                entropy_flat = dist.entropy().sum(dim=-1)                  # [batch*N]

                new_log_probs = log_prob_flat.view(len(batch_indices), self.num_drones)  # [batch, N]
                entropy = entropy_flat.mean()

                ratio = torch.exp(new_log_probs - batch_old_log_probs)  # [batch, num_drones]

                # advantage 为每步一个标量（集中式 critic），广播到每个 agent
                adv_broad = batch_advantages.unsqueeze(-1)  # [batch, 1]
                surr1 = ratio * adv_broad
                surr2 = torch.clamp(ratio, 1 - self.clip_epsilon, 1 + self.clip_epsilon) * adv_broad
                # 在 batch × agents 上平均（per-agent surrogate，MAPPO 共享策略标准做法）
                policy_loss = -torch.min(surr1, surr2).mean()

                new_values = self.value(batch_states).squeeze()

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
                    return {'total_loss': 0.0}

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
            approx_kl = ((new_log_probs - batch_old_log_probs) ** 2).mean().item()
            if approx_kl > self.target_kl * 1.5:
                logging.info(f"KL早停: {approx_kl:.4f} > {self.target_kl * 1.5:.4f} (epoch {epoch + 1}/{self.epochs})")
                break

        self.training_step += 1
        self._clear_buffer()

        num_updates = self.epochs * max(len(states) // self.batch_size, 1)
        return {
            'total_loss': (total_policy_loss + total_value_loss) / num_updates,
            'policy_loss': total_policy_loss / num_updates,
            'value_loss': total_value_loss / num_updates,
            'entropy': total_entropy / num_updates,
            'grad_norm': total_grad_norm / num_updates
        }

    def _clear_buffer(self):
        self.buffer_states = None
        self.buffer_actions = None
        self.buffer_log_probs = None
        self.buffer_rewards = None
        self.buffer_dones = None
        self.buffer_values = None

    def save(self, path: str):
        checkpoint = {
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
            'reward_rms_count': self.reward_rms.count
        }
        torch.save(checkpoint, path)
        logging.info(f"MAPPO模型已保存到: {path}")

    def load(self, path: str):
        checkpoint = torch.load(path, map_location=self.device)
        self.policy.load_state_dict(checkpoint['policy_state_dict'])
        self.value.load_state_dict(checkpoint['value_state_dict'])
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
        logging.info(f"MAPPO模型已从 {path} 加载")