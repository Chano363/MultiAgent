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


def _smooth(data: List[float], window: int = 5) -> List[float]:
    """移动平均平滑"""
    if len(data) < window:
        return data
    smoothed = []
    for i in range(len(data)):
        start = max(0, i - window // 2)
        end = min(len(data), i + window // 2 + 1)
        smoothed.append(np.mean(data[start:end]))
    return smoothed


def plot_training_curve(
    rewards: List[float],
    losses: List[float],
    velocities: List[float] = None,
    formation_errors: List[float] = None,
    height_errors: List[float] = None,
    save_path: str = None,
    mode: str = "compact"
):
    """
    绘制训练曲线

    Args:
        rewards: 奖励列表
        losses: 损失列表
        velocities: 速度列表
        formation_errors: 编队误差列表
        height_errors: 高度误差列表
        save_path: 保存路径
        mode: "compact"（一行多子图，训练日志用）| "presentation"（独立大图，PPT汇报用）

    Returns:
        生成的图片文件路径列表
    """
    saved_paths = []
    metrics = [
        ("rewards", rewards, "Episode", "Episode Reward", "Training Reward", "#2196F3"),
        ("losses", losses, "Update Step", "Loss", "Training Loss", "#FF9800"),
        ("velocities", velocities, "Episode", "Speed (m/s)", "Average Velocity", "#4CAF50"),
        ("formation_errors", formation_errors, "Episode", "Error (m)", "Formation Error", "#FF9800"),
        ("height_errors", height_errors, "Episode", "Error (m)", "Height Error", "#F44336"),
    ]
    metrics = [(n, d, xl, yl, t, c) for n, d, xl, yl, t, c in metrics if d is not None and len(d) >= 2]

    if mode == "presentation":
        for name, data, xlabel, ylabel, title, color in metrics:
            fig, ax = plt.subplots(figsize=(12, 5))
            ax.plot(data, alpha=0.3, color=color, linewidth=0.8, label="Raw")
            ax.plot(_smooth(data), color=color, linewidth=2.5, label="Smoothed (w=5)")
            ax.set_xlabel(xlabel, fontsize=14, fontweight="bold")
            ax.set_ylabel(ylabel, fontsize=14, fontweight="bold")
            ax.set_title(title, fontsize=16, fontweight="bold", pad=15)
            ax.legend(fontsize=12, loc="best")
            ax.grid(True, alpha=0.3)
            ax.tick_params(labelsize=12)
            if name == "rewards":
                best_idx = int(np.argmax(data))
                ax.annotate(f"Best: {data[best_idx]:.1f}\n@ ep {best_idx}",
                            xy=(best_idx, data[best_idx]),
                            xytext=(best_idx * 0.7, data[best_idx] * 1.1),
                            fontsize=11, fontweight="bold", color=color,
                            arrowprops=dict(arrowstyle="->", color=color, lw=2))
            if save_path:
                base = Path(save_path)
                p = base.parent / f"{base.stem}_{name}{base.suffix}"
                saved_paths.append(str(p))
            else:
                p = None
            plt.tight_layout()
            plt.savefig(p if p else save_path, dpi=150, bbox_inches="tight")
            plt.close()
        return saved_paths

    num_plots = len(metrics)
    fig, axes = plt.subplots(1, num_plots, figsize=(4 * num_plots, 4))
    if num_plots == 1:
        axes = [axes]

    for idx, (_, data, xlabel, ylabel, title, color) in enumerate(metrics):
        ax = axes[idx]
        ax.plot(data, color=color)
        ax.set_xlabel(xlabel)
        ax.set_ylabel(ylabel)
        ax.set_title(title)
        ax.grid(True)

    plt.tight_layout()
    if save_path:
        plt.savefig(save_path)
        saved_paths.append(save_path)
    else:
        plt.show()
    plt.close()
    return saved_paths


def plot_from_results(
    results_dir: str,
    output_dir: str = None,
    modes: List[str] = None
):
    """
    从已有的训练结果文件加载数据并生成图表

    Args:
        results_dir: 结果文件目录（包含 results.json）
        output_dir: 图片输出目录（默认为 results_dir 下的 charts 子目录）
        modes: 生成模式列表，可选 "compact"、"presentation"，默认两种都生成

    Returns:
        生成的图片文件路径列表
    """
    if modes is None:
        modes = ["compact", "presentation"]

    results = load_results(results_dir)
    saved_paths = []

    algorithm = results.get('algorithm', 'agent').lower()

    reward_config = results.get('reward_config', {})
    reward_fn = results.get('reward_fn', '')
    print(f"\n{'='*60}")
    print(f"加载训练结果: {results_dir}")
    print(f"  算法: {algorithm.upper()}")
    if reward_config:
        print(f"  奖励配置权重: {reward_config}")
    if reward_fn:
        fn_preview = ''.join(reward_fn.split('\n')[:6])
        print(f"  奖励函数 (前6行):\n{fn_preview}")
    print(f"{'='*60}\n")

    if output_dir is None:
        output_dir = str(Path(results_dir) / "charts")
    Path(output_dir).mkdir(parents=True, exist_ok=True)

    for mode in modes:
        if mode == "compact":
            save_path = str(Path(output_dir) / f"{algorithm}_training_compact.png")
        else:
            save_path = str(Path(output_dir) / f"{algorithm}_training_{mode}.png")

        paths = plot_training_curve(
            rewards=results.get('rewards', []),
            losses=results.get('losses', []),
            velocities=results.get('mean_velocities', None),
            formation_errors=results.get('formation_errors', None),
            height_errors=results.get('height_errors', None),
            save_path=save_path,
            mode=mode
        )
        saved_paths.extend(paths)

    return saved_paths


def generate_training_charts(
    rewards: List[float],
    losses: List[float],
    velocities: List[float] = None,
    formation_errors: List[float] = None,
    height_errors: List[float] = None,
    algorithm: str = "agent",
    output_dir: str = "outputs/results",
    modes: List[str] = None
):
    """
    训练结束后实时生成图表（同时生成 compact 和 presentation 两种模式）

    Args:
        rewards: 奖励列表
        losses: 损失列表
        velocities: 速度列表
        formation_errors: 编队误差列表
        height_errors: 高度误差列表
        algorithm: 算法名称
        output_dir: 结果输出目录
        modes: 生成模式列表，默认两种都生成

    Returns:
        生成的图片文件路径列表
    """
    if modes is None:
        modes = ["compact", "presentation"]

    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    saved_paths = []

    for mode in modes:
        if mode == "compact":
            save_path = str(output_dir / f"{algorithm.lower()}_formation_training_results.png")
        else:
            save_path = str(output_dir / f"{algorithm.lower()}_training_{mode}.png")

        paths = plot_training_curve(
            rewards=rewards,
            losses=losses,
            velocities=velocities,
            formation_errors=formation_errors,
            height_errors=height_errors,
            save_path=save_path,
            mode=mode
        )
        saved_paths.extend(paths)

    return saved_paths


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
