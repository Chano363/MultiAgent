"""
优化后的PPO算法实现
支持连续动作空间和多智能体无人机编队控制
"""

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import numpy as np
from typing import List, Dict, Tuple, Optional
import logging


class ContinuousPolicyNetwork(nn.Module):
    """连续动作空间策略网络"""

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_sizes: List[int] = [256, 128, 64],
        use_layer_norm: bool = True
    ):
        super(ContinuousPolicyNetwork, self).__init__()

        self.use_layer_norm = use_layer_norm
        layers = []
        input_dim = state_dim

        for i, hidden_size in enumerate(hidden_sizes):
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


class OptimizedValueNetwork(nn.Module):
    """优化后的价值网络"""

    def __init__(
        self,
        state_dim: int,
        hidden_sizes: List[int] = [512, 256, 128],
        use_layer_norm: bool = True
    ):
        super(OptimizedValueNetwork, self).__init__()

        self.use_layer_norm = use_layer_norm
        layers = []
        input_dim = state_dim

        for i, hidden_size in enumerate(hidden_sizes):
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


class OptimizedPPOAgent:
    """优化后的PPO智能体 - 支持连续动作空间"""

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        learning_rate: float = 2.5e-4,
        gamma: float = 0.99,
        gae_lambda: float = 0.95,
        clip_epsilon: float = 0.15,
        entropy_coef: float = 0.005,
        value_coef: float = 0.5,
        epochs: int = 10,
        batch_size: int = 128,
        n_steps: int = 100,
        max_grad_norm: float = 0.5,
        device: str = 'cpu',
        use_gae: bool = True,
        use_clipped_value_loss: bool = True,
        use_entropy_decay: bool = True
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.gae_lambda = gae_lambda
        self.clip_epsilon = clip_epsilon
        self.initial_clip_epsilon = clip_epsilon
        self.entropy_coef = entropy_coef
        self.initial_entropy_coef = entropy_coef
        self.value_coef = value_coef
        self.epochs = epochs
        self.batch_size = batch_size
        self.n_steps = n_steps
        self.max_grad_norm = max_grad_norm
        self.use_gae = use_gae
        self.use_clipped_value_loss = use_clipped_value_loss
        self.use_entropy_decay = use_entropy_decay

        self.device = torch.device(device)
        logging.info(f"PPO设备: {self.device}")

        self.policy = ContinuousPolicyNetwork(state_dim, action_dim).to(self.device)
        self.value = OptimizedValueNetwork(state_dim).to(self.device)

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

        self.training_step = 0

    def select_action(self, state: np.ndarray) -> Tuple[np.ndarray, float]:
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        mean, log_std = self.policy(state_tensor)
        
        std = torch.exp(log_std)
        dist = torch.distributions.Normal(mean, std)
        
        action = dist.sample()
        action = torch.clamp(action, -1.0, 1.0)
        
        log_prob = dist.log_prob(action).sum(dim=-1)

        return action.cpu().detach().numpy().flatten(), log_prob.item()

    def get_value(self, state: np.ndarray) -> float:
        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            value = self.value(state_tensor)
            return value.item()

    def store_transition(
        self,
        state: np.ndarray,
        action: np.ndarray,
        reward: float,
        log_prob: float,
        done: bool,
        value: float
    ):
        if self.buffer_states is None:
            self.buffer_states = [state]
            self.buffer_actions = [action]
            self.buffer_log_probs = [log_prob]
            self.buffer_rewards = [reward]
            self.buffer_dones = [done]
            self.buffer_values = [value]
        else:
            self.buffer_states.append(state)
            self.buffer_actions.append(action)
            self.buffer_log_probs.append(log_prob)
            self.buffer_rewards.append(reward)
            self.buffer_dones.append(done)
            self.buffer_values.append(value)

    def compute_gae(
        self,
        rewards: List[float],
        values: List[float],
        dones: List[bool]
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
        returns = advantages + np.array(values)
        
        advantages = (advantages - advantages.mean()) / (advantages.std() + 1e-8)
        
        return advantages, returns

    def update(self) -> Dict[str, float]:
        if self.buffer_states is None or len(self.buffer_states) < self.batch_size:
            return {'total_loss': 0.0}

        states = torch.FloatTensor(np.array(self.buffer_states)).to(self.device)
        actions = torch.FloatTensor(np.array(self.buffer_actions)).to(self.device)
        
        # 错误检测：检查动作形状是否正确
        expected_action_dim = self.action_dim
        if len(actions.shape) > 2:
            raise ValueError(
                f"动作形状错误！期望形状 [batch_size, {expected_action_dim}]，"
                f"实际形状 {actions.shape}。请检查存储的是否是flatten后的动作。"
            )
        if actions.shape[-1] != expected_action_dim:
            raise ValueError(
                f"动作维度错误！期望维度 {expected_action_dim}，实际维度 {actions.shape[-1]}。"
            )
        
        old_log_probs = torch.FloatTensor(self.buffer_log_probs).to(self.device)
        rewards = np.array(self.buffer_rewards)
        dones = np.array(self.buffer_dones)
        values = np.array(self.buffer_values)

        advantages, returns = self.compute_gae(rewards, values, dones)
        advantages = torch.FloatTensor(advantages).to(self.device)
        returns = torch.FloatTensor(returns).to(self.device)

        total_policy_loss = 0.0
        total_value_loss = 0.0
        total_entropy_loss = 0.0

        for _ in range(self.epochs):
            indices = np.random.permutation(len(states))
            
            for start in range(0, len(states), self.batch_size):
                end = start + self.batch_size
                batch_indices = indices[start:end]
                
                batch_states = states[batch_indices]
                batch_actions = actions[batch_indices]
                batch_old_log_probs = old_log_probs[batch_indices]
                batch_advantages = advantages[batch_indices]
                batch_returns = returns[batch_indices]

                mean, log_std = self.policy(batch_states)
                std = torch.exp(log_std)
                dist = torch.distributions.Normal(mean, std)
                
                new_log_probs = dist.log_prob(batch_actions).sum(dim=-1)
                entropy = dist.entropy().sum(dim=-1).mean()

                ratio = torch.exp(new_log_probs - batch_old_log_probs)
                
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

                if self.use_entropy_decay:
                    entropy_coef = self.entropy_coef * (1 - self.training_step / 10000)
                else:
                    entropy_coef = self.entropy_coef

                total_loss = policy_loss + self.value_coef * value_loss - entropy_coef * entropy

                self.optimizer.zero_grad()
                total_loss.backward()
                torch.nn.utils.clip_grad_norm_(
                    list(self.policy.parameters()) + list(self.value.parameters()),
                    self.max_grad_norm
                )
                self.optimizer.step()

                total_policy_loss += policy_loss.item()
                total_value_loss += value_loss.item()
                total_entropy_loss += entropy.item()

        self.training_step += 1
        
        self.buffer_states = None
        self.buffer_actions = None
        self.buffer_log_probs = None
        self.buffer_rewards = None
        self.buffer_dones = None
        self.buffer_values = None

        num_updates = self.epochs * (len(states) // self.batch_size)
        
        return {
            'total_loss': total_policy_loss / num_updates + total_value_loss / num_updates,
            'policy_loss': total_policy_loss / num_updates,
            'value_loss': total_value_loss / num_updates,
            'entropy': total_entropy_loss / num_updates
        }

    def save(self, path: str):
        checkpoint = {
            'policy_state_dict': self.policy.state_dict(),
            'value_state_dict': self.value.state_dict(),
            'optimizer_state_dict': self.optimizer.state_dict(),
            'training_step': self.training_step
        }
        torch.save(checkpoint, path)
        logging.info(f"模型已保存到: {path}")

    def load(self, path: str):
        checkpoint = torch.load(path, map_location=self.device)
        self.policy.load_state_dict(checkpoint['policy_state_dict'])
        self.value.load_state_dict(checkpoint['value_state_dict'])
        self.optimizer.load_state_dict(checkpoint['optimizer_state_dict'])
        self.training_step = checkpoint.get('training_step', 0)
        logging.info(f"模型已从 {path} 加载")