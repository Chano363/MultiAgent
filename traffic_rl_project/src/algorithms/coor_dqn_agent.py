"""
协同阈值 DQN 智能体（公平 baseline：M-DQN-fair）。

【定位】与 M1（MAPPO 协同阈值）完全同架构，只把第2层 RL 算法从 MAPPO 换成 DQN：
- 第1层：规则循环制动 + 车钩力安全层（与 M1/M3/M4 相同，HierarchicalController）
- 第2层：DQN 每列输出离散 coor_adj ∈ [-1,1]（映射为 v_max_adj/v_min_adj 阈值偏移），
  喂给与 M1 完全相同的 HierarchicalController.get_action(train_env, coor_adj)。

与朴素 M-DQN（Zhang2024 式，学单列循环制动、无安全层、无协同）不同，本 agent
是有"规则循环制动 + 车钩力安全层 + DQN 协同"的公平 baseline，可回答审稿人
"DQN 输是因为没协同/没安全层，还是因为 DQN 本身不如 MAPPO"的质疑。

离散动作空间 = 协同阈值偏移档位。obs 与 M1 相同（11 维，train_fleet_env._get_obs）。
"""
import torch
import torch.nn as nn
import numpy as np
from collections import deque
import random


class CoorDQN(nn.Module):
    """Q 网络：obs -> Q(s, a) 各离散协同动作的 Q 值。"""

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


class CoorDQNAgent:
    """DQN 协同阈值智能体（每列独立 DQN 输出 coor_adj）。"""

    # 离散动作 → 协同阈值偏移 coor_adj ∈ [-1,1]（均匀档位，负=延后制动/提前缓解，
    # 正=提前制动/延后缓解，0=无偏移）。经 HierarchicalController 映射为
    # v_max_adj/v_min_adj（限制 ±COOP_LIMIT=±5km/h）。
    # 用奇数量档位保证 0 是中间档（无协同偏移），与 M3（δ=0）可比。
    NUM_ACTIONS = 5
    COOR_GRID = np.linspace(-1.0, 1.0, NUM_ACTIONS, dtype=np.float32)  # [-1,-0.5,0,0.5,1]

    def __init__(
        self,
        obs_dim: int,
        num_actions: int = None,
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
        num_actions = num_actions or self.NUM_ACTIONS
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

        self.q_net = CoorDQN(obs_dim, num_actions).to(self.device)
        self.target_net = CoorDQN(obs_dim, num_actions).to(self.device)
        self.target_net.load_state_dict(self.q_net.state_dict())
        self.optimizer = torch.optim.Adam(self.q_net.parameters(), lr=lr)

        self.buffer = deque(maxlen=buffer_size)

    def select_action(self, obs: np.ndarray, eval_mode: bool = False) -> int:
        """ε-greedy 选择离散协同动作索引。"""
        if not eval_mode and random.random() < self.eps:
            return random.randrange(self.num_actions)
        obs_t = torch.tensor(obs, dtype=torch.float32, device=self.device).unsqueeze(0)
        with torch.no_grad():
            q_vals = self.q_net(obs_t)
        return int(q_vals.argmax(dim=1).item())

    def action_to_coor(self, action_idx: int) -> float:
        """离散动作索引 → coor_adj ∈ [-1,1]。"""
        return float(self.COOR_GRID[action_idx])

    def store_transition(self, obs, action, reward, next_obs, done):
        self.buffer.append((obs.copy(), int(action), float(reward), next_obs.copy(), float(done)))

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
        self.eps = ckpt.get('eps', self.eps_end)
