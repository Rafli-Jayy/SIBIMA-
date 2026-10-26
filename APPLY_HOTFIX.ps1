param(
    [Parameter(Mandatory = $true)]
    [string]$ProjectRoot
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = [System.IO.Path]::GetFullPath($ProjectRoot)
$PatchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$source = Join-Path $PatchRoot 'files\app\repositories\student_repo.py'
$target = Join-Path $ProjectRoot 'app\repositories\student_repo.py'

if (-not (Test-Path -LiteralPath $ProjectRoot -PathType Container)) { throw "Folder proyek tidak ditemukan: $ProjectRoot" }
if (-not (Test-Path -LiteralPath (Join-Path $ProjectRoot 'app\main.py') -PathType Leaf)) { throw 'Folder target bukan root proyek SIBIMA: app\main.py tidak ditemukan.' }
if (-not (Test-Path -LiteralPath $source -PathType Leaf)) { throw 'File patch student_repo.py tidak ditemukan.' }
if (-not (Test-Path -LiteralPath $target -PathType Leaf)) { throw 'File target app\repositories\student_repo.py tidak ditemukan.' }

$stamp = Get-Date -Format 'yyyyMMdd_HHmmss'
$parent = Split-Path -Parent $ProjectRoot
$backupRoot = Join-Path $parent ("SIBIMA_backup_fix_jadwal_siswa_" + $stamp)
New-Item -ItemType Directory -Path (Split-Path -Parent (Join-Path $backupRoot 'app\repositories\student_repo.py')) -Force | Out-Null
Copy-Item -LiteralPath $target -Destination (Join-Path $backupRoot 'app\repositories\student_repo.py') -Force

Write-Host ''
Write-Host 'SIBIMA — Hotfix InvalidColumnReference pada Jadwal Saya' -ForegroundColor Cyan
Write-Host "Target : $target"
Write-Host "Backup : $backupRoot"
Write-Host 'Perubahan: memperbaiki query jadwal dan menghindari duplikasi melalui EXISTS.' -ForegroundColor Yellow
$confirm = Read-Host 'Lanjutkan pemasangan? (Y/N)'
if ($confirm -notin @('Y', 'y', 'YES', 'yes')) {
    Write-Host 'Dibatalkan. File target tidak diubah.' -ForegroundColor Yellow
    exit 0
}
Copy-Item -LiteralPath $source -Destination $target -Force
Write-Host 'OK  app\repositories\student_repo.py' -ForegroundColor Green
Write-Host 'Selesai. Tidak ada migrasi SQL yang dijalankan.' -ForegroundColor Green
Write-Host "Backup: $backupRoot"
