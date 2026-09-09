"""统一训练框架：Registry —— 算法/环境/交互 构建注册表。

集中 import + 按 ExperimentConfig 构建 (env, agents, interaction)，
避免各脚本四处散落 import；后续新算法/环境只需 register 一项。
"""
import numpy as np

from src.environments.train_env import TrainFormationEnv
from src.environments.train_fleet_env import TrainFleetEnv
from src.algorithms.mappo_agent import MAPPOAgent
from src.algorithms.dqn_agent import DQNAgent
from src.algorithms.coor_dqn_agent import CoorDQNAgent

from src.trainer.interaction import (
    MappoSingleInteraction, MappoFleetInteraction,
    DqnSingleInteraction, CoorDqnFleetInteraction,
)


def _build_env(cfg):
    if cfg.env_type == 'single':
        return TrainFormationEnv(cfg.env_cfg)
    if cfg.env_type == 'fleet':
        return TrainFleetEnv(cfg.env_cfg)
    raise KeyError(f"[registry] 未支持 env_type: {cfg.env_type}")


def _build_agents(env, cfg, device):
    p = dict(cfg.algo_params or {})
    if cfg.algorithm == 'mappo':
        if cfg.interaction == 'mappo_single':
            params = dict(num_drones=1, obs_per_drone=4, act_per_drone=1, learning_rate=5e-5)
            params.update(p)
            return MAPPOAgent(device=device, **params)
        # mappo_fleet / decompose
        act_dim = int(getattr(env, 'act_dim', 1))
        od = int(getattr(env, 'obs_dim', 11))
        # agent 数：decompose 模式 = 每列机车总和（num_agents），否则 = 列车数（num_trains）
        nt = int(getattr(env, 'num_agents', 0)) or int(getattr(env, 'num_trains', cfg.num_trains))
        params = dict(num_drones=nt, obs_per_drone=od, act_per_drone=act_dim, learning_rate=3e-4)
        params.update(p)
        return MAPPOAgent(device=device, **params)
    if cfg.algorithm == 'dqn':
        params = dict(obs_dim=4, num_actions=4)
        params.update(p)
        return DQNAgent(device=device, **params)
    if cfg.algorithm == 'coor_dqn':
        od = int(getattr(env, 'obs_dim', 11))
        nt = int(getattr(env, 'num_trains', cfg.num_trains))
        params = dict(obs_dim=od)
        params.update(p)
        return [CoorDQNAgent(device=device, **params) for _ in range(nt)]
    raise KeyError(f"[registry] 未支持 algorithm: {cfg.algorithm}")


def _build_interaction(env, agents, cfg):
    # agent 数：decompose 模式 = 每列机车总和（num_agents），否则 = 列车数（num_trains）
    nt = int(getattr(env, 'num_agents', 0)) or int(getattr(env, 'num_trains', cfg.num_trains))
    if cfg.interaction == 'mappo_single':
        return MappoSingleInteraction(agents, env, num_vehicles=env.num_vehicles,
                                      action_kind=cfg.action)
    if cfg.interaction == 'mappo_fleet':
        act_dim = int(getattr(env, 'act_dim', 1))
        return MappoFleetInteraction(agents, env, num_agents=nt, act_dim=act_dim,
                                     decision_interval=cfg.decision_interval)
    if cfg.interaction == 'dqn_single':
        return DqnSingleInteraction(agents, num_vehicles=env.num_vehicles)
    if cfg.interaction == 'coor_dqn_fleet':
        return CoorDqnFleetInteraction(agents, env, num_trains=nt)
    raise KeyError(f"[registry] 未支持 interaction: {cfg.interaction}")


class Registry:
    """统一构建入口。"""

    @staticmethod
    def build(cfg, device: str):
        env = _build_env(cfg)
        agents = _build_agents(env, cfg, device)
        inter = _build_interaction(env, agents, cfg)
        return env, agents, inter