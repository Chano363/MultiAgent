# -*- coding: utf-8 -*-
"""组件注册表：算法 / 物理适配器按名字解析，便于替换与对比实验。

算法插件除实现契约外，可声明以下类属性供"算法管理"域展示：
  display_name  中文名称
  category      算法族（如 tube_mpc / 经典控制 / 规则）
  description   一句话说明
  params        关键参数（名称 -> 默认值），仅作展示，不影响契约
"""
from __future__ import annotations

from typing import Any, Callable, Dict, List

_ALGORITHMS: Dict[str, Callable[..., Any]] = {}
_PLANTS: Dict[str, Callable[..., Any]] = {}

_META_FIELDS = ("display_name", "category", "description", "params")


def register_algorithm(name: str) -> Callable:
    def deco(obj: Callable) -> Callable:
        _ALGORITHMS[name] = obj
        return obj
    return deco


def register_plant(name: str) -> Callable:
    def deco(obj: Callable) -> Callable:
        _PLANTS[name] = obj
        return obj
    return deco


def get_algorithm(name: str, **kwargs: Any) -> Any:
    if name not in _ALGORITHMS:
        raise KeyError(f"未注册的算法: {name}，可用: {sorted(_ALGORITHMS)}")
    return _ALGORITHMS[name](**kwargs)


def get_plant(name: str, **kwargs: Any) -> Any:
    if name not in _PLANTS:
        raise KeyError(f"未注册的物理适配器: {name}，可用: {sorted(_PLANTS)}")
    return _PLANTS[name](**kwargs)


def has_algorithm(name: str) -> bool:
    return name in _ALGORITHMS


def describe_algorithms() -> List[Dict[str, Any]]:
    """算法清单 + 元数据（给"算法管理"域与算法发送下拉框用）。"""
    out: List[Dict[str, Any]] = []
    for key, cls in _ALGORITHMS.items():
        meta: Dict[str, Any] = {"key": key}
        for f in _META_FIELDS:
            meta[f] = getattr(cls, f, None)
        meta["display_name"] = meta["display_name"] or key
        meta["category"] = meta["category"] or "未分类"
        meta["description"] = meta["description"] or ""
        meta["params"] = meta["params"] or {}
        out.append(meta)
    return sorted(out, key=lambda m: (m["category"], m["key"]))


def list_components() -> Dict[str, list]:
    return dict(algorithms=sorted(_ALGORITHMS), plants=sorted(_PLANTS))
