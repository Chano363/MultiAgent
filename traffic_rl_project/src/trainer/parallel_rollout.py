"""统一训练框架：并行多环境 rollout（进程级）。

【动机】n_env>1 时 train_runner 的 `for ei in range(n_env)` 是**串行**循环——n_env 条
轨迹依次在单核上跑完，只增加样本量、不缩短墙钟（实测 GPU 0%、12 核仅 1 核忙、
单核物理仿真 ≈47.5 ms/env-step）。本模块把 n_env 条轨迹分发到 n_env 个进程并行执行，
用满多核：单 run 墙钟 ≈ 串行 / min(n_env, 可用核)。

【确定性】轨迹 ei **固定**由第 ei 个 worker 进程执行（非 Pool.map 的自由调度）。
原因：env 底层控制器（如 AB 最小充风/保持计时）在 reset 间存在少量跨回合残留状态，
若任务随机落到不同 worker，残留状态随调度漂移 → 同 seed 结果不可复现。固定映射后
（同 seed 多次运行逐位一致），实测 2 ep 冒烟两次运行 CSV 完全相同。

【等价性声明】
  - 与串行版**语义等价**：每条轨迹仍是独立 rollout（同 reset / 同 decision_interval
    展开 / 同 reward / 同 metric 口径），轨迹结束统一回父进程、**按同一顺序**
    store_transition，再调一次 update()。故 buffer 内容分布与 GAE/update 语义一致。
  - 与串行版**数值不等价**（已声明）：串行版全局 torch RNG 连续消耗；本版每条轨迹用
    独立确定性种子 `_traj_seed(seed, ep, ei)`。两者各自可复现，但互不逐位相同。
  - 仅支持 interaction='mappo_fleet' + obs='env' + reward!='cyclic' + 非异构（其余走串行，
    由 train_runner 侧 gate）。
"""
import multiprocessing
import random

import numpy as np
import torch

from src.trainer.registry import _build_env, _build_agents
from src.trainer.interaction import MappoFleetInteraction


# worker 进程内缓存（每个 worker 独占一份 env/agent，构造一次复用）
_W = {}


def _traj_seed(base_seed: int, ep: int, ei: int) -> int:
    """由 (run seed, 全局回合号, 轨迹序号) 派生的确定性轨迹种子（不依赖调度顺序）。"""
    return int((int(base_seed) * 1000003 + int(ep) * 101 + int(ei)) % (2 ** 31 - 1))


def _worker_init(cfg):
    """在每个 worker 进程内构造自己的 env + agent(CPU) + 交互对象（构造一次复用）。"""
    # 固定单线程：① 避免 worker 间线程超订阅（每个 worker 已独占一核）；
    # ② 保证策略前向的浮点归约顺序确定 → 同 seed 多次运行逐位可复现。
    torch.set_num_threads(1)
    env = _build_env(cfg)
    agent = _build_agents(env, cfg, 'cpu')
    num_agents = int(getattr(env, 'num_agents', 0)) or int(getattr(env, 'num_trains', 1))
    act_dim = int(getattr(env, 'act_dim', 1)) or int(cfg.env_cfg.get('action_dim', 1))
    inter = MappoFleetInteraction(agent, env, num_agents=num_agents, act_dim=act_dim,
                                  decision_interval=cfg.decision_interval)
    _W.update(env=env, agent=agent, inter=inter, cfg=cfg)


def _load_weights(agent, payload):
    """把父进程当前权重（每 episode 一份）载入 worker 本地 agent 副本。

    只同步前向所需：policy/value 权重 + value_norm 的 mean/std（get_value 反归一化用）。
    优化器/value_norm.count 只归父进程（唯一 update 执行者），worker 无需。
    """
    agent.policy.load_state_dict(payload['policy'])
    agent.value.load_state_dict(payload['value'])
    agent.value_norm.mean = payload['vn_mean']
    agent.value_norm.std = payload['vn_std']


def _weights_payload(agent) -> dict:
    """父进程当前权重的可 pickle 快照（跨设备统一搬到 CPU）。"""
    return {
        'policy': {k: v.detach().cpu() for k, v in agent.policy.state_dict().items()},
        'value': {k: v.detach().cpu() for k, v in agent.value.state_dict().items()},
        'vn_mean': float(agent.value_norm.mean),
        'vn_std': float(agent.value_norm.std),
    }


