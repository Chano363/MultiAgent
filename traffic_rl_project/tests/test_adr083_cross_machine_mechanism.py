"""§19.43 永久守卫：跨机器差异的机制层追查结论不得被静默推翻。

钉住四类事实：
  1. 代码同源的三重旁证（`.preflight_ok` 的 commit + 祖先核验 + `src/` 路径 diff）；
  2. 浮点层排除：线程序（torch 线程 1/2/4/8/16/默认）与 JIT 目标 ISA
     （generic/skylake/icelake/sapphirerapids/默认）均**位级唯一**；
  3. 放大系数探针的产物契约（字段齐全、基线档存在、不得缺整程结果）；
  4. 文档纪律：§19.43 已排除项不得在规则/诊断里被改写成"未定位"或反过来
     写成"已定位到某一项"。

⚠️ 本守卫**不重跑整程仿真**（那是 2–3 h 的长跑，属计划任务范畴）：
它复核**已落盘的探针产物**与**文档表述**。
"""
from __future__ import annotations

import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DIAG = ROOT / "docs/logs/diagnostics/DIAGNOSTICS_2026-11.md"
RULES = ROOT / "docs/rules/EXECUTION_RULES.md"
AGENTS = ROOT.parent / "AGENTS.md"
PROBE_DIR = ROOT / "outputs/logs/adr083_float_probe"


def _read(p: Path) -> str:
    return p.read_text(encoding="utf-8")


def test_preflight_ok_carries_real_cloud_commit():
    """.preflight_ok 是"实际上云 commit"的权威标记（W4 窗口）。"""
    f = ROOT / ".preflight_ok"
    assert f.is_file(), ".preflight_ok 缺失：无法核验实际上云的代码版本"
    txt = _read(f)
    assert "commit=" in txt, ".preflight_ok 缺 commit= 字段"
    assert "preflight_ok_at=" in txt, ".preflight_ok 缺 preflight_ok_at= 字段"
    m = re.search(r"commit=([0-9a-f]{7,40})", txt)
    assert m, ".preflight_ok 的 commit= 不是合法 sha"
    sha = m.group(1)
    # 【2026-11-21 更新】窗口已从 W4 推进到第 11 投 ⇒ 配置名断言改为**族名 + 文件真实存在**
    #   （原断言硬编码 "nincrgatecaprel.yaml"，对第 11 投的 "_colgap.yaml" 会误报）
    assert "nincrgatecaprel" in txt, ".preflight_ok 未记录本投配置族名"
    m_cfg = re.search(r"config=(\S+)", txt)
    assert m_cfg, ".preflight_ok 缺 config= 字段"
    assert (ROOT / m_cfg.group(1)).is_file(), (
        f".preflight_ok 记录的配置文件不存在：{m_cfg.group(1)}"
    )


def test_w4_cloud_commit_is_ancestor_of_all_physics_commits():
    """云端真实 commit 必须是 ADR-076/077/080/081 物理改动的后代。

    云端真实 commit = `.preflight_ok` 的 commit（§19.43 (1)）。
    """
    import subprocess

    f = ROOT / ".preflight_ok"
    sha = re.search(r"commit=([0-9a-f]{7,40})", _read(f)).group(1)
    # ADR-076 AB 坡度物理判据 / ADR-077 AB 三键修复 / ADR-080+081 / ADR-081 v_rel 修正
    for c in ("4a96d40", "fb005d9", "dcbe214", "fef27a3", "b14e2bd"):
        rc = subprocess.run(["git", "merge-base", "--is-ancestor", c, sha],
                            cwd=str(ROOT), capture_output=True)
        assert rc.returncode == 0, (
            f"{c} 不是云端真实 commit {sha} 的祖先 ⇒ 云端代码不含该物理改动，"
            f"§19.43 的代码同源实证失效")


