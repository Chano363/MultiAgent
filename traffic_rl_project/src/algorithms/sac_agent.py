"""
Soft Actor-Critic (SAC) 算法实现
支持连续动作空间和多智能体无人机编队控制
"""

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import numpy as np
from typing import List, Dict, Tuple, Optional
import logging


class RunningMeanStd:
    """运行均值和标准差计算类 - 用于奖励归一化"""
    
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


class SACPolicyNetwork(nn.Module):
    """SAC策略网络 - 输出高斯分布的均值和标准差"""

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_sizes: List[int] = [256, 256],
        action_scale: float = 1.0,
        action_bias: float = 0.0
    ):
        super(SACPolicyNetwork, self).__init__()
        
        self.action_scale = torch.tensor(action_scale)
        self.action_bias = torch.tensor(action_bias)
        
        layers = []
        input_dim = state_dim
        
        for hidden_size in hidden_sizes:
            layers.append(nn.Linear(input_dim, hidden_size))
            layers.append(nn.ReLU())
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
        mean = self.mean_layer(features)
        log_std = self.log_std_layer(features)
        log_std = torch.clamp(log_std, min=-20, max=2)
        return mean, log_std
    
    def sample(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor, torch.Tensor]:
        mean, log_std = self.forward(state)
        std = log_std.exp()
        
        normal = torch.distributions.Normal(mean, std)
        x_t = normal.rsample()
        y_t = torch.tanh(x_t)
        action = y_t * self.action_scale + self.action_bias
        
        log_prob = normal.log_prob(x_t)
        log_prob -= torch.log(self.action_scale * (1 - y_t.pow(2)) + 1e-6)
        log_prob = log_prob.sum(1, keepdim=True)
        
        mean = torch.tanh(mean) * self.action_scale + self.action_bias
        
        return action, log_prob, mean


class SACQNetwork(nn.Module):
    """SAC Q网络"""

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_sizes: List[int] = [256, 256]
    ):
        super(SACQNetwork, self).__init__()
        
        layers = []
        input_dim = state_dim + action_dim
        
        for hidden_size in hidden_sizes:
            layers.append(nn.Linear(input_dim, hidden_size))
            layers.append(nn.ReLU())
            input_dim = hidden_size
        
        layers.append(nn.Linear(input_dim, 1))
        
        self.network = nn.Sequential(*layers)
        self._initialize_weights()
    
    def _initialize_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.orthogonal_(m.weight, gain=np.sqrt(2))
                nn.init.constant_(m.bias, 0)
    
    def forward(self, state: torch.Tensor, action: torch.Tensor) -> torch.Tensor:
        x = torch.cat([state, action], dim=1)
        return self.network(x)


class ReplayBuffer:
    """经验回放缓冲区"""
    
    def __init__(self, capacity: int, state_dim: int, action_dim: int):
        self.capacity = capacity
        self.state_dim = state_dim
        self.action_dim = action_dim
        
        self.states = np.zeros((capacity, state_dim), dtype=np.float32)
        self.actions = np.zeros((capacity, action_dim), dtype=np.float32)
        self.rewards = np.zeros(capacity, dtype=np.float32)
        self.next_states = np.zeros((capacity, state_dim), dtype=np.float32)
        self.dones = np.zeros(capacity, dtype=np.float32)
        
        self.size = 0
        self.ptr = 0
    
    def add(self, state, action, reward, next_state, done):
        self.states[self.ptr] = state
        self.actions[self.ptr] = action
        self.rewards[self.ptr] = reward
        self.next_states[self.ptr] = next_state
        self.dones[self.ptr] = done
        
        self.ptr = (self.ptr + 1) % self.capacity
        self.size = min(self.size + 1, self.capacity)
    
    def sample(self, batch_size: int) -> Dict[str, np.ndarray]:
        indices = np.random.randint(0, self.size, size=batch_size)
        
        return {
            'states': self.states[indices],
            'actions': self.actions[indices],
            'rewards': self.rewards[indices],
            'next_states': self.next_states[indices],
            'dones': self.dones[indices]
        }


