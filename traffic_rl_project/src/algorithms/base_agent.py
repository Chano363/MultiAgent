"""RL 智能体基类：统一 checkpoint 存档协议（模板方法）+ 共享 DQN 机制。

【自包含 checkpoint 协议 2026-09-10】对标 Ultralytics YOLO 的 best.pt——
save() 把 metadata（git_commit / physics_version / seed / 超参数等，来自
src.metadata.build_metadata）直接嵌入 checkpoint 字典，使单个 .pt 自描述、
可溯源、可复现，不再依赖外置 metadata.json 的弱关联。

向后兼容：旧版裸 checkpoint（无 'metadata' 键）load 不受影响；
load() 返回完整 checkpoint 字典，调用方可按需读取 metadata。

子类职责（两个钩子）：
- _checkpoint_payload(): 返回要落盘的状态字典（权重/优化器/统计量等）
- _restore_checkpoint(ckpt): 从 checkpoint 恢复内部状态（需兼容旧版裸存档）
"""
import logging
import random
from collections import deque
from typing import Optional

import numpy as np
import torch
import torch.nn as nn


class BaseRLAgent:
    """所有 RL 智能体的共同基类（checkpoint 存档模板方法）。"""

    # -- 子类必须实现的两个钩子 ------------------------------------------
    def _checkpoint_payload(self) -> dict:
        """返回要落盘的状态字典（权重/优化器/统计量等，不含 metadata）。"""
        raise NotImplementedError

    def _restore_checkpoint(self, ckpt: dict) -> None:
        """从 checkpoint 字典恢复内部状态（须兼容旧版裸 checkpoint）。"""
        raise NotImplementedError

    # -- 模板方法：统一 save/load ----------------------------------------
    def save(self, path: str, metadata: Optional[dict] = None) -> None:
        """落盘 checkpoint；传入 metadata 时嵌入字典（自包含协议）。"""
        checkpoint = self._checkpoint_payload()
        if metadata is not None:
            checkpoint['metadata'] = metadata
        torch.save(checkpoint, path)
        logging.info(f"{type(self).__name__} 模型已保存到: {path}")

    def load(self, path: str) -> dict:
        """加载 checkpoint 并恢复内部状态；返回完整字典（含 metadata 若有）。"""
        ckpt = torch.load(path, map_location=self.device, weights_only=False)
        self._restore_checkpoint(ckpt)
        logging.info(f"{type(self).__name__} 模型已从 {path} 加载")
        return ckpt


class QNetworkMLP(nn.Module):
    """共享 Q 网络：obs -> 各离散动作 Q 值（DQN / CoorDQN 同构）。"""

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


class BaseDQNAgent(BaseRLAgent):
    """离散动作 DQN 共同基类：q/target 网络 + 回放 + ε-greedy + 软更新。

    子类只声明：Q 网络类（_q_net_cls）与动作映射（action_to_*）。
    """

    def __init__(self, obs_dim: int, num_actions: int, *, lr: float = 1e-4,
                 gamma: float = 0.99, tau: float = 0.005,
                 buffer_size: int = 100000, batch_size: int = 128,
                 eps_start: float = 1.0, eps_end: float = 0.05,
                 eps_decay: float = 0.995, device: str = 'cuda'):
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

        q_cls = self._q_net_cls()
        self.q_net = q_cls(obs_dim, num_actions).to(self.device)
        self.target_net = q_cls(obs_dim, num_actions).to(self.device)
        self.target_net.load_state_dict(self.q_net.state_dict())
        self.optimizer = torch.optim.Adam(self.q_net.parameters(), lr=lr)

        # 经验回放
        self.buffer = deque(maxlen=buffer_size)

    @classmethod
    def _q_net_cls(cls):
        """子类可覆盖：返回该 agent 使用的 Q 网络类。"""
        return QNetworkMLP

    # -- 交互 ------------------------------------------------------------
    def select_action(self, obs: np.ndarray, eval_mode: bool = False) -> int:
        """ε-greedy 选择离散动作索引。"""
        if not eval_mode and random.random() < self.eps:
            return random.randrange(self.num_actions)
        obs_t = torch.tensor(obs, dtype=torch.float32, device=self.device).unsqueeze(0)
        with torch.no_grad():
            q_vals = self.q_net(obs_t)
        return int(q_vals.argmax(dim=1).item())

    def store_transition(self, obs, action, reward, next_obs, done):
        self.buffer.append((obs.copy(), int(action), float(reward),
                            next_obs.copy(), float(done)))

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

    # -- checkpoint 钩子（DQN 家族共用） ----------------------------------
    def _checkpoint_payload(self) -> dict:
        return {'q_net': self.q_net.state_dict(), 'eps': self.eps}

    def _restore_checkpoint(self, ckpt: dict) -> None:
        self.q_net.load_state_dict(ckpt['q_net'])
        self.target_net.load_state_dict(ckpt['q_net'])
        self.eps = ckpt.get('eps', self.eps_end)