def _rollout_once(payload, init, max_steps, rand_seed):
    """单条轨迹 rollout（在 worker 内执行）。

    逐行镜像 train_runner 串行内层循环（decision_interval 展开 / reward / metric 口径）；
    区别仅是这里**不** store_transition（交由父进程按序重放）与返回 transition 列表。
    """
    env, agent, inter, cfg = _W['env'], _W['agent'], _W['inter'], _W['cfg']
    _load_weights(agent, payload)
    # 每轨迹独立确定性种子：动作采样（torch）+ 起点随机化（env 自有生成器）+ 兜底 np/random
    torch.manual_seed(rand_seed)
    np.random.seed(rand_seed % (2 ** 32))
    random.seed(rand_seed)
    if getattr(env, '_start_rand', None) is not None:
        env._start_rand['rng'] = np.random.default_rng(rand_seed)

    env.max_steps = int(max_steps)
    obs = env.reset(options={'speed': float(init)})
    if isinstance(obs, tuple):
        obs = obs[0]

    di = max(1, int(cfg.decision_interval))
    transitions = []
    ep_reward, ep_peak, ep_viol, step, done = 0.0, 0.0, 0, 0, False
    gap_err_sum, gap_min, gap_steps = 0.0, float('inf'), 0
    while not done and step < max_steps:
        env_act, value, aux = inter.act(obs)
        nxt, acc, term, trunc, info = obs, 0.0, False, False, None
        for _ in range(di):
            nxt, r_step, term, trunc, info = env.step(env_act)
            acc += r_step
            step += 1
            if term or trunc or step >= max_steps:
                break
        reward = acc
        done = term or trunc or step >= max_steps
        flat, actions, log_prob = aux
        transitions.append((flat, actions, float(reward), log_prob, bool(done), value))

        ep_reward += reward
        ep_peak = max(ep_peak, info.get('coupler_force_peak', 0))
        ep_viol = info.get('coupler_limit_violations', 0)
        if info is not None:
            gap_err_sum += float(info.get('gap_err_mean', 0.0))
            gap_min = min(gap_min, float(info.get('gap_min_m', float('inf'))))
            gap_steps += 1
        obs = nxt

    return {
        'transitions': transitions,
        'reward': float(ep_reward),
        'peak': float(ep_peak),
        'viol': int(ep_viol),
        'gap_err': (gap_err_sum / gap_steps) if gap_steps else 0.0,
        'gap_min': (gap_min if gap_steps else 0.0),
    }


def _worker_main(conn, cfg):
    """worker 进程主循环：构造环境后阻塞等待任务（固定映射，避免调度漂移）。"""
    _worker_init(cfg)
    while True:
        msg = conn.recv()
        if msg[0] == 'stop':
            break
        _, payload, init, max_steps, rand_seed = msg
        try:
            conn.send(('ok', _rollout_once(payload, init, max_steps, rand_seed)))
        except Exception as e:  # 失败回传父进程 → 快速失败（不静默降级）
            conn.send(('err', f"{type(e).__name__}: {e}"))


class ParallelRollout:
    """n_env 条轨迹的进程池封装（spawn：避免 fork 复制父进程 CUDA 上下文）。

    轨迹 ei 固定绑定第 ei 个进程 → (ep, ei) → 执行进程恒定 → 同 seed 逐位可复现。
    """

    def __init__(self, cfg, n_env: int):
        self.cfg = cfg
        self.n_env = max(1, int(n_env))
        self._ctx = multiprocessing.get_context('spawn')
        self._procs, self._conns = [], []
        for _ in range(self.n_env):
            parent_conn, child_conn = self._ctx.Pipe()
            p = self._ctx.Process(target=_worker_main, args=(child_conn, cfg), daemon=True)
            p.start()
            child_conn.close()
            self._procs.append(p)
            self._conns.append(parent_conn)

    def run_episode(self, agent, max_steps: int, ep_index: int, inits):
        """跑完本 ep 的 n_env 条轨迹，保序返回结果列表（含 transitions + 轨迹级指标）。"""
        payload = _weights_payload(agent)
        for ei, conn in enumerate(self._conns):
            conn.send(('run', payload, float(inits[ei]), int(max_steps),
                       _traj_seed(int(self.cfg.seed), int(ep_index), ei)))
        results = []
        for conn in self._conns:
            if not conn.poll(7200):
                raise RuntimeError("[parallel_rollout] worker 超时未返回（可能崩溃）")
            tag, body = conn.recv()
            if tag == 'err':
                raise RuntimeError(f"[parallel_rollout] worker 失败：{body}")
            results.append(body)
        return results

    def close(self):
        for conn in self._conns:
            try:
                conn.send(('stop',))
            except Exception:
                pass
        for p in self._procs:
            p.join(timeout=10)
            if p.is_alive():
                p.terminate()
        for conn in self._conns:
            conn.close()
        self._procs, self._conns = [], []