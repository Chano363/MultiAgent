"""
神经网络模块
"""

import torch
import torch.nn as nn
from typing import Tuple


class ActorCriticNetwork(nn.Module):
    """Actor-Critic共享网络"""

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_sizes: Tuple[int, ...] = (256, 256),
        shared_layers: bool = True
    ):
        super(ActorCriticNetwork, self).__init__()

        self.shared_layers = shared_layers

        if shared_layers:
            self.shared = nn.Sequential(
                nn.Linear(state_dim, hidden_sizes[0]),
                nn.ReLU(),
                nn.Linear(hidden_sizes[0], hidden_sizes[1]),
                nn.ReLU(),
            )

            self.actor = nn.Linear(hidden_sizes[1], action_dim)
            self.critic = nn.Sequential(
                nn.Linear(hidden_sizes[1], hidden_sizes[1] // 2),
                nn.ReLU(),
                nn.Linear(hidden_sizes[1] // 2, 1)
            )
        else:
            self.actor = nn.Sequential(
                nn.Linear(state_dim, hidden_sizes[0]),
                nn.ReLU(),
                nn.Linear(hidden_sizes[0], hidden_sizes[1]),
                nn.ReLU(),
                nn.Linear(hidden_sizes[1], action_dim)
            )

            self.critic = nn.Sequential(
                nn.Linear(state_dim, hidden_sizes[0]),
                nn.ReLU(),
                nn.Linear(hidden_sizes[0], hidden_sizes[1]),
                nn.ReLU(),
                nn.Linear(hidden_sizes[1], 1)
            )

    def forward(self, state: torch.Tensor) -> Tuple[torch.Tensor, torch.Tensor]:
        """前向传播，返回策略和价值"""
        if self.shared_layers:
            shared_features = self.shared(state)
            action_logits = self.actor(shared_features)
            value = self.critic(shared_features)
        else:
            action_logits = self.actor(state)
            value = self.critic(state)

        return action_logits, value


class MultiAgentActor(nn.Module):
    """多智能体Actor网络"""

    def __init__(
        self,
        state_dim: int,
        action_dim: int,
        hidden_sizes: Tuple[int, ...] = (128, 128),
        share_weights: bool = True
    ):
        super(MultiAgentActor, self).__init__()

        self.share_weights = share_weights

        layers = []
        input_dim = state_dim

        for hidden_size in hidden_sizes:
            layers.extend([
                nn.Linear(input_dim, hidden_size),
                nn.ReLU(),
            ])
            input_dim = hidden_size

        self.feature_extractor = nn.Sequential(*layers) if not share_weights else None

        if share_weights:
            self.policy_head = nn.Sequential(
                nn.Linear(state_dim, hidden_sizes[0]),
                nn.ReLU(),
                nn.Linear(hidden_sizes[0], hidden_sizes[1]),
                nn.ReLU(),
                nn.Linear(hidden_sizes[1], action_dim),
                nn.Softmax(dim=-1)
            )
        else:
            self.policy_head = nn.Sequential(
                nn.Linear(hidden_sizes[-1], action_dim),
                nn.Softmax(dim=-1)
            )

    def forward(self, state: torch.Tensor) -> torch.Tensor:
        if self.share_weights:
            return self.policy_head(state)
        else:
            features = self.feature_extractor(state)
            return self.policy_head(features)


class MultiAgentCritic(nn.Module):
    """多智能体Critic网络"""

    def __init__(
        self,
        state_dim: int,
        action_dim: int = 0,
        hidden_sizes: Tuple[int, ...] = (256, 256),
        centralized: bool = True,
        share_weights: bool = True
    ):
        super(MultiAgentCritic, self).__init__()

        self.centralized = centralized
        self.share_weights = share_weights

        if centralized:
            critic_input_dim = state_dim + action_dim if action_dim > 0 else state_dim
        else:
            critic_input_dim = state_dim

        layers = []
        input_dim = critic_input_dim

        for hidden_size in hidden_sizes:
            layers.extend([
                nn.Linear(input_dim, hidden_size),
                nn.ReLU(),
            ])
            input_dim = hidden_size

        layers.append(nn.Linear(input_dim, 1))

        if share_weights:
            self.critic_network = nn.Sequential(*layers)
        else:
            self.critic_network = nn.Sequential(*layers)

    def forward(self, state: torch.Tensor, action: torch.Tensor = None) -> torch.Tensor:
        if self.centralized and action is not None:
            critic_input = torch.cat([state, action], dim=-1)
        else:
            critic_input = state

        return self.critic_network(critic_input)
