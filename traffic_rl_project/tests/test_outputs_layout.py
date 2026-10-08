"""outputs/ 布局守卫回归（2026-10-08）。

背景：历史上 outputs/ 根级堆积 92 个散文件，由"临时脚本 + shell 重定向"
（`python tmp_x.py | tee outputs/log_x.txt`）产生，绕过了所有 Python 入口
守卫。根因与溯源见 `docs/logs/learnings/LEARNINGS.md` + EXECUTION_RULES
「产物目录规范」。本用例调用 `scripts/check_outputs_layout.py` 的 `check()`，
把"落盘位置"锁进 pytest——不依赖写入方，因而对任意写法都有效。

规范：`docs/rules/EXECUTION_RULES.md`「产物目录规范（outputs/ 布局）」。
"""
import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "check_outputs_layout", ROOT / "scripts" / "check_outputs_layout.py")
_mod = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(_mod)


def test_no_stray_files_at_outputs_root():
    """R1：outputs/ 根级不得出现任何普通文件。"""
    errors, _ = _mod.check()
    stray = [e for e in errors if "根级出现散文件" in e]
    assert not stray, "outputs/ 根级出现散文件（规范 R1）：\n" + "\n".join(stray)


def test_top_level_dirs_are_registered():
    """§1：一级目录只能是目标树成员或已登记的遗留待迁移目录。"""
    errors, _ = _mod.check()
    unknown = [e for e in errors if "不是目标树的一级分类" in e]
    assert not unknown, "outputs/ 出现未登记的一级目录：\n" + "\n".join(unknown)