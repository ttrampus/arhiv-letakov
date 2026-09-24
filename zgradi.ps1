<#
.SYNOPSIS
    Zgradi dist\arhiv-letakov\ (mapa z arhiv-letakov.exe) za Windows strežnike.

.DESCRIPTION
    Poženi na Windows stroju s Pythonom 3.12 (x64). Odvisnosti pridejo iz
    requirements-gradnja.txt z zaklenjenimi različicami in kontrolnimi vsotami,
    zato vsaka gradnja uporabi natanko iste, preverjene pakete. Pred gradnjo
    tečejo testi, po gradnji pa se zgrajeni program še enkrat zažene.

      powershell -ExecutionPolicy Bypass -File zgradi.ps1
#>

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$koren = Split-Path -Parent $MyInvocation.MyCommand.Path
Set-Location $koren

function Invoke-Korak([string]$opis, [scriptblock]$ukaz) {
    Write-Host "==> $opis"
    & $ukaz
    if ($LASTEXITCODE -ne 0) { throw "$opis ni uspelo (izhod $LASTEXITCODE)" }
}

$python = "py"
$razlicica = & $python -3.12 -c "import sys; print(sys.version_info[:2] == (3, 12))" 2>$null
if ($LASTEXITCODE -ne 0 -or $razlicica -ne "True") {
    throw "Potreben je Python 3.12 (x64); zaklenjene odvisnosti veljajo zanj. Namesti ga s python.org."
}

if (Test-Path ".\venv-gradnja") { Remove-Item ".\venv-gradnja" -Recurse -Force }
Invoke-Korak "virtualno okolje" { & $python -3.12 -m venv venv-gradnja }
$py = ".\venv-gradnja\Scripts\python.exe"

Invoke-Korak "pip" { & $py -m pip install --quiet --upgrade pip }
Invoke-Korak "odvisnosti (zaklenjene)" {
    & $py -m pip install --quiet --require-hashes --no-deps -r requirements-gradnja.txt
}
Invoke-Korak "testi" { & $py -m pytest testi -q }

if (Test-Path ".\build") { Remove-Item ".\build" -Recurse -Force }
if (Test-Path ".\dist") { Remove-Item ".\dist" -Recurse -Force }
Invoke-Korak "gradnja" { & $py -m PyInstaller --clean --noconfirm arhiv-letakov.spec }

$exe = Join-Path $koren "dist\arhiv-letakov\arhiv-letakov.exe"
if (-not (Test-Path $exe)) { throw "gradnja ni naredila $exe" }

# Zgrajeni program mora teči brez Pythona in najti vse svoje module.
$preizkus = Join-Path $env:TEMP "arhiv-letakov-preizkus"
New-Item -ItemType Directory -Force -Path $preizkus | Out-Null
Copy-Item "nastavitve.primer.yaml" (Join-Path $preizkus "nastavitve.yaml") -Force
Invoke-Korak "zgrajeni program" {
    & $exe --nastavitve (Join-Path $preizkus "nastavitve.yaml") gostitelji | Out-Null
}
Remove-Item $preizkus -Recurse -Force

Write-Host ""
Write-Host "Gotovo: dist\arhiv-letakov\  (na strežnik gre cela mapa)"
Write-Host "Namesti z:  .\namesti-windows.ps1 -Arhiv \\streznik\delnica\letaki -Racun DOMENA\svc-letaki$"
