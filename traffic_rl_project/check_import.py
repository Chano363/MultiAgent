import sys
print("Python path:", sys.path)

try:
    import gym_pybullet_drones
    print("gym_pybullet_drones module found")
    print("Version:", gym_pybullet_drones.__version__)
except ImportError as e:
    print("Import error:", e)