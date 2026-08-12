"""
列车纵向动力学模块。

基于 NeTrainSim（VTTI-CSM）提取的 Davis 阻力、牵引力、Karwatzki 制动力公式，
补充多体质量-弹簧-阻尼车钩模型（NeTrainSim 为单质点，无车钩力）。

公式来源：
- 阻力: NeTrainSim car.cpp / locomotive.cpp getResistance (Davis)
- 牵引: NeTrainSim locomotive.cpp getTractiveForce + getHyperbolicThrottleCoef
- 制动: NeTrainSim traincomponent.cpp getBrakingForce (Karwatzki)
- 车钩: 本项目多体扩展（质量-弹簧-阻尼）
"""

from .params import VehicleParams, LocomotiveParams, CouplerParams, TrainConsist
from .resistance import resistance_force_n
from .tractive import tractive_force, throttle_coefficient
from .braking import braking_force, brake_shoe_friction, BrakeShoeType
from .coupler import coupler_force
from .train import TrainDynamics

__all__ = [
    'VehicleParams', 'LocomotiveParams', 'CouplerParams', 'TrainConsist',
    'resistance_force_n', 'tractive_force', 'throttle_coefficient',
    'braking_force', 'brake_shoe_friction', 'BrakeShoeType',
    'coupler_force', 'TrainDynamics',
]
