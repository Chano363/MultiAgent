"""
多智能体编队控制环境模块
"""

from .train_env import TrainFormationEnv

__all__ = ['TrainFormationEnv']


def __getattr__(name):
    # 惰性导入无人机环境：避免在没有 gym_pybullet_drones 的环境中报错
    if name in ('FormationControlEnv', 'make_formation_control_env'):
        from .formation_control_env import FormationControlEnv, make_formation_control_env
        return locals()[name]
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")