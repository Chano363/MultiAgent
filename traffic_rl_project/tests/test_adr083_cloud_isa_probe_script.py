"""守卫：云端 ISA 探针脚本（诊断 §19.53）的判读规则必须前置写死且用完整 32 位 md5。

背景：本机探针 C 测出"唯独 MKL SSE4.2 改变前向（差 1 eps）"，跨机差异的根因候选收窄到
"MKL ISA 派发"；闭合动作 = 在云端机上跑同一探针 ⇒ 必须有一条**判读规则前置写死**的
脚本，否则云端结果出来后会临时解释。
"""
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SH = ROOT / "scripts" / "probes" / "run_cloud_isa_probe.sh"
PROBE_JSON = ROOT / "outputs" / "logs" / "adr083_float_probe" / "torch_isa_path_probe.json"


def _text(p):
    return p.read_text(encoding="utf-8")


def test_script_exists_and_bash_syntax_ok():
    t = _text(SH)
    assert t.startswith("#!/usr/bin/env bash")
    assert "probe_torch_isa_path.py" in t


def test_all_four_verdict_exits_present():
    t = _text(SH)
    for code in ("ROOT_CAUSE_ISOLATED", "ISA_NOT_ROOT_CAUSE", "BASELINE_INVALID", "THIRD_PATH"):
        assert code in t, f"判读出口缺失：{code}"


def test_md5_constants_are_full_32_hex():
    t = _text(SH)
    consts = dict(re.findall(r'^(LOCAL_\w+_MD5)="([0-9a-f]+)"', t, flags=re.M))
    assert len(consts) == 2, f"应有两条 md5 常量，实际 {consts}"
    for name, val in consts.items():
        assert len(val) == 32, f"{name} 必须是完整 32 位 md5，实际 {val}（{len(val)} 位）"


def test_md5_constants_match_local_probe_artifact():
    if not PROBE_JSON.exists():
        return
    import json
    j = json.loads(_text(PROBE_JSON))
    res = j["results"]
    t = _text(SH)
    assert res["default"]["md5"] in t, "默认档 md5 与本机产物不一致"
    assert res["mkl_sse42"]["md5"] in t, "SSE4.2 档 md5 与本机产物不一致"


def test_no_short_prefix_used_for_comparison():
    """禁止用 16 位前缀做比较（初版即此错，会被判成 BASELINE_INVALID）。"""
    t = _text(SH)
    # 去掉注释行后再检查比较用的常量
    code_lines = [ln for ln in t.splitlines() if not ln.strip().startswith("#")]
    code = "\n".join(code_lines)
    for m in re.finditer(r'LOCAL_\w+_MD5\s*=\s*"([0-9a-f]+)"', code):
        assert len(m.group(1)) == 32, f"比较用 md5 必须是 32 位：{m.group(1)}"


def test_script_does_not_touch_cloud_api():
    t = _text(SH)
    for bad in ("aliyun", "ecs.c9i", "InstanceId", "DescribeInstances"):
        assert bad not in t, f"云端 ISA 脚本出现云 API 痕迹：{bad}"