# 【§19.43 落账时的本地 HEAD】—— 代码同源实证所核验的**那个**本地代码状态。
# ⚠️ 守卫锁定的是**快照事实**（"在 §19.43 落账时，本地数值路径与云端相同"），
#    **不是**"从今往后 HEAD 永远等于云端代码"——后者会把守卫变成"禁止任何
#    src/ 改动"的假约束，从而阻断后续一切正当开发（如第 11 投候选的
#    训练期逐列落盘）。若日后确需复核"当前 HEAD 与云端是否仍同源"，
#    应重跑 §19.43 的核验并更新本常量 + 诊断文档，而不是让守卫持续漂移。
LOCAL_HEAD_AT_1943 = "de7fdcd"


def test_cloud_commit_to_local_head_at_1943_diff_is_provenance_only():
    """云端真实 commit → §19.43 落账时本地 HEAD 的 src/ configs/ 差异只能是 provenance。"""
    import subprocess

    f = ROOT / ".preflight_ok"
    sha = re.search(r"commit=([0-9a-f]{7,40})", _read(f)).group(1)
    out = subprocess.run(["git", "diff", "--stat", sha, LOCAL_HEAD_AT_1943,
                          "--", "src/", "configs/"],
                         cwd=str(ROOT), capture_output=True, text=True).stdout
    changed = [ln.split("|")[0].strip() for ln in out.splitlines()
               if "|" in ln and ln.strip()]
    # git 输出的路径带仓库前缀（traffic_rl_project/…），归一到 src/… 后比对
    normalized = [c.split("traffic_rl_project/", 1)[-1] if "traffic_rl_project/" in c else c
                  for c in changed]
    # 允许出现差异的文件（纯 provenance）
    allowed = {"src/metadata.py"}
    # 【2026-11-21 更新】§19.66 的干预面③ 实现**主动改了数值路径**
    #   （train_fleet_env.py：gap_eff_scale_m 可配置）⇒ 云端代码与 §19.43 快照**不再同源**
    #   ⇒ 原断言（差异只允许 provenance）对**后续窗口**理应失效。
    #   ⇒ 双模式：① 若云端 commit 仍 == §19.43 快照 ⇒ 保持原严格断言；
    #             ② 否则 ⇒ 差异必须**恰好**落在"已登记的后续数值变更清单"内，
    #               且 §19.43 快照必须仍是云端 commit 的**祖先**（历史连续性未被破坏）。
    # 【2026-11-21 更新，重要】§19.43 的"云端代码 == 当时本地 HEAD（同源）"是**一次性历史事实**：
    #   它的证据是**当时的探针产物与当时的 diff**，而不是"今天的 diff"。
    #   云端 commit 会随窗口前进（第 11 投窗口 = c9cad36…）⇒ 今天的 diff **必然**包含
    #   第 7–9 投与第 11 投的全部代码变更 ⇒ 在后续窗口里做"与 §19.43 快照逐文件比对"
    #   是**口径错误**（会把正常的迭代当成"同源失效"）。
    #   ⇒ 改法：**只在云端 commit 仍等于 §19.43 快照时**做严格 diff；
    #     否则（本分支）只校验**历史连续性**：§19.43 快照仍在 git 历史里、且仍是云端 commit 的祖先。
    #     "每次窗口的同源"由 `test_preflight_ok_carries_real_cloud_commit` 负责
    #     （`.preflight_ok` 记录实际上云的 commit，且必须存在）。
    if sha.startswith(LOCAL_HEAD_AT_1943) or LOCAL_HEAD_AT_1943.startswith(sha):
        bad = [c for c in normalized if c not in allowed]
        assert not bad, (f"云端 commit {sha} 与 §19.43 快照在数值路径上存在差异：{bad}"
                         "（§19.43 的代码同源实证失效）")
    else:
        rc = subprocess.run(["git", "cat-file", "-e", f"{LOCAL_HEAD_AT_1943}^{{commit}}"],
                            cwd=str(ROOT), capture_output=True)
        assert rc.returncode == 0, f"{LOCAL_HEAD_AT_1943} 不在 git 历史里"
        rc2 = subprocess.run(["git", "merge-base", "--is-ancestor",
                              LOCAL_HEAD_AT_1943, sha],
                             cwd=str(ROOT), capture_output=True)
        assert rc2.returncode == 0, (
            f"§19.43 快照 {LOCAL_HEAD_AT_1943} 不在云端 commit {sha} 的祖先链上"
            " ⇒ 历史连续性断裂")


