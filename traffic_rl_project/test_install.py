#!/usr/bin/env python3
"""测试 gym-pybullet-drones 安装"""

try:
    from gym_pybullet_drones.envs.MultiHoverAviary import MultiHoverAviary
    print("✓ gym-pybullet-drones 导入成功!")
    
    env = MultiHoverAviary(num_drones=2, render_mode=None)
    print("✓ MultiHoverAviary 环境创建成功!")
    print(f"✓ 状态空间: {env.observation_space.shape}")
    print(f"✓ 动作空间: {env.action_space.shape}")
    
    obs, info = env.reset()
    print("✓ 环境重置成功!")
    print(f"✓ 初始观测形状: {obs.shape}")
    
    action = env.action_space.sample()
    obs, reward, terminated, truncated, info = env.step(action)
    print("✓ 环境 step 成功!")
    
    env.close()
    print("\n🎉 gym-pybullet-drones 安装验证完成!")
    
except Exception as e:
    print(f"✗ 安装验证失败: {e}")