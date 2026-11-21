#!/usr/bin/env bash
# 【§19.53】第 11 投开窗后的**第一个动作**：在**云端机**上跑策略前向的 ISA 路径探针，
# 按**前置写死**的判读规则给出跨机差异根因的判决。
#
# 【为什么这是开窗后的第一动作】
#   本机探针 C（诊断 §19.53）已测出：九档 ISA 派发中，**唯独 "MKL 强制 SSE4.2"**
#   改变了策略前向输出（差值恰为 float32 的 1 eps = 1 ULP），其余八档逐位相同
#   ⇒ 跨机差异的根因候选已从四条收窄到一条："**MKL 走哪条 ISA 路径**"。
#   而 §19.48 实测"策略输入 1 ULP 扰动 ⇒ 整程车钩峰值漂移 −14.9%"⇒ 两者量级严丝合缝。
#   ⚠️ **但这条链的最后一环尚未在真实跨机上验证** ⇒ 必须在云端机上跑一次同一探针对照，
#      才能把"跨机 17.7% 差异**可被** 1 ULP 解释"推进到"**根因定位到具体机制**"。
#
# 【用法】（在云端实例内执行）
#   bash scripts/probes/run_cloud_isa_probe.sh [ckpt] [out_json]
#   例：
#     bash scripts/probes/run_cloud_isa_probe.sh \
#       outputs/checkpoints/formation_10kt_1plus108/<第11投自己的run_tag>/mappo_fleet_last_ep1_dec_ad1_cp_seed0_seed0.pt
#   ⚠️ ckpt 缺省为第 9 投 W4 窗口的 ep6 ckpt（仅用于回溯本地基线口径）；
#      **第 11 投窗口必须传本投自己的 ckpt**。
#
# 【判读规则（前置写死，不得事后调整）】
#   下列 md5 在文档与日志中以 **16 位前缀缩写**出现（如 `dc324208b1387f4f`），
#   **脚本比对时一律用完整 32 位值**。
#   云端 default 档 md5 = 56bb457aab560bbc…（= 本机 SSE4.2 档）⇒ 云端 MKL 实际走 SSE4.2
#                                          ⇒ **根因定位到 "MKL ISA 派发"**
#   云端 default 档 md5 = dc324208b1387f4f…（= 本机默认 AVX2 档）⇒ 与本地逐位相同
#                                          ⇒ **ISA 不是根因**，候选须再向下收窄
#                                            （libm / 库版本 / 其它归约细节）
#                                            ⇒ **不得**回头宣称"已定位根因"
#   其它 md5                                 ⇒ 第三种情形（云端走了本机未覆盖的路径）
#                                          ⇒ 人工核查后再判，**不得**默认归因
#   另：云端 mkl_sse42 档 md5 若 ≠ 本机 56bb457aab560bbc… ⇒ **基准本身失效**
#      （本机基准是在本机 torch 构建下测的，云端可能整体不同）⇒ 判决作废，须重做本地基准。
#
# 【口径】
#   · **零新增训练、秒级**（每次前向 9 档子进程，各档一次前向）；
#   · **不产出任何峰值/安全判据**（只比策略前向输出的 md5）；
#   · 产物落在 outputs/logs/adr083_float_probe/ 下 ⇒ 不违反硬红线 4。
set -uo pipefail
source /home/chano/miniconda3/etc/profile.d/conda.sh
conda activate traffic_rl
cd /mnt/d/Code/MultiAgent/traffic_rl_project

CKPT="${1:-outputs/checkpoints/formation_10kt_1plus108/w4nincrgatecaprel_w4full_20261120_cloud/mappo_fleet_last_ep6_dec_ad1_cp_seed0_seed0.pt}"
OUT="${2:-outputs/logs/adr083_float_probe/torch_isa_path_probe_cloud.json}"

# ⚠️ 以下为**完整 32 位 md5**（文档/日志里出现的 16 位是**前缀缩写**，不是完整值）：
LOCAL_DEFAULT_MD5="dc324208b1387f4f576cbac6cfad2f5b"   # 本机默认（AVX2）档
LOCAL_SSE42_MD5="56bb457aab560bbc756bd7bacabae84e"    # 本机 MKL SSE4.2 档

if [ ! -f "${CKPT}" ]; then
  echo "[isa-cloud] ABORT: ckpt 不存在：${CKPT}"
  echo "[isa-cloud] ⚠️ 第 11 投窗口必须传入**本投自己的** ckpt，勿沿用第 9 投路径。"
  exit 2
fi

echo "[isa-cloud] ckpt=${CKPT}"
echo "[isa-cloud] out=${OUT}"
python scripts/probes/probe_torch_isa_path.py \
  --checkpoint "${CKPT}" --out "${OUT}" \
  > outputs/logs/adr083_float_probe/torch_isa_path_cloud.log 2>&1
RC=$?
echo "[isa-cloud] probe rc=${RC}"
if [ "${RC}" -ne 0 ]; then
  echo "[isa-cloud] ABORT: 探针失败，判决作废。"
  exit 2
fi

python - "$OUT" "${LOCAL_DEFAULT_MD5}" "${LOCAL_SSE42_MD5}" <<'PYEOF'
import json, sys
out, local_default, local_sse42 = sys.argv[1], sys.argv[2], sys.argv[3]
j = json.load(open(out, encoding="utf-8"))
res = j.get("results", {})
cloud_default = res.get("default", {}).get("md5")
cloud_sse42 = res.get("mkl_sse42", {}).get("md5")

print("[isa-cloud] 云端 default md5 =", cloud_default)
print("[isa-cloud] 云端 mkl_sse42 md5 =", cloud_sse42)
print("[isa-cloud] 本机 default md5 =", local_default)
print("[isa-cloud] 本机 sse42  md5 =", local_sse42)

verdict = None
if cloud_sse42 is not None and cloud_sse42 != local_sse42:
    verdict = ("BASELINE_INVALID",
               "云端 mkl_sse42 档 md5 与本机基准不同 ⇒ 本机基准在云端整体失效 "
               "⇒ 本次判决作废，须在云端重新建立基准后再判。")
elif cloud_default == local_sse42:
    verdict = ("ROOT_CAUSE_ISOLATED",
               "云端默认档与本机 'MKL SSE4.2' 档逐位相同 ⇒ 云端 MKL 实际走 SSE4.2 路径 "
               "⇒ 跨机 17.7% 差异的根因定位到 'MKL ISA 派发'（机制层闭合）。")
elif cloud_default == local_default:
    verdict = ("ISA_NOT_ROOT_CAUSE",
               "云端默认档与本机默认档逐位相同 ⇒ ISA 派发不是根因 ⇒ 候选须再向下收窄 "
               "（libm / 库版本 / 其它归约细节）⇒ 不得回头宣称已定位根因。")
else:
    verdict = ("THIRD_PATH",
               "云端 default md5 既不等于本机默认档也不等于本机 SSE4.2 档 ⇒ "
               "云端走了本机未覆盖的第三条路径 ⇒ 人工核查后再判，不得默认归因。")

code, text = verdict
print("[isa-cloud] VERDICT =", code)
print("[isa-cloud] ", text)
j["cloud_verdict"] = {"code": code, "text": text,
                       "cloud_default_md5": cloud_default,
                       "cloud_mkl_sse42_md5": cloud_sse42,
                       "local_default_md5": local_default,
                       "local_mkl_sse42_md5": local_sse42}
json.dump(j, open(out, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
print("[isa-cloud] 判决已写入", out)
PYEOF

echo "[isa-cloud] ALL_DONE $(date -Is)"
