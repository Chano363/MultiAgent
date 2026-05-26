"""
优化后的DQN算法实现
使用Agent Lightning进行模型调优
"""

import torch
import torch.nn as nn
import torch.optim as optim
import torch.nn.functional as F
import numpy as np
from collections import deque
from typing import Optional, Tuple
import logging


class OptimizedQNetwork(nn.Module):
    """优化后的Q网络"""

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_sizes: list = [256, 256, 128],
        use_layer_norm: bool = True
    ):
        super(OptimizedQNetwork, self).__init__()

        self.use_layer_norm = use_layer_norm
        layers = []
        input_dim = state_dim

        for i, hidden_size in enumerate(hidden_sizes):
            layers.append(nn.Linear(input_dim, hidden_size))

            if use_layer_norm:
                layers.append(nn.LayerNorm(hidden_size))

            layers.append(nn.ReLU())
            input_dim = hidden_size

        layers.append(nn.Linear(input_dim, action_dim))

        self.network = nn.Sequential(*layers)

        self._initialize_weights()

    def _initialize_weights(self):
        """初始化权重"""
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.orthogonal_(m.weight, gain=np.sqrt(2))
                nn.init.constant_(m.bias, 0)

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        return self.network(state)


class PrioritizedReplayBuffer:
    """优先经验回放缓冲区"""

    def __init__(self, capacity: int, alpha: float = 0.6, beta: float = 0.4):
        self.capacity = capacity
        self.alpha = alpha
        self.beta = beta
        self.buffer = deque(maxlen=capacity)
        self.priorities = deque(maxlen=capacity)
        self.epsilon = 1e-6

    def push(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool,
        td_error: Optional[float] = None
    ):
        priority = td_error if td_error is not None else 1.0
        self.buffer.append((state, action, reward, next_state, done))
        self.priorities.append(priority ** self.alpha)

    def sample(self, batch_size: int) -> Tuple:
        if len(self.buffer) < batch_size:
            return None

        priorities = np.array(self.priorities)
        probs = priorities / priorities.sum()

        indices = np.random.choice(len(self.buffer), batch_size, p=probs, replace=False)

        weights = (len(self.buffer) * probs[indices]) ** (-self.beta)
        weights = weights / weights.max()

        states, actions, rewards, next_states, dones = zip(*[self.buffer[i] for i in indices])

        return (
            np.array(states),
            np.array(actions),
            np.array(rewards),
            np.array(next_states),
            np.array(dones),
            indices,
            weights
        )

    def update_priorities(self, indices: list, td_errors: list):
        for idx, error in zip(indices, td_errors):
            self.priorities[idx] = abs(error) + self.epsilon

    def __len__(self):
        return len(self.buffer)


