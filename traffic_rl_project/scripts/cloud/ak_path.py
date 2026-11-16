"""解析阿里云 AK 文件路径（兼容 Windows 原生 Python 与 WSL 内 Python）。

背景（2026-11-10 实测）：凭据文件放在 **Windows 用户目录** 下，Windows 侧
`~` 指 `%USERPROFILE%`，而 WSL 侧 `~` 指 Linux home —— 两者不是同一位置。
曾在 WSL 里用 `~/` 查过并误判"文件不存在"。

解析顺序：
1. 环境变量 `ALIYUN_AK_FILE`（显式指定优先）；
2. `~/.aliyun_ak.txt`（Windows 原生 / 已复制到 Linux home 的情形）；
3. WSL 下经 Windows 用户目录的挂载点（先 `wslpath` 换算，再退回 `/mnt/<盘>/Users/<用户>`）。

文件格式：第 1 行 AccessKeyId、第 2 行 AccessKeySecret、第 3 行可选默认地域。
本模块**只返回路径**，不读取/打印任何密钥内容。
"""
import getpass
import os
import subprocess

_AK_NAME = ".aliyun_ak.txt"


def _is_wsl() -> bool:
    try:
        with open("/proc/version", encoding="utf-8", errors="ignore") as f:
            return "microsoft" in f.read().lower()
    except OSError:
        return False


def _wsl_windows_profile():
    """把 Windows 的 USERPROFILE 换算成 WSL 路径；失败返回 None。"""
    try:
        out = subprocess.run(
            ["powershell.exe", "-NoProfile", "-Command", "$env:USERPROFILE"],
            capture_output=True, text=True, timeout=15,
        )
        win = (out.stdout or "").strip().splitlines()
        if not win:
            return None
        conv = subprocess.run(["wslpath", "-u", win[0].strip()],
                              capture_output=True, text=True, timeout=10)
        return (conv.stdout or "").strip() or None
    except Exception:
        return None


def resolve_ak_file() -> str:
    env = os.environ.get("ALIYUN_AK_FILE")
    if env and os.path.exists(env):
        return env

    home = os.path.join(os.path.expanduser("~"), _AK_NAME)
    if os.path.exists(home):
        return home

    if _is_wsl():
        win_home = _wsl_windows_profile()
        if win_home:
            p = os.path.join(win_home, _AK_NAME)
            if os.path.exists(p):
                return p
        user = getpass.getuser()
        for drive in "cdefgh":
            p = f"/mnt/{drive}/Users/{user}/{_AK_NAME}"
            if os.path.exists(p):
                return p

    return home
