"""补判 ep10/ep20：护栏失明期间的追溯判决（部署修复后的一次性脚本）。"""
import sys

from src.evaluation.cover_quick_eval import judge

R10 = "outputs/results/decompose/eval_decompose_decompose_m1_ms31500_w4cover_full_20261118b_det_ep10.json"
R20 = "outputs/results/decompose/eval_decompose_decompose_m1_ms31500_w4cover_full_20261118b_det_ep20.json"

r10 = judge(R10)
print("ep10 pass=%s reason=%r metrics=%s" % (r10["pass"], r10["reason"], r10["metrics"]))
r20 = judge(R20, prev_peak_kN=r10["metrics"]["peak_kN"])
print("ep20 pass=%s reason=%r metrics=%s" % (r20["pass"], r20["reason"], r20["metrics"]))