class OptimizedDQNAgent:
    """优化后的DQN智能体"""

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        learning_rate: float = 2.5e-4,
        gamma: float = 0.99,
        epsilon_start: float = 1.0,
        epsilon_decay: float = 0.995,
        epsilon_min: float = 0.01,
        buffer_size: int = 10000,
        batch_size: int = 128,
        target_update_freq: int = 100,
        device: str = 'cpu',
        hidden_sizes: list = [256, 256, 128],
        use_layer_norm: bool = True,
        use_prioritized_replay: bool = True,
        double_dqn: bool = True
    ):
        self.action_dim = action_dim
        self.gamma = gamma
        self.epsilon = epsilon_start
        self.epsilon_start = epsilon_start
        self.epsilon_decay = epsilon_decay
        self.epsilon_min = epsilon_min
        self.batch_size = batch_size
        self.target_update_freq = target_update_freq
        self.update_count = 0
        self.double_dqn = double_dqn
        self.use_prioritized_replay = use_prioritized_replay

        self.device = torch.device(device)
        logging.info(f"DQN设备: {self.device}")

        self.q_network = OptimizedQNetwork(
            state_dim, action_dim, hidden_sizes, use_layer_norm
        ).to(self.device)

        self.target_network = OptimizedQNetwork(
            state_dim, action_dim, hidden_sizes, use_layer_norm
        ).to(self.device)

        self.target_network.load_state_dict(self.q_network.state_dict())
        self.target_network.eval()

        self.optimizer = optim.Adam(
            self.q_network.parameters(),
            lr=learning_rate,
            betas=(0.9, 0.999),
            weight_decay=1e-5
        )

        if use_prioritized_replay:
            self.replay_buffer = PrioritizedReplayBuffer(capacity=buffer_size)
        else:
            self.replay_buffer = deque(maxlen=buffer_size)

    def select_action(self, state: np.ndarray, training: bool = True) -> int:
        if training and np.random.rand() < self.epsilon:
            return np.random.randint(self.action_dim)

        with torch.no_grad():
            state_tensor = torch.FloatTensor(state).unsqueeze(0).to(self.device)
            q_values = self.q_network(state_tensor)
            return q_values.argmax(dim=1).item()

    def store_transition(
        self,
        state: np.ndarray,
        action: int,
        reward: float,
        next_state: np.ndarray,
        done: bool
    ):
        if self.use_prioritized_replay:
            self.replay_buffer.push(state, action, reward, next_state, done, td_error=None)
        else:
            self.replay_buffer.append((state, action, reward, next_state, done))

    def update(self) -> float:
        if self.use_prioritized_replay:
            batch_data = self.replay_buffer.sample(self.batch_size)
            if batch_data is None:
                return 0.0

            states, actions, rewards, next_states, dones, indices, weights = batch_data
            weights = torch.FloatTensor(weights).to(self.device)
        else:
            if len(self.replay_buffer) < self.batch_size:
                return 0.0

            batch = np.random.choice(len(self.replay_buffer), self.batch_size, replace=False)
            states, actions, rewards, next_states, dones = zip(
                *[self.replay_buffer[i] for i in batch]
            )
            indices = batch
            weights = torch.ones(self.batch_size).to(self.device)

        states = torch.FloatTensor(np.array(states)).to(self.device)
        actions = torch.LongTensor(actions).to(self.device)
        rewards = torch.FloatTensor(rewards).to(self.device)
        next_states = torch.FloatTensor(np.array(next_states)).to(self.device)
        dones = torch.FloatTensor(dones).to(self.device)

        current_q = self.q_network(states).gather(1, actions.unsqueeze(1)).squeeze(1)

        with torch.no_grad():
            if self.double_dqn:
                next_actions = self.q_network(next_states).argmax(1)
                next_q = self.target_network(next_states).gather(1, next_actions.unsqueeze(1)).squeeze(1)
            else:
                next_q = self.target_network(next_states).max(1)[0]

            target_q = rewards + (1 - dones) * self.gamma * next_q

        td_errors = abs(current_q - target_q).detach().cpu().numpy()

        loss = F.mse_loss(current_q, target_q, reduction='none')
        loss = (loss * weights).mean()

        self.optimizer.zero_grad()
        loss.backward()

        torch.nn.utils.clip_grad_norm_(self.q_network.parameters(), max_norm=10.0)

        self.optimizer.step()

        if self.use_prioritized_replay:
            self.replay_buffer.update_priorities(indices, td_errors)

        self.update_count += 1

        if self.update_count % self.target_update_freq == 0:
            self.update_target_network()

        self.epsilon = max(
            self.epsilon_min,
            self.epsilon * self.epsilon_decay
        )

        return loss.item()

    def update_target_network(self):
        """软更新目标网络"""
        tau = 0.005
        for target_param, param in zip(
            self.target_network.parameters(),
            self.q_network.parameters()
        ):
            target_param.data.copy_(tau * param.data + (1 - tau) * target_param.data)

    def save(self, path: str):
        torch.save({
            'q_network': self.q_network.state_dict(),
            'target_network': self.target_network.state_dict(),
            'optimizer': self.optimizer.state_dict(),
            'epsilon': self.epsilon,
            'update_count': self.update_count
        }, path)

    def load(self, path: str):
        checkpoint = torch.load(path)
        self.q_network.load_state_dict(checkpoint['q_network'])
        self.target_network.load_state_dict(checkpoint['target_network'])
        self.optimizer.load_state_dict(checkpoint['optimizer'])
        self.epsilon = checkpoint.get('epsilon', self.epsilon)
        self.update_count = checkpoint.get('update_count', 0)

    def get_learning_rate(self) -> float:
        return self.optimizer.param_groups[0]['lr']

    def set_learning_rate(self, lr: float):
        for param_group in self.optimizer.param_groups:
            param_group['lr'] = lr
