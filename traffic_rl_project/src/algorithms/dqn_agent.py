"""
DQN 智能体（对标 Zhang2024：用 DQN 学单列循环制动）。

Zhang2024（Algorithms 2024,17,190）在朔黄线用 DQN 学单列循环制动，动作=离散制动设置。
本实现：
- Q-network：MLP，输入 obs，输出每个离散动作的 Q 值
- 离散动作空间：参考 Zhang2024 的制动档位（电制动 + 空气制动），映射为 throttle
  （负=制动，正=牵引，0=缓解/惰行）
- 训练：经验回放 + target network + ε-greedy 探索

用作论文 baseline（M-DQN）：单列 DQN 学循环制动，多列场景中每列独立 DQN（无协同），
对比 M1（MAPPO 协同）。
"""
import torch
import torch.nn as nn
import numpy as np
from collections import deque
import random


class DQN(nn.Module):
    """Q 网络：obs -> Q(s, a) 各离散动作的 Q 值。"""

    def __init__(self, obs_dim: int, num_actions: int, hidden: int = 128):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(obs_dim, hidden),
            nn.Tanh(),
            nn.Linear(hidden, hidden),
            nn.Tanh(),
            nn.Linear(hidden, num_actions),
        )

    def forward(self, obs):
        return self.net(obs)


class DQNAgent:
    """DQN 智能体（离散动作，学循环制动）。"""

    # 离散动作 → throttle 映射（对齐循环制动：制动/缓解/牵引）
    # 0: 缓解/惰行(0), 1: SERVICE制动(-0.75), 2: 牵引(+0.5), 3: 弱制动(-0.4)
    ACTION_THROTTLE = np.array([0.0, -0.75, 0.5, -0.4], dtype=np.float32)

    def __init__(
        self,
        obs_dim: int,
        num_actions: int = 4,
        lr: float = 1e-4,
        gamma: float = 0.99,
        tau: float = 0.005,
        buffer_size: int = 100000,
        batch_size: int = 128,
        eps_start: float = 1.0,
        eps_end: float = 0.05,
        eps_decay: float = 0.995,
        device: str = 'cuda',
    ):
        self.obs_dim = obs_dim
        self.num_actions = num_actions
        self.gamma = gamma
        self.tau = tau
        self.batch_size = batch_size
        self.device = torch.device(device if torch.cuda.is_available() else 'cpu')
        self.eps_start = eps_start
        self.eps_end = eps_end
        self.eps_decay = eps_decay
        self.eps = eps_start

        self.q_net = DQN(obs_dim, num_actions).to(self.device)
        self.target_net = DQN(obs_dim, num_actions).to(self.device)
        self.target_net.load_state_dict(self.q_net.state_dict())
        self.optimizer = torch.optim.Adam(self.q_net.parameters(), lr=lr)

        # 经验回放
        self.buffer = deque(maxlen=buffer_size)

    def select_action(self, obs: np.ndarray, eval_mode: bool = False) -> int:
        """ε-greedy 选择离散动作索引。"""
        if not eval_mode and random.random() < self.eps:
            return random.randrange(self.num_actions)
        obs_t = torch.tensor(obs, dtype=torch.float32, device=self.device).unsqueeze(0)
        with torch.no_grad():
            q_vals = self.q_net(obs_t)
        return int(q_vals.argmax(dim=1).item())

    def action_to_throttle(self, action_idx: int) -> float:
        """离散动作 → throttle。"""
        return float(self.ACTION_THROTTLE[action_idx])

    def store_transition(self, obs, action, reward, next_obs, done):
        self.buffer.append((obs.copy(), action, reward, next_obs.copy(), float(done)))

    def update(self) -> float:
        """从经验回放采样训练 Q 网络，返回 loss。"""
        if len(self.buffer) < self.batch_size:
            return 0.0
        batch = random.sample(self.buffer, self.batch_size)
        obs, act, rew, nobs, done = map(np.array, zip(*batch))
        obs_t = torch.tensor(obs, dtype=torch.float32, device=self.device)
        act_t = torch.tensor(act, dtype=torch.long, device=self.device).unsqueeze(1)
        rew_t = torch.tensor(rew, dtype=torch.float32, device=self.device).unsqueeze(1)
        nobs_t = torch.tensor(nobs, dtype=torch.float32, device=self.device)
        done_t = torch.tensor(done, dtype=torch.float32, device=self.device).unsqueeze(1)

        q = self.q_net(obs_t).gather(1, act_t)
        with torch.no_grad():
            q_next = self.target_net(nobs_t).max(dim=1, keepdim=True)[0]
            target = rew_t + self.gamma * (1 - done_t) * q_next
        loss = nn.functional.smooth_l1_loss(q, target)

        self.optimizer.zero_grad()
        loss.backward()
        torch.nn.utils.clip_grad_norm_(self.q_net.parameters(), 1.0)
        self.optimizer.step()

        # 软更新 target 网络
        for tp, p in zip(self.target_net.parameters(), self.q_net.parameters()):
            tp.data.copy_(self.tau * p.data + (1 - self.tau) * tp.data)

        # ε 衰减
        self.eps = max(self.eps * self.eps_decay, self.eps_end)
        return float(loss.item())

    def save(self, path: str):
        torch.save({'q_net': self.q_net.state_dict(), 'eps': self.eps}, path)

    def load(self, path: str):
        ckpt = torch.load(path, map_location=self.device)
        self.q_net.load_state_dict(ckpt['q_net'])
        self.target_net.load_state_dict(ckpt['q_net'])
        self.eps = ckpt.get('eps', 0.05)