def test_1943_snapshot_commit_is_reachable_and_ancestry_holds():
    """§19.43 落账时的本地 HEAD 必须在历史里，且仍是云端 commit 的后代。"""
    import subprocess

    rc = subprocess.run(["git", "cat-file", "-e", f"{LOCAL_HEAD_AT_1943}^{{commit}}"],
                        cwd=str(ROOT), capture_output=True)
    assert rc.returncode == 0, f"{LOCAL_HEAD_AT_1943} 不在 git 历史里"
    f = ROOT / ".preflight_ok"
    sha = re.search(r"commit=([0-9a-f]{7,40})", _read(f)).group(1)
    # 【2026-11-21 更新】云端 commit 随窗口前进（现在是第 11 投的 commit）⇒
    #   "云端 commit 是 §19.43 快照的祖先"这一方向在**后续窗口**里不再成立
    #   （快照更早 ⇒ 它是云端 commit 的祖先）。双模式：
    #   ① 快照 == 云端 commit ⇒ 原断言（祖先关系，平凡成立）；
    #   ② 否则 ⇒ 断言**云端 commit 是快照的后代**（历史连续、快照仍是祖先链上一环）。
    rc = subprocess.run(["git", "merge-base", "--is-ancestor", sha, LOCAL_HEAD_AT_1943],
                        cwd=str(ROOT), capture_output=True)
    if rc.returncode == 0:
        return
    rc2 = subprocess.run(["git", "merge-base", "--is-ancestor", LOCAL_HEAD_AT_1943, sha],
                         cwd=str(ROOT), capture_output=True)
    assert rc2.returncode == 0, (
        f"云端 commit {sha} 与 §19.43 快照 {LOCAL_HEAD_AT_1943} **互不为祖先**"
        "⇒ 历史连续性断裂（快照已不在云端 commit 的祖先链上）")


def test_thread_order_probe_shows_bit_identical_across_threads():
    """线程序不是放大层：策略前向在 1/2/4/8/16/默认线程下 md5 唯一。"""
    f = PROBE_DIR / "thread_order_probe.json"
    assert f.is_file(), "thread_order_probe.json 缺失：§19.43 (2) 的排除性证据丢失"
    d = json.loads(_read(f))
    assert d.get("across_threads_bit_identical") is True, (
        "探针结论变了：跨线程前向不再位级唯一 ⇒ 线程序重回候选层，§19.43 (2) 需重做")
    assert d.get("n_unique_action_hashes") == 1, d.get("n_unique_action_hashes")
    assert len(d.get("threads_tried", [])) >= 5, d.get("threads_tried")
    for k, v in d.get("within_thread_stable", {}).items():
        assert v is True, f"{k} 线程内重复不稳定：{k}"


def test_numba_isa_probe_shows_bit_identical_across_isa_targets():
    """JIT 目标 ISA 不是放大层：车钩力内核跨 ISA 输出 md5 唯一。"""
    f = PROBE_DIR / "numba_isa_probe.json"
    assert f.is_file(), "numba_isa_probe.json 缺失：§19.43 (3) 的排除性证据丢失"
    d = json.loads(_read(f))
    assert d.get("across_isa_bit_identical") is True, (
        "探针结论变了：跨 ISA 内核输出不再位级唯一 ⇒ ISA 重回候选层，§19.43 (3) 需重做")
    assert d.get("n_unique_md5") == 1, d.get("n_unique_md5")
    ok_targets = set(d.get("targets_ok", []))
    for t in ("generic", "skylake", "icelake", "sapphirerapids"):
        assert t in ok_targets, f"ISA 目标 {t} 未成功执行，排除性证据不完整"


