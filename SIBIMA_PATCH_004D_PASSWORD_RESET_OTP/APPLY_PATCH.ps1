$ErrorActionPreference = 'Stop'
$patchRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$projectRoot = (Get-Location).Path
$filesRoot = Join-Path $patchRoot 'files'
$changed = @(
    @{ Rel = 'app\services\auth_service.py'; Base = 'AF37061E23EFFD274A89590BD87FBB58817478658F0D4E0D6E6E395A1A25E179'; Patched = '99CF12799EEAB986FFE0CDC1F3D654552FC276F85ECD60A6A5B0FA83A7469AE1' }
    @{ Rel = 'app\services\otp_service.py'; Base = '5417D5208206C9EBBD2566F5904C11C5370330776779BF61F9E5C6AD6B1B9A06'; Patched = '760F5410A9264CECA1C7832F8F6EBAD24EAE0804C6DAF94F8C4826778C43437B' }
    @{ Rel = 'app\repositories\otp_repo.py'; Base = '6A63CB2BCE1A3214DF6DE019FC3194DC6221DE630F46A5578DC13EB76D796F12'; Patched = 'E6F62AD1536AD3B403E04033E83525B78472BA5ECD316E6C5DA4A6397212637E' }
    @{ Rel = 'app\services\email_service.py'; Base = 'C5C02B453515ADA2839BBEB338B1E66C00C3258371A6BADEE1F19B748B5062A2'; Patched = 'AF2CF794888EC613B8501BEA8896A52E1EA7186B2093975CA2A918AC1F8060B0' }
    @{ Rel = 'app\ui\menu_auth.py'; Base = 'E6EE730D58150799025D98B1AB977612D46CF9293E93C159EB1EDCD29324240C'; Patched = '191B421572ADA1A084566E16E7AB756400AF5B9C85E89C2632B6C0C7748F8A2E' }
)
$added = @(
    @{ Rel = 'tests\test_password_reset_otp.py'; Patched = '57D57F4AFDC55FE445D5788B333643DB1023B0A83E961788CA9977807209DA45' }
)

foreach ($rel in @('app', 'tests', 'requirements.txt')) {
    if (-not (Test-Path -LiteralPath (Join-Path $projectRoot $rel))) {
        throw 'Jalankan installer di folder utama SIBIMA, yang berisi app, tests, dan requirements.txt.'
    }
}

# Preflight: seluruh file diperiksa terlebih dahulu; tidak ada penimpaan diam-diam.
$numberAlreadyPatched = 0
$numberAtBase = 0
foreach ($item in $changed) {
    $item.Src = Join-Path $filesRoot $item.Rel
    $item.Dst = Join-Path $projectRoot $item.Rel
    if (-not (Test-Path -LiteralPath $item.Src -PathType Leaf) -or
        -not (Test-Path -LiteralPath $item.Dst -PathType Leaf)) {
        throw "File tidak ditemukan: $($item.Rel)"
    }
    if ((Get-FileHash -LiteralPath $item.Src -Algorithm SHA256).Hash -ne $item.Patched) {
        throw "File patch diubah/rusak: $($item.Rel)"
    }
    $hash = (Get-FileHash -LiteralPath $item.Dst -Algorithm SHA256).Hash
    if ($hash -eq $item.Base) {
        $numberAtBase += 1
    } elseif ($hash -eq $item.Patched) {
        $numberAlreadyPatched += 1
    } else {
        throw "Versi file proyek berbeda: $($item.Rel). Tidak ada file yang ditimpa."
    }
}
$alreadyAdded = 0
foreach ($item in $added) {
    $item.Src = Join-Path $filesRoot $item.Rel
    $item.Dst = Join-Path $projectRoot $item.Rel
    if (-not (Test-Path -LiteralPath $item.Src -PathType Leaf) -or
        (Get-FileHash -LiteralPath $item.Src -Algorithm SHA256).Hash -ne $item.Patched) {
        throw "Berkas tambahan tidak cocok: $($item.Rel)"
    }
    if (Test-Path -LiteralPath $item.Dst -PathType Leaf) {
        if ((Get-FileHash -LiteralPath $item.Dst -Algorithm SHA256).Hash -ne $item.Patched) {
            throw "File tujuan sudah ada dan berbeda: $($item.Rel). Tidak akan ditimpa."
        }
        $alreadyAdded += 1
    }
}
if ($numberAlreadyPatched -eq $changed.Count -and $alreadyAdded -eq $added.Count) {
    Write-Host 'PATCH-004D sudah terpasang. Tidak ada perubahan.' -ForegroundColor Cyan
    return
}
if ($numberAtBase -ne $changed.Count -or $alreadyAdded -gt 0) {
    throw 'Versi atau pemasangan campuran ditemukan. Installer tidak melakukan perubahan.'
}

$backupFolder = Join-Path $projectRoot ('.patch_backups\PATCH-004D_OTP_' + (Get-Date -Format 'yyyyMMdd_HHmmss_fff'))
New-Item -ItemType Directory -Force -Path $backupFolder | Out-Null
foreach ($item in $changed) {
    $backupDest = Join-Path $backupFolder $item.Rel
    New-Item -ItemType Directory -Force -Path (Split-Path -Parent $backupDest) | Out-Null
    Copy-Item -LiteralPath $item.Dst -Destination $backupDest -ErrorAction Stop
}

$updated = @()
$created = @()
try {
    foreach ($item in $changed) {
        $updated += $item
        Copy-Item -LiteralPath $item.Src -Destination $item.Dst -Force -ErrorAction Stop
    }
    foreach ($item in $added) {
        $created += $item
        Copy-Item -LiteralPath $item.Src -Destination $item.Dst -ErrorAction Stop
    }
    Write-Host 'PATCH-004D OTP berhasil diterapkan.' -ForegroundColor Green
    Write-Host 'Fitur Lupa Kata Sandi siap digunakan. Tidak ada migrasi database.' -ForegroundColor Cyan
    Write-Host "Backup file lama: $backupFolder" -ForegroundColor DarkGray
    Write-Host 'Test patch: python -m pytest tests/test_password_reset_otp.py -q' -ForegroundColor Cyan
    Write-Host 'Semua test: python -m pytest tests -q' -ForegroundColor Cyan
} catch {
    foreach ($item in $updated) {
        $backupSource = Join-Path $backupFolder $item.Rel
        Copy-Item -LiteralPath $backupSource -Destination $item.Dst -Force
    }
    foreach ($item in $created) {
        if (Test-Path -LiteralPath $item.Dst -PathType Leaf) {
            Remove-Item -LiteralPath $item.Dst -Force
        }
    }
    throw
}
