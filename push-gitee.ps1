# =============================================================
# push-gitee.ps1 — 一键提交并推送到 gitee（当前分支）
# 用法：
#   .\push-gitee.ps1 -Message "提交说明"   # 有变更：提交 + 推送
#   .\push-gitee.ps1                       # 无变更只推送；有变更但未给说明时用默认说明
# =============================================================

param(
    [string]$Message = ""
)

$ErrorActionPreference = "Stop"

# 1. 定位 git（PATH 里没有时用固定安装路径）
$git = (Get-Command git.exe -ErrorAction SilentlyContinue).Source
if (-not $git) { $git = "D:\Git\cmd\git.exe" }
if (-not (Test-Path $git)) { Write-Host "[错误] 找不到 git.exe" -ForegroundColor Red; exit 1 }

# 2. 切到仓库根目录（脚本所在目录）
Set-Location $PSScriptRoot
$branch = & $git branch --show-current
Write-Host "仓库：$PSScriptRoot  分支：$branch"

# 3. 有未跟踪/已修改变更 -> 提交
$dirty = & $git status --porcelain
if ($dirty) {
    if (-not $Message) {
        $stamp = Get-Date -Format "yyyy-MM-dd HH:mm"
        $Message = "update: $stamp"
        Write-Host "[提示] 未提供提交说明，使用默认：$Message" -ForegroundColor Yellow
    }
    & $git add -A
    & $git commit -m $Message
    if ($LASTEXITCODE -ne 0) { Write-Host "[错误] 提交失败" -ForegroundColor Red; exit 1 }
    Write-Host "[OK] 已提交：$Message" -ForegroundColor Green
} else {
    Write-Host "无本地变更，跳过提交"
}

# 4. 比较本地与 gitee，需要推送才推
$local  = & $git rev-parse HEAD
$remote = & $git rev-parse "gitee/$branch" 2>$null
if ($local -eq $remote) {
    Write-Host "已是最新，无需推送" -ForegroundColor Green
    exit 0
}

& $git push gitee $branch
if ($LASTEXITCODE -eq 0) {
    Write-Host "[OK] 已推送到 gitee/$branch" -ForegroundColor Green
} else {
    Write-Host "[错误] 推送失败（检查 SSH key / 网络）" -ForegroundColor Red
    exit 1
}