class SACAgent:
    """Soft Actor-Critic 智能体"""

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        learning_rate: float = 3e-4,
        gamma: float = 0.99,
        tau: float = 0.005,
        alpha: float = 0.2,
        automatic_entropy_tuning: bool = True,
        target_entropy: Optional[float] = None,
        buffer_capacity: int = 1000000,
        batch_size: int = 256,
        device: str = 'cpu'
    ):
        self.state_dim = state_dim
        self.action_dim = action_dim
        self.gamma = gamma
        self.tau = tau
        self.batch_size = batch_size
        
        self.device = torch.device(device)
        logging.info(f"SAC设备: {self.device}")
        
        # 自动熵调整
        self.automatic_entropy_tuning = automatic_entropy_tuning
        if target_entropy is None:
            self.target_entropy = -action_dim
        else:
            self.target_entropy = target_entropy
        
        if self.automatic_entropy_tuning:
            self.log_alpha = torch.tensor(np.log(alpha), requires_grad=True, device=self.device)
            self.alpha_optimizer = optim.Adam([self.log_alpha], lr=learning_rate)
        
        self.alpha = alpha
        
        # 策略网络
        self.policy_net = SACPolicyNetwork(state_dim, action_dim).to(self.device)
        self.policy_optimizer = optim.Adam(self.policy_net.parameters(), lr=learning_rate)
        
        # Q网络（双网络）
        self.q_net1 = SACQNetwork(state_dim, action_dim).to(self.device)
        self.q_net2 = SACQNetwork(state_dim, action_dim).to(self.device)
        
        # 目标Q网络
        self.target_q_net1 = SACQNetwork(state_dim, action_dim).to(self.device)
        self.target_q_net2 = SACQNetwork(state_dim, action_dim).to(self.device)
        
        # 初始化目标网络权重
        self.target_q_net1.load_state_dict(self.q_net1.state_dict())
        self.target_q_net2.load_state_dict(self.q_net2.state_dict())
        
        self.q_optimizer = optim.Adam(
            list(self.q_net1.parameters()) + list(self.q_net2.parameters()),
            lr=learning_rate
        )
        
        # 经验回放缓冲区
        self.buffer = ReplayBuffer(buffer_capacity, state_dim, action_dim)
        
        # 奖励归一化
        self.reward_rms = RunningMeanStd()
    
    def select_action(self, state: np.ndarray, deterministic: bool = False) -> np.ndarray:
        state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
        
        if deterministic:
            _, _, action = self.policy_net.sample(state_tensor)
        else:
            action, _, _ = self.policy_net.sample(state_tensor)
        
        return action.cpu().detach().numpy().flatten()
    
    def store_transition(
        self,
        state: np.ndarray,
        action: np.ndarray,
        reward: float,
        next_state: np.ndarray,
        done: bool
    ):
        self.buffer.add(state, action, reward, next_state, done)
    
    def update(self) -> Dict[str, float]:
        if self.buffer.size < self.batch_size:
            return {
                'total_loss': 0.0,
                'q_loss': 0.0,
                'policy_loss': 0.0,
                'alpha_loss': 0.0,
                'alpha': self.alpha
            }
        
        batch = self.buffer.sample(self.batch_size)
        
        states = torch.FloatTensor(batch['states']).to(self.device)
        actions = torch.FloatTensor(batch['actions']).to(self.device)
        rewards = torch.FloatTensor(batch['rewards']).to(self.device)
        next_states = torch.FloatTensor(batch['next_states']).to(self.device)
        dones = torch.FloatTensor(batch['dones']).to(self.device)
        
        # 奖励归一化
        self.reward_rms.update(batch['rewards'])
        rewards = rewards / torch.sqrt(torch.tensor(self.reward_rms.var + 1e-8, device=self.device))
        
        # 更新Q网络
        with torch.no_grad():
            next_actions, next_log_probs, _ = self.policy_net.sample(next_states)
            q1_target = self.target_q_net1(next_states, next_actions)
            q2_target = self.target_q_net2(next_states, next_actions)
            min_q_target = torch.min(q1_target, q2_target) - self.alpha * next_log_probs
            target_q = rewards.unsqueeze(1) + (1 - dones.unsqueeze(1)) * self.gamma * min_q_target
        
        q1_pred = self.q_net1(states, actions)
        q2_pred = self.q_net2(states, actions)
        
        q_loss1 = F.mse_loss(q1_pred, target_q)
        q_loss2 = F.mse_loss(q2_pred, target_q)
        q_loss = q_loss1 + q_loss2
        
        self.q_optimizer.zero_grad()
        q_loss.backward()
        self.q_optimizer.step()
        
        # 更新策略网络（冻结Q网络）
        for param in self.q_net1.parameters():
            param.requires_grad = False
        for param in self.q_net2.parameters():
            param.requires_grad = False
        
        actions_sample, log_probs, _ = self.policy_net.sample(states)
        q1 = self.q_net1(states, actions_sample)
        q2 = self.q_net2(states, actions_sample)
        min_q = torch.min(q1, q2)
        
        policy_loss = (self.alpha * log_probs - min_q).mean()
        
        self.policy_optimizer.zero_grad()
        policy_loss.backward()
        self.policy_optimizer.step()
        
        for param in self.q_net1.parameters():
            param.requires_grad = True
        for param in self.q_net2.parameters():
            param.requires_grad = True
        
        # 更新目标Q网络
        self._update_target_networks()
        
        # 更新alpha（如果启用自动调整）
        alpha_loss = 0.0
        if self.automatic_entropy_tuning:
            alpha_loss = -(self.log_alpha * (log_probs + self.target_entropy).detach()).mean()
            
            self.alpha_optimizer.zero_grad()
            alpha_loss.backward()
            self.alpha_optimizer.step()
            
            self.alpha = self.log_alpha.exp()
        
        return {
            'total_loss': q_loss.item() + policy_loss.item() + (alpha_loss.item() if isinstance(alpha_loss, torch.Tensor) else alpha_loss),
            'q_loss': q_loss.item(),
            'policy_loss': policy_loss.item(),
            'alpha_loss': alpha_loss.item() if isinstance(alpha_loss, torch.Tensor) else alpha_loss,
            'alpha': self.alpha.item() if isinstance(self.alpha, torch.Tensor) else self.alpha
        }
    
    def _update_target_networks(self):
        """软更新目标网络"""
        self._soft_update(self.q_net1, self.target_q_net1)
        self._soft_update(self.q_net2, self.target_q_net2)
    
    def _soft_update(self, source, target):
        for source_param, target_param in zip(source.parameters(), target.parameters()):
            target_param.data.copy_(
                self.tau * source_param.data + (1 - self.tau) * target_param.data
            )
    
    def save(self, path: str):
        checkpoint = {
            'policy_net_state_dict': self.policy_net.state_dict(),
            'q_net1_state_dict': self.q_net1.state_dict(),
            'q_net2_state_dict': self.q_net2.state_dict(),
            'target_q_net1_state_dict': self.target_q_net1.state_dict(),
            'target_q_net2_state_dict': self.target_q_net2.state_dict(),
            'policy_optimizer_state_dict': self.policy_optimizer.state_dict(),
            'q_optimizer_state_dict': self.q_optimizer.state_dict(),
            'reward_rms_mean': self.reward_rms.mean,
            'reward_rms_var': self.reward_rms.var,
            'reward_rms_count': self.reward_rms.count
        }
        
        if self.automatic_entropy_tuning:
            checkpoint['log_alpha'] = self.log_alpha
            checkpoint['alpha_optimizer_state_dict'] = self.alpha_optimizer.state_dict()
        
        torch.save(checkpoint, path)
        logging.info(f"SAC模型已保存到: {path}")
    
    def load(self, path: str):
        checkpoint = torch.load(path, map_location=self.device)
        
        self.policy_net.load_state_dict(checkpoint['policy_net_state_dict'])
        self.q_net1.load_state_dict(checkpoint['q_net1_state_dict'])
        self.q_net2.load_state_dict(checkpoint['q_net2_state_dict'])
        self.target_q_net1.load_state_dict(checkpoint['target_q_net1_state_dict'])
        self.target_q_net2.load_state_dict(checkpoint['target_q_net2_state_dict'])
        self.policy_optimizer.load_state_dict(checkpoint['policy_optimizer_state_dict'])
        self.q_optimizer.load_state_dict(checkpoint['q_optimizer_state_dict'])
        
        # 恢复 reward_rms 状态
        if 'reward_rms_mean' in checkpoint:
            self.reward_rms.mean = checkpoint['reward_rms_mean']
            self.reward_rms.var = checkpoint['reward_rms_var']
            self.reward_rms.count = checkpoint.get('reward_rms_count', 0)
        
        # 恢复 alpha
        if self.automatic_entropy_tuning and 'log_alpha' in checkpoint:
            self.log_alpha = checkpoint['log_alpha']
            self.alpha_optimizer.load_state_dict(checkpoint['alpha_optimizer_state_dict'])
        
        logging.info(f"SAC模型已从 {path} 加载")
