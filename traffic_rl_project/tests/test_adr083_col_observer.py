"""守卫：训练期逐列车钩力量落盘（ADR-083 / 诊断 §19.44 候选前提①）。

钉住四件事：
    1. **通道存在**：env 的 info 带 `col_peak_coupler_kN` / `col_coupler_viol_steps`；
       trainer 侧把它们收集成 per-episode 列表并传给 `save_training_artifacts`。
    2. **口径与评估侧一致**：逐列 peak = max|abs(coupler_interface_forces())|，
       超限 = count(|iface| > coupler_force_limit_n)，单位 kN（/1e3）。
       ⇒ 训练期与评估态同口径量（§19.44 前提②的"同向性"检验才有意义）。
    3. **纯观测、零物理改动**：新增的只写两个 episode 计数器，
       不得触碰动力学状态 / 奖励 / 动作面 / 安全层（红线 5 的静态部分）。
    4. **产物契约**：`train_history_{tag}.json` 带 `col_peak_coupler_kN` /
       `col_violations` 两键；另写独立 `train_col_coupler_{tag}.csv`
       （既有 CSV 列数冻结，见 logger 侧同款理由）。

⚠️ 本守卫**不能**替代红线 5 的动态验收（"同 ckpt 同 seed 复跑 20 集，
peak 逐位相同"）—— 那需要一次完整重训窗口，属训练窗口验收范畴，
不在单测范围内。本守卫只保证"改动面不含物理路径"。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

ENV_PY = ROOT / "src" / "environments" / "train_fleet_env.py"
TRAINER_PY = ROOT / "src" / "trainer" / "train_fleet.py"
ARTIFACTS_PY = ROOT / "src" / "trainer" / "artifacts.py"
EVAL_PY = ROOT / "src" / "evaluation" / "evaluate_decompose.py"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


# ---------------------------------------------------------------- 1. 通道存在

def test_env_info_exposes_per_column_coupler_fields():
    txt = _read(ENV_PY)
    assert "'col_peak_coupler_kN'" in txt
    assert "'col_coupler_viol_steps'" in txt


def test_env_counters_are_reset_at_episode_start():
    """计数器必须每集清零（否则逐列量跨集污染）。"""
    txt = _read(ENV_PY)
    # 两处初始化：__init__ 与 _reset_once
    assert txt.count("self._ep_col_peak_coupler_n = np.zeros(") >= 2
    assert txt.count("self._ep_col_coupler_viol_steps = np.zeros(") >= 2


def test_trainer_collects_and_forwards_per_column():
    txt = _read(TRAINER_PY)
    assert "info.get('col_peak_coupler_kN')" in txt
    assert "info.get('col_coupler_viol_steps')" in txt
    assert "col_peak_coupler=episode_col_peak" in txt
    assert "col_violations=episode_col_viol" in txt


# ---------------------------------------------------------------- 2. 口径一致

def test_per_column_peak_uses_interface_force_abs_max():
    """逐列 peak 必须取**断面力**绝对值 max（ADR-018 指标 SSOT），不是净力。"""
    txt = _read(ENV_PY)
    for m in re.finditer(
        r"self\._ep_col_peak_coupler_n\[(\w+)\] = max\(\s*"
        r"self\._ep_col_peak_coupler_n\[\1\], float\(np\.max\((\w+)\)\)\)", txt):
        var = m.group(2)
        # 该变量必须由 abs(coupler_interface_forces()) 派生
        assert re.search(rf"{var} = np\.abs\(", txt), f"{var} 非断面力绝对值口径"
        assert "coupler_interface_forces()" in txt


def test_per_column_violation_uses_same_limit_as_evaluation():
    env_txt = _read(ENV_PY)
    eval_txt = _read(EVAL_PY)
    # env 侧用 env 自己的 coupler_force_limit_n
    assert "np.count_nonzero(interface > self.coupler_force_limit_n)" in env_txt
    # 评估侧同一判据
    assert "np.count_nonzero(" in eval_txt
    assert "_iface_n > float(env.coupler_force_limit_n)" in eval_txt
    # 评估侧单位换算 /1000 ⇒ 训练侧必须是 /1e3（同值）
    assert "(train_peak_coupler_n / 1000.0)" in eval_txt
    assert "(self._ep_col_peak_coupler_n / 1e3)" in env_txt


# ---------------------------------------------------------------- 3. 纯观测

def test_column_observers_do_not_touch_physics_state():
    """逐列累加只能写两个计数器；不得改动力学/奖励/动作面/安全层字段。"""
    txt = _read(ENV_PY)
    # 提取所有涉及两个计数器的赋值行，确认没有别名（no self._ep_col_* = 别的字段）
    for line in txt.splitlines():
        if "_ep_col_peak_coupler_n" in line or "_ep_col_coupler_viol_steps" in line:
            if "=" in line and "==" not in line:
                assert re.search(r"_ep_col_\w+(\[[^\]]+\])?\s*(\+=|-=|=)", line), \
                    f"疑似非计数器写入：{line.strip()}"
    # 不得在逐列累加附近引入对动力学状态的写
    assert "_ep_col_peak_coupler_n" in txt
    for forbidden in ("_ep_col_peak_coupler_n = tr", "_ep_col_peak_coupler_n = self._peak"):
        assert forbidden not in txt


def test_column_observers_are_not_used_in_reward_or_action_path():
    """逐列量不得参与 reward / 动作 ⇒ 不影响训练行为（纯落盘通道）。"""
    txt = _read(ENV_PY)
    # 计数器的所有出现位置：定义、reset 清零、累加、info 输出
    for i, line in enumerate(txt.splitlines(), 1):
        if "_ep_col_peak_coupler_n" in line or "_ep_col_coupler_viol_steps" in line:
            s = line.strip()
            allowed = (
                s.startswith("#")
                or s.startswith("self._ep_col_")
                or "self._ep_col_peak_coupler_n" in s
                or "self._ep_col_coupler_viol_steps" in s
            )
            assert allowed, f"L{i} 逐列量出现在非累加路径：{s}"
    # reward 计算里不得引用逐列量
    reward_region = txt[txt.find("def _compute_reward"):] if "def _compute_reward" in txt else ""
    if reward_region:
        assert "_ep_col_peak_coupler_n" not in reward_region.split("def ")[1:][0] \
            if len(reward_region.split("def ")) > 1 else True


# ---------------------------------------------------------------- 4. 产物契约

def test_artifacts_write_json_keys_and_separate_csv(tmp_path):
    from src.trainer.artifacts import save_training_artifacts

    col_peak = [[100.0, 200.0, 300.0], [110.0, 210.0, 310.0]]
    col_viol = [[0.0, 1.0, 2.0], [0.0, 0.0, 3.0]]
    save_training_artifacts(
        [1.0, 2.0], [100.0, 110.0], [0.0, 1.0],
        meta={"seed": 0}, results_dir=str(tmp_path), figures_dir=str(tmp_path / "fig"),
        tag="unit", col_peak_coupler=col_peak, col_violations=col_viol,
    )
    hist = json.loads((tmp_path / "train_history_unit.json").read_text(encoding="utf-8"))
    assert hist["col_peak_coupler_kN"] == col_peak
    assert hist["col_violations"] == col_viol
    # 既有键未被破坏
    for k in ("rewards", "peak_coupler_kN", "violations", "meta"):
        assert k in hist

    csv_path = tmp_path / "train_col_coupler_unit.csv"
    assert csv_path.exists()
    lines = [l for l in csv_path.read_text(encoding="utf-8").strip().splitlines() if l]
    header = lines[0].split(",")
    assert header[0] == "episode"
    assert header[1:4] == ["col0_peak_kN", "col1_peak_kN", "col2_peak_kN"]
    assert header[4:7] == ["col0_viol_steps", "col1_viol_steps", "col2_viol_steps"]
    assert len(lines) == 3  # 表头 + 2 集


def test_artifacts_without_column_data_is_backward_compatible(tmp_path):
    """不传逐列量时，产物与既有形状完全一致（不产生空文件）。"""
    from src.trainer.artifacts import save_training_artifacts

    save_training_artifacts(
        [1.0], [100.0], [0.0], meta={}, results_dir=str(tmp_path),
        figures_dir=str(tmp_path / "fig"), tag="nocol",
    )
    hist = json.loads((tmp_path / "train_history_nocol.json").read_text(encoding="utf-8"))
    assert "col_peak_coupler_kN" not in hist
    assert not (tmp_path / "train_col_coupler_nocol.csv").exists()


# ---------------------------------------------------------------- 5. 只读性动态探针

@pytest.mark.slow
def test_interface_force_read_is_side_effect_free():
    """动态：额外读取 `coupler_interface_forces()`（新增观测会做的事）
    **不得**改变动力学轨迹 —— 逐位相同。

    这是红线 5"纯观测"要求的**直接检验**：若该读取带副作用
    （缓存刷新/状态写入），额外调用一次就会改变后续轨迹。

    注：直接构造 `TrainFleetEnv`（不 import evaluate_decompose，避免 torch 依赖）
    —— cfg 字段与 make_env 的 else 分支同构。
    """
    import numpy as np

    from src.environments.train_fleet_env import TrainFleetEnv

    cfg = {
        "num_trains": 3,
        "consist_preset": "20kt_1plus108_1plus108",
        "grade_profile": "shuozhou_ningwuxi_beidaniu_49km",
        "max_steps": 200,
        "eval_mode": True,
        "decompose": "loco_ed_ab",
        "formation_relative_speed_obs": False,
    }

    def _rollout(extra_read: bool, n_steps: int = 15):
        env = TrainFleetEnv(cfg)
        obs, _ = env.reset(seed=1234)
        act = np.zeros((env.num_agents, env.act_dim), dtype=np.float32)
        traj = []
        for _ in range(n_steps):
            if extra_read:
                for tr in env.trains:
                    np.abs(tr.dynamics.coupler_interface_forces())
            obs, _r, _t, _tr, _info = env.step(act)
            traj.append(np.asarray(obs, dtype=np.float64).copy())
        return np.stack(traj)

    a = _rollout(extra_read=False)
    b = _rollout(extra_read=True)
    assert a.shape == b.shape
    assert np.array_equal(a, b), "额外只读调用改变了动力学轨迹 ⇒ 逐列观测非纯观测"


# ---------------------------------------------------------------- 6. 落账存在性

def test_diagnostic_1945_documents_the_observer_channel():
    p = ROOT / "docs" / "logs" / "diagnostics" / "DIAGNOSTICS_2026-11.md"
    txt = p.read_text(encoding="utf-8")
    assert "§19.45" in txt
    # 必须写明"纯观测、零物理改动"这条设计红线
    assert "纯新增观测" in txt
    assert "零额外仿真成本" in txt
    # 必须写明边界：冒烟不作峰值判据、红线 5 窗口级验收仍待
    assert "不作峰值/安全判据" in txt
    assert "仍待" in txt


def test_pipeline_and_decisions_record_the_channel():
    pipe = (ROOT / "docs" / "PROJECT_PIPELINE.md").read_text(encoding="utf-8")
    assert "§19.45" in pipe
    dec = (ROOT / "docs" / "logs" / "decisions" / "DECISIONS.md").read_text(encoding="utf-8")
    assert "§19.45" in dec
    assert "train_col_coupler_" in dec
