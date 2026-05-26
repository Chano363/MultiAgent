"""
工具函数模块
"""

import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from pathlib import Path
from typing import Dict, List, Any
import json
import yaml


def plot_training_curve(
    rewards: List[float],
    losses: List[float],
    save_path: str = None
):
    """
    绘制训练曲线

    Args:
        rewards: 奖励列表
        losses: 损失列表
        save_path: 保存路径
    """
    fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(12, 4))

    ax1.plot(rewards)
    ax1.set_xlabel('Episode')
    ax1.set_ylabel('Reward')
    ax1.set_title('Training Reward')
    ax1.grid(True)

    ax2.plot(losses)
    ax2.set_xlabel('Update Step')
    ax2.set_ylabel('Loss')
    ax2.set_title('Training Loss')
    ax2.grid(True)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path)
    else:
        plt.show()

    plt.close()


def plot_comparison(
    results: Dict[str, List[float]],
    metric_name: str = 'Waiting Time',
    save_path: str = None
):
    """
    绘制算法对比图

    Args:
        results: 算法名称到指标值的映射
        metric_name: 指标名称
        save_path: 保存路径
    """
    plt.figure(figsize=(10, 6))

    algorithms = list(results.keys())
    values = list(results.values())

    bars = plt.bar(algorithms, values)

    colors = plt.cm.viridis(np.linspace(0, 1, len(algorithms)))
    for bar, color in zip(bars, colors):
        bar.set_color(color)

    plt.xlabel('Algorithm')
    plt.ylabel(metric_name)
    plt.title(f'Algorithm Comparison - {metric_name}')
    plt.xticks(rotation=45)
    plt.grid(axis='y', alpha=0.3)

    plt.tight_layout()

    if save_path:
        plt.savefig(save_path)
    else:
        plt.show()

    plt.close()


def save_results(
    results: Dict[str, Any],
    save_dir: str = "outputs/results"
):
    """
    保存结果到文件，支持追加模式（合并历史数据）

    Args:
        results: 结果字典
        save_dir: 保存目录
    """
    save_dir = Path(save_dir)
    save_dir.mkdir(parents=True, exist_ok=True)

    results_file = save_dir / "results.json"
    
    if results_file.exists():
        try:
            with open(results_file, 'r') as f:
                existing_results = json.load(f)
            
            if 'rewards' in existing_results and 'rewards' in results:
                existing_rewards = existing_results['rewards']
                new_rewards = results['rewards']
                
                if isinstance(existing_rewards, list) and isinstance(new_rewards, list):
                    merged_rewards = existing_rewards + new_rewards
                    results['rewards'] = merged_rewards
                    results['total_episodes'] = len(merged_rewards)
                    
                    if 'best_reward' in existing_results:
                        old_best = existing_results['best_reward']
                        new_best = results.get('best_reward', float('-inf'))
                        results['best_reward'] = max(old_best, new_best)
                    
                    if 'mean_reward' in results:
                        results['mean_reward'] = np.mean(merged_rewards)
                    
                    if 'final_reward' in new_rewards:
                        results['final_reward'] = new_rewards[-1]
        except Exception as e:
            print(f"Failed to merge existing results: {e}")

    def convert_numpy(obj):
        if isinstance(obj, np.floating):
            return float(obj)
        elif isinstance(obj, np.integer):
            return int(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, list):
            return [convert_numpy(item) for item in obj]
        elif isinstance(obj, dict):
            return {key: convert_numpy(value) for key, value in obj.items()}
        else:
            return obj

    results = convert_numpy(results)

    with open(results_file, 'w') as f:
        json.dump(results, f, indent=2)

    with open(save_dir / "results.yaml", 'w') as f:
        yaml.dump(results, f, default_flow_style=False)


def load_results(load_dir: str = "outputs/results") -> Dict[str, Any]:
    """
    加载结果文件

    Args:
        load_dir: 加载目录

    Returns:
        结果字典
    """
    load_dir = Path(load_dir)

    json_path = load_dir / "results.json"
    yaml_path = load_dir / "results.yaml"

    if json_path.exists():
        with open(json_path, 'r') as f:
            return json.load(f)
    elif yaml_path.exists():
        with open(yaml_path, 'r') as f:
            return yaml.safe_load(f)
    else:
        raise FileNotFoundError(f"No results found in {load_dir}")


def compute_statistics(data: List[float]) -> Dict[str, float]:
    """
    计算统计指标

    Args:
        data: 数据列表

    Returns:
        统计指标字典
    """
    return {
        'mean': np.mean(data),
        'std': np.std(data),
        'min': np.min(data),
        'max': np.max(data),
        'median': np.median(data),
        'p25': np.percentile(data, 25),
        'p75': np.percentile(data, 75),
    }


def moving_average(data: List[float], window: int = 10) -> List[float]:
    """
    计算移动平均

    Args:
        data: 数据列表
        window: 窗口大小

    Returns:
        移动平均值列表
    """
    if len(data) < window:
        return data

    cumsum = np.cumsum(data)
    cumsum[window:] = cumsum[window:] - cumsum[:-window]

    return list(cumsum[window - 1:] / window)


class MetricsTracker:
    """指标跟踪器"""

    def __init__(self):
        self.metrics = {
            'rewards': [],
            'losses': [],
            'episode_lengths': [],
            'custom': {}
        }

    def add_reward(self, reward: float):
        self.metrics['rewards'].append(reward)

    def add_loss(self, loss: float):
        self.metrics['losses'].append(loss)

    def add_episode_length(self, length: int):
        self.metrics['episode_lengths'].append(length)

    def add_custom_metric(self, name: str, value: float):
        if name not in self.metrics['custom']:
            self.metrics['custom'][name] = []
        self.metrics['custom'][name].append(value)

    def get_metrics(self) -> Dict[str, Any]:
        return self.metrics

    def reset(self):
        self.metrics = {
            'rewards': [],
            'losses': [],
            'episode_lengths': [],
            'custom': {}
        }

    def save(self, path: str):
        save_results(self.metrics, path)

    def load(self, path: str):
        self.metrics = load_results(path)
