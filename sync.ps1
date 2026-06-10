# sync.ps1 — pull latest data from GitHub into local working copy
# Run this whenever players have made purchases or picks via the live app.
# Usage: .\sync.ps1

Set-Location $PSScriptRoot

Write-Host "`nPulling latest from GitHub..." -ForegroundColor Cyan
git fetch origin master

$behind = git rev-list HEAD..origin/master --count
if ($behind -eq "0") {
    Write-Host "Already up to date. No changes to pull." -ForegroundColor Green
} else {
    Write-Host "$behind new commit(s) on remote:" -ForegroundColor Yellow
    git log HEAD..origin/master --oneline
    Write-Host ""
    git pull origin master
    Write-Host "`nDone. Local copy is now up to date." -ForegroundColor Green
}

Write-Host ""
