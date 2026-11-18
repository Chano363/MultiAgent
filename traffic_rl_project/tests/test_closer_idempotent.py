"""双活 closer 的幂等停机单测（2026-11-18 owner 放开权限后做本地冗余）。

mock 掉 aliyun SDK（函数内 import），验证：
  1. 实例已 Stopped+StopCharging：不再调 StopInstance，直接成功（双活 loser 干净退出）
  2. 实例 Running：走 StopInstance + 复核，成功后返回 True
  3. 复核拿到 Stopped 但非 StopCharging：返回 False（"没停费绝不收工"）
"""
import importlib.util
import os
import sys
import types
from unittest.mock import patch

HERE = os.path.dirname(os.path.abspath(__file__))
SCRIPTS = os.path.join(os.path.dirname(HERE), "scripts", "cloud")
sys.path.insert(0, SCRIPTS)
spec = importlib.util.spec_from_file_location(
    "closer_idem", os.path.join(SCRIPTS, "closer_aliyun_ecs.py"))
closer = importlib.util.module_from_spec(spec)
spec.loader.exec_module(closer)


class FakeReq:
    def __init__(self): self.params = {}; self.action = ""
    def set_accept_format(self, x): pass
    def set_protocol_type(self, x): pass
    def set_domain(self, x): pass
    def set_version(self, x): pass
    def set_action_name(self, x): self.action = x
    def set_method(self, x): pass
    def add_query_param(self, k, v): self.params[k] = v


def fake_sdk(statuses):
    """statuses: list of (Status, StoppedMode) 按 DescribeInstances 调用顺序。"""
    calls = []
    seq = list(statuses)

    class FakeClient:
        def __init__(self, *a, **kw): pass
        def do_action_with_exception(self, req):
            calls.append(req.action)
            if req.action == "DescribeInstances":
                st, sm = seq.pop(0) if seq else ("Stopped", "StopCharging")
                return __import__("json").dumps(
                    {"Instances": {"Instance": [{"Status": st, "StoppedMode": sm}]}}).encode()
            return b"{}"

    core = types.ModuleType("aliyunsdkcore")
    client_mod = types.ModuleType("aliyunsdkcore.client")
    request_mod = types.ModuleType("aliyunsdkcore.request")
    client_mod.AcsClient = FakeClient
    request_mod.CommonRequest = FakeReq
    core.client = client_mod
    core.request = request_mod
    return {"aliyunsdkcore": core, "aliyunsdkcore.client": client_mod,
            "aliyunsdkcore.request": request_mod}, calls


def test_already_stopped_is_idempotent_success():
    mods, calls = fake_sdk([("Stopped", "StopCharging")])
    with patch.dict(sys.modules, mods), patch.object(closer, "log"):
        assert closer.stop_instance("cn-heyuan", "i-test") is True
    assert "StopInstance" not in calls, "双活 loser 不应重复发停机 API"


def test_running_instance_stop_and_verify():
    mods, calls = fake_sdk([("Running", "Not-applicable"), ("Stopped", "StopCharging")])
    with patch.dict(sys.modules, mods), patch.object(closer, "log"):
        assert closer.stop_instance("cn-heyuan", "i-test") is True
    assert "StopInstance" in calls


def test_stopped_but_not_charging_is_failure():
    mods, calls = fake_sdk([("Stopped", "Not-applicable")])
    with patch.dict(sys.modules, mods), patch.object(closer, "log"):
        assert closer.stop_instance("cn-heyuan", "i-test") is False
    assert "StopInstance" not in calls


def test_closer_source_has_closeout_marker_and_retry():
    """静态守卫：wrapper 靠 CLOSEOUT_OK 判断真收账；源码不得丢掉该标记或重试逻辑。"""
    src = open(os.path.join(SCRIPTS, "closer_aliyun_ecs.py"), encoding="utf-8").read()
    assert "CLOSEOUT_OK" in src
    assert "停在未确认" not in src  # 不是反向断言，防止有人加错语义词
    assert "停机未确认" in src
