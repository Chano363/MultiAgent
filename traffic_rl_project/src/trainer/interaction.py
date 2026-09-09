"""统一训练框架：InteractionPolicy —— 内层"env↔agent 逐步契约"策略对象。

外层骨架（episode 循环 bookkeeping / curriculum / best-checkpoint / artifacts /
metadata）统一在 train_runner.TrainRunner；这里只承载真正因算法而异的逐步交互：
  单列 MAPPO(L1, notch量化+安全层log_prob重算)
  fleet MAPPO(platoon/decompose, reshape+可选 semi-MDP)
  单列 DQN(dqn_cyclic, 每步DQN)
  每列 CoorDQN(fair_dqn, 每列独立DQN)
"""
import numpy as np

from src.algorithms.mappo_agent import MAPPOAgent
from src.trainer.specs.cyclic_spec import quantize_to_notch


class InteractionPolicy:
    """接口：act(obs)->(env_action, value, aux)；observe(...) 存转移(+DQN在线update)；
    end_episode()->metrics(MAPPO update)。"""

    def act(self, obs):
        raise NotImplementedError

    def observe(self, obs, env_action, value, next_obs, reward, done, info, aux):
        raise NotImplementedError

    def end_episode(self):
        return {}


class MappoSingleInteraction(InteractionPolicy):
    """L1：单列 MAPPO。obs=(1,4) cyclic；动作 notch 量化 + 安全层 log_prob 重算。"""

    def __init__(self, agent: MAPPOAgent, env, num_vehicles, action_kind='notch', reward_fn=None):
        self.agent = agent
        self.env = env
        self.num_vehicles = num_vehicles
        self.action_kind = action_kind          # 'notch' 或 'continuous'
        self.reward_fn = reward_fn

    def act(self, obs):
        flat = np.asarray(obs).flatten()
        actions, log_prob = self.agent.select_actions(flat)
        self.last_throttle = None
        if self.action_kind == 'notch':
            throttle = quantize_to_notch(float(np.clip(actions[0], -1.0, 1.0)))
            if abs(throttle - float(actions[0])) > 1e-4:
                log_prob = self.agent.get_log_prob(flat, np.array([throttle]))
            self.last_throttle = throttle
            env_act = np.full(self.num_vehicles, throttle)
        else:
            self.last_throttle = float(actions[0])
            env_act = np.full(self.num_vehicles, self.last_throttle)
        value = self.agent.get_value(flat)
        return env_act, value, (flat, actions, log_prob)

    def observe(self, obs, env_action, value, next_obs, reward, done, info, aux):
        flat, actions, log_prob = aux
        # 安全层修正后重算 log_prob（V5.1）
        executed = info.get('executed_actions')
        if executed is not None and info.get('actions_modified', True):
            actions = np.array([executed[0]])
            log_prob = self.agent.get_log_prob(flat, actions)
        self.agent.store_transition(flat, actions, reward, log_prob, done, value)

    def end_episode(self):
        return self.agent.update()


class MappoFleetInteraction(InteractionPolicy):
    """platoon/decompose：多列 MAPPO。obs=env per-train obs；reshape 到 (num_agents, act_dim)。"""

    def __init__(self, agent: MAPPOAgent, env, num_agents, act_dim, interaction_action='continuous',
                 decision_interval=1, reward_fn=None):
        self.agent = agent
        self.env = env
        self.num_agents = num_agents
        self.act_dim = act_dim
        self.decision_interval = decision_interval
        self.reward_fn = reward_fn

    def act(self, obs, step=0, horizon=1):
        flat = np.asarray(obs).flatten()
        actions, log_prob = self.agent.select_actions(flat)
        env_act = actions.reshape(self.num_agents, self.act_dim)
        value = self.agent.get_value(flat)
        return env_act, value, (flat, actions, log_prob)

    def observe(self, obs, env_action, value, next_obs, reward, done, info, aux):
        flat, actions, log_prob = aux
        # 分层/映射模式：策略分布定义在 RL 输出动作空间，log_prob 用原始 actions 即可
        self.agent.store_transition(flat, actions, reward, log_prob, done, value)

    def end_episode(self):
        return self.agent.update()


class DqnSingleInteraction(InteractionPolicy):
    """dqn_cyclic：单列 DQN，每步 select_action->throttle、store、update。"""

    def __init__(self, agent, num_vehicles, reward_fn=None):
        self.agent = agent
        self.num_vehicles = num_vehicles
        self.reward_fn = reward_fn

    def act(self, obs, eval_mode=False):
        o = np.asarray(obs).flatten()
        idx = self.agent.select_action(o, eval_mode=eval_mode)
        throttle = self.agent.action_to_throttle(idx)
        self.last_throttle = throttle if not eval_mode else self.last_throttle
        return np.full(self.num_vehicles, throttle), None, (o, idx, throttle)

    def observe(self, obs, env_action, value, next_obs, reward, done, info, aux):
        o, idx, throttle = aux
        nxt = np.asarray(next_obs).flatten()
        self.agent.store_transition(o, idx, reward, nxt, done)
        self.agent.update()

    def end_episode(self):
        return {}


class CoorDqnFleetInteraction(InteractionPolicy):
    """fair_dqn：每列独立 CoorDQNAgent，输出离散 coor_adj。"""

    def __init__(self, agents, env, num_trains, reward_fn=None):
        self.agents = agents
        self.env = env
        self.num_trains = num_trains
        self.reward_fn = reward_fn

    def act(self, obs, eval_mode=False):
        o = np.asarray(obs)
        coor = np.zeros((self.num_trains, 1), dtype=np.float32)
        idxs = []
        for i in range(self.num_trains):
            oi = o[i].flatten()
            ai = self.agents[i].select_action(oi, eval_mode=eval_mode)
            coor[i, 0] = self.agents[i].action_to_coor(ai)
            idxs.append(ai)
        return coor, None, (o, idxs)

    def observe(self, obs, env_action, value, next_obs, reward, done, info, aux):
        o, idxs = aux
        nxt = np.asarray(next_obs)
        for i in range(self.num_trains):
            oi = o[i].flatten()
            ni = nxt[i].flatten()
            ai = self.agents[i].select_action(oi)   # ε-greedy（与旧脚本一致重取样）
            self.agents[i].store_transition(oi, ai, reward, ni, done)
            self.agents[i].update()

    def end_episode(self):
        return {}