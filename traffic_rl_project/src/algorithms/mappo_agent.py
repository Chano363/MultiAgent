"""
Multi-Agent Proximal Policy Optimization (MAPPO)
Shared policy + centralized critic for multi-drone formation control.
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
        log_std = torch.clamp(log_std, min=-20, max=2)
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

        self.reward_rms = RunningMeanStd()
        self.training_step = 0

    def select_actions(self, global_state: np.ndarray, deterministic: bool = False) -> Tuple[np.ndarray, float]:
        actions = []
        total_log_prob = 0.0
        for i in range(self.num_drones):
            start = i * self.obs_per_drone
            end = start + self.obs_per_drone
            obs_i = global_state[start:end]
            obs_tensor = torch.FloatTensor(obs_i).unsqueeze(0).to(self.device)

            mean, log_std = self.policy(obs_tensor)
            if deterministic:
                action = mean
            else:
                std = torch.exp(log_std)
                dist = torch.distributions.Normal(mean, std)
                action = dist.sample()
            action = torch.clamp(action, -1.0, 1.0)
            log_prob = torch.distributions.Normal(mean, torch.exp(log_std)).log_prob(action).sum(dim=-1)

            actions.append(action.cpu().detach().numpy().flatten())
            total_log_prob += log_prob.item()

        return np.concatenate(actions), total_log_prob

    def get_value(self, global_state: np.ndarray) -> float:
        with torch.no_grad():
            state_tensor = torch.FloatTensor(global_state).unsqueeze(0).to(self.device)
            return self.value(state_tensor).item()

    def store_transition(
        self,
        global_state: np.ndarray,
        actions: np.ndarray,
        reward: float,
        total_log_prob: float,
        done: bool,
        value: float
    ):
        if self.buffer_states is None:
            self.buffer_states = [global_state]
            self.buffer_actions = [actions]
            self.buffer_log_probs = [total_log_prob]
            self.buffer_rewards = [reward]
            self.buffer_dones = [done]
            self.buffer_values = [value]
        else:
            self.buffer_states.append(global_state)
            self.buffer_actions.append(actions)
            self.buffer_log_probs.append(total_log_prob)
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
        old_log_probs = torch.FloatTensor(self.buffer_log_probs).to(self.device)
        rewards = np.array(self.buffer_rewards)
        dones = np.array(self.buffer_dones)
        values = np.array(self.buffer_values)

        self.reward_rms.update(rewards)
        rewards = rewards / np.sqrt(self.reward_rms.var + 1e-8)

        advantages, returns = self.compute_gae(rewards, values, dones)
        advantages = torch.FloatTensor(advantages).to(self.device)
        returns = torch.FloatTensor(returns).to(self.device)

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
                batch_returns = returns[batch_indices]

                new_total_log_probs = torch.zeros(len(batch_indices), device=self.device)
                batch_entropy = 0.0
                for i in range(self.num_drones):
                    s_start = i * self.obs_per_drone
                    s_end = s_start + self.obs_per_drone
                    a_start = i * self.act_per_drone
                    a_end = a_start + self.act_per_drone

                    obs_i = batch_states[:, s_start:s_end]
                    act_i = batch_actions[:, a_start:a_end]

                    mean, log_std = self.policy(obs_i)
                    std = torch.exp(log_std)
                    dist = torch.distributions.Normal(mean, std)

                    log_prob_i = dist.log_prob(act_i).sum(dim=-1)
                    new_total_log_probs += log_prob_i
                    batch_entropy += dist.entropy().sum(dim=-1).mean()

                entropy = batch_entropy / self.num_drones
                ratio = torch.exp(new_total_log_probs - batch_old_log_probs)

                surr1 = ratio * batch_advantages
                surr2 = torch.clamp(ratio, 1 - self.clip_epsilon, 1 + self.clip_epsilon) * batch_advantages
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

                if total_loss.item() > 1000.0:
                    logging.warning(f"Loss异常 ({total_loss.item():.2f})，跳过本次更新")
                    self._clear_buffer()
                    return {'total_loss': 0.0}

                self.optimizer.zero_grad()
                total_loss.backward()

                grad_norm = torch.nn.utils.clip_grad_norm_(
                    list(self.policy.parameters()) + list(self.value.parameters()),
                    self.max_grad_norm
                )
                total_grad_norm += grad_norm.item()
                self.optimizer.step()

                total_policy_loss += policy_loss.item()
                total_value_loss += value_loss.item()
                total_entropy += entropy.item()

            approx_kl = ((new_total_log_probs - batch_old_log_probs) ** 2).mean().item()
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
        if 'reward_rms_mean' in checkpoint:
            self.reward_rms.mean = checkpoint['reward_rms_mean']
            self.reward_rms.var = checkpoint['reward_rms_var']
            self.reward_rms.count = checkpoint.get('reward_rms_count', 0)
        logging.info(f"MAPPO模型已从 {path} 加载")