def test_amplification_probe_artifact_contract():
    """放大系数产物契约：字段齐全、基线档存在、每档带相对漂移。"""
    f = PROBE_DIR / "amplification_probe.json"
    if not f.is_file():
        # 整程探针仍在跑（计划任务 MultiAgent_ADR083_amp）⇒ 允许暂缺，
        # 但不得让"缺产物"被当成"结论已成立"。
        return
    d = json.loads(_read(f))
    assert "baseline_peak_kN" in d, "放大系数产物缺 baseline_peak_kN"
    rs = d.get("results", [])
    assert len(rs) >= 2, f"放大系数档位不足（{len(rs)} 档），无法给敏感度曲线"
    ulps = [r["ulps"] for r in rs]
    assert 0 in ulps, "放大系数产物缺 0 ULP 基线档"
    for r in rs:
        for k in ("peak_coupler_kN", "rel_delta_peak_vs_base_pct", "steps"):
            assert k in r, f"放大系数档位缺字段 {k}"
    # ⚠️ 2026-11-21 修正（守卫误报 ⇒ 口径澄清）：
    #   `max_steps` 是**步数上限**，不是"整程步数"。本线路（49.6 km，起点 4300 m，
    #   init 60 km/h）在 **24953 步自然终止**（term/trunc ⇒ 跑完线路终点），
    #   31500 步只是不会触顶的上限 ⇒ **"整程"= 走完全程线路，不是"跑满 31500 步"**。
    #   原断言 `steps == max_steps` 把整程误判为短窗 ⇒ 误报（首现于四档产物落盘时）。
    #   正确的整程判据 = **各档步数彼此一致（同一线路终点）**，而不是等于上限。
    steps = [r["steps"] for r in rs]
    lo, hi = min(steps), max(steps)
    assert hi > 0
    assert (hi - lo) / hi < 0.02, (
        f"各档步数不一致（{lo}~{hi}）⇒ 不是同一整程口径 ⇒ 曲线不可比"
    )
    assert lo >= 20000, (
        f"各档步数（{lo}~{hi}）远低于本线路的整程量级（≈2.5 万步）"
        "⇒ 疑似短窗（红线 3：短窗不作判据）"
    )


def test_diagnostics_records_1943_and_keeps_exclusions():
    """§19.43 必须在诊断文档里，且已排除项不得被改写成别的说法。"""
    txt = _read(DIAG)
    assert "§19.43" in txt, "诊断文档缺 §19.43"
    for kw in ("probe_float_order.py", "probe_numba_isa.py", "probe_amplification.py",
               "1bb7b02", "三重旁证"):
        assert kw in txt, f"§19.43 缺关键内容：{kw}"
    # 不得把已排除项又写成"已定位"
    assert "线程序 / BLAS 线程归约顺序 —— 不是放大层" in txt
    assert "JIT 目标 ISA（AVX2 vs AVX512）—— 不是放大层" in txt


def test_rules_and_agents_keep_exclusion_and_no_assumption():
    """规则正文与 AGENTS.md 必须保留"已排除两项"+"不得当假设写进结论"。"""
    rules = _read(RULES)
    assert "均被实测排除" in rules, "规则正文未记录已排除的浮点候选层"
    assert "三重旁证" in rules, "规则正文缺代码同源三重旁证法"
    assert "放大系数实测回答" in rules, "规则正文缺『放大系数须实测』的纪律"
    ag = _read(AGENTS)
    assert "已排除两项" in ag, "AGENTS.md 未同步 §19.43 的排除结论"
    assert "不得当假设写进结论" in ag, "AGENTS.md 缺『不得把假设当结论』的纪律"
