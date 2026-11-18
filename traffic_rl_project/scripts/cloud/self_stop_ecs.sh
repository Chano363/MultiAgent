#!/usr/bin/env bash
# 实例内自停机（服务器端 closer 的最后一块）：实例自己调 StopInstance 完成"停费"，
# 不再依赖本地 Windows schtasks 在线。一手依据见 docs/CLOSER_SERVER_SIDE_ASSESSMENT.md：
#   - ECS 实例 RAM 角色经 IMDS 取 STS 临时凭证，无需 AK（help.aliyun.com/zh/ecs/user-guide/attach-an-instance-ram-role）
#   - aliyun CLI >=3.3.0 的 EcsRamRole 凭证模式（help.aliyun.com/zh/cli/ecs-ram-role）
#   - StopInstance --StoppedMode StopCharging = 省钱停机（vCPU/内存/静态IP 停计费）
#
# 前置（一次性，控制台操作，需 owner 批）：
#   1. 建 RAM 角色（信任 ECS 服务），授权 ecs:StopInstance + ecs:DescribeInstances（最小权限）
#   2. 把角色绑到目标实例；实例设为按量付费
#   3. 实例内装 aliyun CLI >=3.3.0：aliyun configure --mode EcsRamRole --profile ecs-self
#   —— 本脚本不执行任何云端变更（不建角色/不绑角色/不开机），只调用已授权的停止动作。
#
# 用法： bash self_stop_ecs.sh [reason]
#   reason  停机原因（写日志，如 DEAD_HEARTBEAT / train_exit / DEADLINE）
# 退出码：0=已确认 Stopped+StopCharging；1=调用/复核失败（调用方须回退 OS poweroff）；
#         2=前置缺失（CLI/角色/region 任一不可用）
set -uo pipefail

REASON="${1:-unspecified}"
IMDS="${SELF_STOP_IMDS:-http://100.100.100.200/latest/meta-data}"  # 可覆盖（单测用 mock）
PROFILE="${ALIYUN_PROFILE:-ecs-self}"
SELF_LOG="${SELF_STOP_LOG:-/root/traffic_rl_project/outputs/logs/cloud/self_stop.log}"
# 复核重试（StopInstance 异步，状态落地有延迟）
VERIFY_RETRIES="${SELF_STOP_VERIFY_RETRIES:-12}"
VERIFY_SLEEP="${SELF_STOP_VERIFY_SLEEP:-10}"

log() { mkdir -p "$(dirname "$SELF_LOG")"; echo "$(date -Is) [self_stop] $*" | tee -a "$SELF_LOG" 2>/dev/null; }

# 1) 前置：aliyun CLI + EcsRamRole 凭证 profile
if ! command -v aliyun >/dev/null 2>&1; then
  log "FAIL CLI_MISSING reason=$REASON（需 aliyun CLI>=3.3.0）"
  exit 2
fi
# 2) 从实例元数据读 instance-id 与 region（不硬编码、不依赖本地传参）
IID=$(curl -fsS --max-time 5 "$IMDS/instance-id" 2>/dev/null | tr -d '\r\n')
RID=$(curl -fsS --max-time 5 "$IMDS/region-id" 2>/dev/null | tr -d '\r\n')
if [ -z "$IID" ] || [ -z "$RID" ]; then
  log "FAIL IMDS_UNAVAILABLE reason=$REASON iid=${IID:-?} rid=${RID:-?}"
  exit 2
fi
log "BEGIN reason=$REASON instance=$IID region=$RID profile=$PROFILE"

# 3) 调 API 停自己（StopCharging 省钱停机；--ForceStop false 给进程优雅退出窗口）
if ! aliyun ecs StopInstance \
    --RegionId "$RID" --InstanceId "$IID" \
    --StoppedMode StopCharging --ForceStop false \
    --profile "$PROFILE" >>"$SELF_LOG" 2>&1; then
  log "FAIL STOP_API_ERROR reason=$REASON（检查 RAM 角色权限/STS 凭证/profile 名）"
  exit 1
fi
log "STOP_API_ACCEPTED instance=$IID"

# 4) 二次复核：必须见到 Status=Stopped 且 StoppedMode=StopCharging（对齐硬红线：贴回执）
for i in $(seq 1 "$VERIFY_RETRIES"); do
  DESC=$(aliyun ecs DescribeInstances --RegionId "$RID" \
         --InstanceIds "[\"$IID\"]" --profile "$PROFILE" 2>/dev/null)
  ST=$(echo "$DESC" | grep -o '"Status"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | grep -o '"[^"]*"$' | tr -d '"')
  SM=$(echo "$DESC" | grep -o '"StoppedMode"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | grep -o '"[^"]*"$' | tr -d '"')
  if [ "$ST" = "Stopped" ] && [ "$SM" = "StopCharging" ]; then
    log "VERIFIED Status=$ST StoppedMode=$SM reason=$REASON（实例自停机完成，已停费）"
    exit 0
  fi
  sleep "$VERIFY_SLEEP"
done
log "FAIL VERIFY_TIMEOUT last_status=${ST:-?} last_mode=${SM:-?} reason=$REASON（调用方须回退 OS poweroff）"
exit 1
