<#
.SYNOPSIS
    Postavi arhiv-letakov na Windows strežnik: program, podatke, pravice in opravilo.

.DESCRIPTION
    Program je enkraten opravek, ne storitev. Task Scheduler ga ob uri zažene,
    program prenese, kar je novega, in konča. Pod gMSA ali domenskim računom
    piše letake naravnost na delnico dokumentarnega sistema; prijavo opravi
    Windows s Kerberosom, program sam gesel ne pozna.

    Baza, nastavitve in dnevniki ostanejo lokalno v %ProgramData%, zaščiteni
    tako, da jih lahko spreminjajo samo skrbniki, SYSTEM in servisni račun;
    nastavitve servisni račun samo bere.

    Poženi v PowerShell kot skrbnik:
      powershell -ExecutionPolicy Bypass -File .\namesti-windows.ps1 -Arhiv ... -Racun ...

.PARAMETER Arhiv
    Kam naj shranjuje letake; pot UNC na delnico dokumentarnega sistema.
.PARAMETER Racun
    gMSA (DOMENA\svc-letaki$) ali domenski račun (DOMENA\svc-letaki). Za
    navaden račun skripta geslo vpraša; v ukazno vrstico ga ne vpisuj.
.PARAMETER Poverilnica
    Za avtomatizacijo (Ansible, DSC): poverilnica navadnega računa kot objekt
    PSCredential, da skripta gesla ne vpraša. Geslo tudi tako ne gre v ukazno
    vrstico. Za gMSA ni potrebna.
.PARAMETER ZazeniZdaj
    Po namestitvi opravilo takoj zažene pod servisnim računom in počaka na
    izid. To je edini pravi preizkus, da račun pride do spleta in do delnice.
.PARAMETER Odstrani
    Odstrani opravilo in program; podatkov v %ProgramData% ne briše.

.EXAMPLE
    .\namesti-windows.ps1 -Arhiv \\dms01\letaki\arhiv -Racun DOMENA\svc-letaki$ -Urnik "cet 06:00" -ZazeniZdaj
#>

[CmdletBinding()]
param(
    [string]$Arhiv,
    [string]$ArhivMeso,
    [string]$Racun,
    [string]$Urnik = "cet 06:00",
    [string]$Posrednik,
    [pscredential]$Poverilnica,
    [string]$Izvor = ".\dist\arhiv-letakov",
    [switch]$ZazeniZdaj,
    [switch]$Odstrani,
    [string]$Mapa,
    [string]$Podatki
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"

$ImeOpravila = "arhiv-letakov"
$PotOpravila = "\arhiv-letakov\"
# SID namesto imen: na slovenskem Windows se skupina imenuje "Skrbniki".
$SidSistem = "*S-1-5-18"
$SidSkrbniki = "*S-1-5-32-544"

function Test-Skrbnik {
    $jaz = [Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()
    return $jaz.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Get-MojSid {
    return [Security.Principal.WindowsIdentity]::GetCurrent().User.Value
}

function Get-SidRacuna([string]$racun) {
    try {
        return (New-Object Security.Principal.NTAccount($racun)).Translate(
            [Security.Principal.SecurityIdentifier]).Value
    } catch {
        throw "Računa $racun ni mogoče najti v domeni. Za gMSA mora ime končati z `$."
    }
}

function ConvertTo-YamlNiz([string]$besedilo) {
    # Enojni narekovaji v YAML ne poznajo ubežnih znakov; ' se podvoji.
    return "'" + $besedilo.Replace("'", "''") + "'"
}

function Invoke-Icacls([string[]]$argumenti) {
    # Absolutna pot: brez nje bi se lahko zagnal podtaknjen icacls.exe iz PATH.
    & (Join-Path $env:SystemRoot "System32\icacls.exe") @argumenti | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "icacls $($argumenti -join ' ') ni uspel ($LASTEXITCODE)" }
}

function Get-Lastnik([string]$pot) {
    return (Get-Acl -LiteralPath $pot).GetOwner([Security.Principal.SecurityIdentifier]).Value
}

function Test-ZaupanjaVrednLastnik([string]$pot, [string[]]$zaupanja) {
    # Tuja datoteka v ProgramData je lahko podtaknjena (npr. nastavitve z ukazom).
    return $zaupanja -contains (Get-Lastnik $pot)
}

function Assert-MapaPrograma([string]$pot) {
    # Mapo pred namestitvijo pobrišemo, zato mora biti res naša.
    if ((Split-Path -Leaf $pot.TrimEnd("\", "/")) -ne "arhiv-letakov") {
        throw "Mapa programa se mora imenovati 'arhiv-letakov' (podano: $pot)."
    }
}

function Install-Program([string]$izvor, [string]$mapa) {
    Assert-MapaPrograma $mapa
    $obstojece = Get-ScheduledTask -TaskName $ImeOpravila -TaskPath $PotOpravila -ErrorAction SilentlyContinue
    if ($obstojece -and $obstojece.State -eq "Running") {
        Stop-ScheduledTask -TaskName $ImeOpravila -TaskPath $PotOpravila
        Start-Sleep -Seconds 3
    }
    if (Test-Path -LiteralPath $mapa) { Remove-Item -LiteralPath $mapa -Recurse -Force }
    New-Item -ItemType Directory -Path $mapa | Out-Null
    Copy-Item -Path (Join-Path $izvor "*") -Destination $mapa -Recurse -Force
    return (Join-Path $mapa "arhiv-letakov.exe")
}

function Protect-Podatki([string]$podatki, [string]$racun, [string[]]$zaupanja) {
    if (Test-Path -LiteralPath $podatki) {
        if ((Get-Item -LiteralPath $podatki -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
            throw "$podatki je spoj ali simbolna povezava. Preveri, kdo ga je naredil, in ga odstrani."
        }
        # V ProgramData lahko privzeto ustvarja vsak uporabnik.
        $povezave = @(Get-ChildItem -LiteralPath $podatki -Recurse -Force -Attributes ReparsePoint -ErrorAction SilentlyContinue)
        if ($povezave.Count -gt 0) {
            throw "V $podatki so spoji ali simbolne povezave ($($povezave[0].FullName)). Odstrani jih in poženi znova."
        }
        foreach ($datoteka in @(Get-ChildItem -LiteralPath $podatki -Recurse -Force -File)) {
            if (-not (Test-ZaupanjaVrednLastnik $datoteka.FullName $zaupanja)) {
                throw "$($datoteka.FullName) ni ustvaril skrbnik. Preglej jo, izbriši in poženi znova."
            }
        }
    } else {
        New-Item -ItemType Directory -Path $podatki | Out-Null
    }
    Invoke-Icacls @($podatki, "/inheritance:r", "/grant:r",
        "${SidSistem}:(OI)(CI)F", "${SidSkrbniki}:(OI)(CI)F", "${racun}:(OI)(CI)M")
    Invoke-Icacls @($podatki, "/setowner", $SidSkrbniki, "/T", "/C", "/Q")
    if (@(Get-ChildItem -LiteralPath $podatki -Force).Count -gt 0) {
        Invoke-Icacls @((Join-Path $podatki "*"), "/reset", "/T", "/C", "/Q")
    }
    New-Item -ItemType Directory -Force -Path (Join-Path $podatki "dnevniki") | Out-Null
}

function Write-Nastavitve([string]$pot, [string]$podatki, [string]$arhiv, [string]$arhivMeso,
                          [string]$urnik, [string]$posrednik) {
    $vrstica = "# posrednik: 'http://proxy.podjetje.si:8080'"
    if ($posrednik) { $vrstica = "posrednik: $(ConvertTo-YamlNiz $posrednik)" }
    $vsebina = @"
# Arhiv gre na delnico, baza in dnevniki ostanejo lokalno (SQLite se čez SMB
# ne zaklepa zanesljivo).
mapa_arhiva: $(ConvertTo-YamlNiz $arhiv)
baza: $(ConvertTo-YamlNiz (Join-Path $podatki "arhiv.db"))
mapa_dnevnikov: $(ConvertTo-YamlNiz (Join-Path $podatki "dnevniki"))
urnik: $(ConvertTo-YamlNiz $urnik)

omrezje:
  cas_zahteve: 60
  cas_prenosa: 900
  premor_med_zahtevami: 2.0
  poskusi: 3
  $vrstica

meje:
  najvecji_pdf_mb: 150
  najvecja_slika_mb: 25
  najvecji_letak_skupaj_mb: 400
  najvecja_stran_mb: 20
  najvec_strani: 300
  cas_obdelave_pdf_s: 900
  najvec_pomnilnika_mb: 2048

izbor:
  samo_zivila: true
  najvec_dni_veljavnosti: 21

mesne_strani:
  vklopljeno: true
  mapa: $(ConvertTo-YamlNiz $arhivMeso)
  ocr: true

obvescanje:
  po_neuspehih: 3
  webhook: ''
  ukaz: ''
"@
    [IO.File]::WriteAllText($pot, $vsebina, (New-Object Text.UTF8Encoding($false)))
}

function Protect-Nastavitve([string]$pot, [string]$racun) {
    # Samo branje: sicer bi zlorabljen račun v 'obvescanje.ukaz' vpisal svoj ukaz.
    Invoke-Icacls @($pot, "/inheritance:r", "/grant:r",
        "${SidSistem}:F", "${SidSkrbniki}:F", "${racun}:R")
}

function ConvertFrom-Sprozilci([string[]]$izpis) {
    # Ena vrstica JSON na sprožilec (ConvertFrom-Json v 5.1 tabele ne razčleni).
    return @($izpis | Where-Object { $_ -like "{*" } | ForEach-Object { ConvertFrom-Json -InputObject $_ })
}

function New-SprozilciOpravila($sprozilci) {
    foreach ($s in $sprozilci) {
        $ob = [datetime]::ParseExact($s.ura, "HH:mm", [Globalization.CultureInfo]::InvariantCulture)
        if (@($s.dnevi).Count -gt 0) {
            New-ScheduledTaskTrigger -Weekly -DaysOfWeek ([DayOfWeek[]]@($s.dnevi)) -At $ob
        } else {
            New-ScheduledTaskTrigger -Daily -At $ob
        }
    }
}

function Register-Opravilo([string]$exe, [string]$nastavitve, [string]$podatki,
                           [string]$racun, $sprozilciOpravila, [pscredential]$poverilnica) {
    $akcija = New-ScheduledTaskAction -Execute $exe `
        -Argument "--nastavitve `"$nastavitve`" prenesi" -WorkingDirectory $podatki

    $nastavitveOpravila = New-ScheduledTaskSettingsSet `
        -ExecutionTimeLimit (New-TimeSpan -Hours 3) `
        -MultipleInstances IgnoreNew `
        -StartWhenAvailable `
        -RestartCount 2 -RestartInterval (New-TimeSpan -Minutes 15) `
        -Priority 7 `
        -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries

    if ($racun.EndsWith("$")) {
        # gMSA: geslo pridobi Windows iz AD.
        $nosilec = New-ScheduledTaskPrincipal -UserId $racun -LogonType Password -RunLevel Limited
        Register-ScheduledTask -TaskName $ImeOpravila -TaskPath $PotOpravila -Action $akcija `
            -Trigger $sprozilciOpravila -Settings $nastavitveOpravila -Principal $nosilec -Force | Out-Null
    } else {
        # Geslo gre prek API, ne v ukazno vrstico (drugi procesi, dogodek 4688).
        if (-not $poverilnica) {
            $poverilnica = Get-Credential -UserName $racun -Message "Geslo servisnega računa $racun"
        }
        if (-not $poverilnica) { throw "Brez gesla opravila ni mogoče registrirati." }
        Register-ScheduledTask -TaskName $ImeOpravila -TaskPath $PotOpravila -Action $akcija `
            -Trigger $sprozilciOpravila -Settings $nastavitveOpravila -RunLevel Limited `
            -User $poverilnica.UserName -Password $poverilnica.GetNetworkCredential().Password -Force | Out-Null
    }
}

function Invoke-PoskusniZagon([string]$podatki, [string]$arhiv) {
    Start-ScheduledTask -TaskName $ImeOpravila -TaskPath $PotOpravila
    Start-Sleep -Seconds 5
    while ((Get-ScheduledTask -TaskName $ImeOpravila -TaskPath $PotOpravila).State -eq "Running") {
        Start-Sleep -Seconds 10
    }
    $izid = (Get-ScheduledTaskInfo -TaskName $ImeOpravila -TaskPath $PotOpravila).LastTaskResult
    $dnevnik = Join-Path $podatki "dnevniki\arhiv-letakov.log"
    if (Test-Path -LiteralPath $dnevnik) { Get-Content -LiteralPath $dnevnik -Tail 15 -Encoding UTF8 | Out-Host }
    if ($izid -eq 0) {
        Write-Host "Poskusni zagon je uspel."
    } else {
        $opis = "Poskusni zagon je vrnil 0x{0:X}. Pogosti vzroki: račun nima pravice " +
            "'Log on as a batch job', nima Modify na $arhiv ali pa požarni zid ali " +
            "posrednik ne pusti ven (glej: arhiv-letakov.exe gostitelji)."
        Write-Warning ($opis -f $izid)
    }
    return $izid
}

function Uninstall-ArhivLetakov([string]$mapa, [string]$podatki) {
    Assert-MapaPrograma $mapa
    Unregister-ScheduledTask -TaskName $ImeOpravila -TaskPath $PotOpravila -Confirm:$false -ErrorAction SilentlyContinue
    if (Test-Path -LiteralPath $mapa) { Remove-Item -LiteralPath $mapa -Recurse -Force }
    Write-Host "Opravilo in program odstranjena. Podatki ostanejo v $podatki."
}

function Install-ArhivLetakov {
    [CmdletBinding()]
    param([string]$Arhiv, [string]$ArhivMeso, [string]$Racun, [string]$Urnik,
          [string]$Posrednik, [pscredential]$Poverilnica, [string]$Izvor,
          [switch]$ZazeniZdaj, [switch]$Odstrani, [string]$Mapa, [string]$Podatki)

    if (-not $Mapa) { $Mapa = Join-Path $env:ProgramFiles "arhiv-letakov" }
    if (-not $Podatki) { $Podatki = Join-Path $env:ProgramData "arhiv-letakov" }
    if (-not (Test-Skrbnik)) { throw "Poženi kot skrbnik (Run as Administrator)." }

    if ($Odstrani) {
        Uninstall-ArhivLetakov $Mapa $Podatki
        return
    }
    if (-not $Arhiv) { throw "Manjka -Arhiv (pot UNC do delnice za letake)." }
    if (-not $Racun) { throw "Manjka -Racun (gMSA DOMENA\ime`$ ali domenski račun)." }

    $exeIzvor = Join-Path $Izvor "arhiv-letakov.exe"
    if (-not (Test-Path -LiteralPath $exeIzvor)) { throw "Ni $exeIzvor. Najprej poženi zgradi.ps1." }
    if (-not $Arhiv.StartsWith("\\")) {
        Write-Warning "Arhiv ni pot UNC ($Arhiv). Zamenjanih pogonov (Z:) servisni račun ne vidi."
    }
    if (-not $ArhivMeso) { $ArhivMeso = $Arhiv.TrimEnd("\") + "-meso" }
    $zaupanja = @("S-1-5-18", "S-1-5-32-544", (Get-SidRacuna $Racun), (Get-MojSid))

    Write-Host "1/5  Program v $Mapa"
    $exe = Install-Program $Izvor $Mapa

    Write-Host "2/5  Podatki v $Podatki"
    Protect-Podatki $Podatki $Racun $zaupanja

    $nastavitve = Join-Path $Podatki "nastavitve.yaml"
    if (Test-Path -LiteralPath $nastavitve) {
        Write-Host "3/5  Nastavitve že obstajajo, puščam jih pri miru: $nastavitve"
    } else {
        Write-Host "3/5  Pišem $nastavitve"
        Write-Nastavitve $nastavitve $Podatki $Arhiv $ArhivMeso $Urnik $Posrednik
    }
    Protect-Nastavitve $nastavitve $Racun

    & $exe --nastavitve $nastavitve gostitelji | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "Program nastavitev $nastavitve ne sprejme (izhod $LASTEXITCODE)." }

    Write-Host "4/5  Opravilo $PotOpravila$ImeOpravila pod $Racun"
    $izpis = @(& $exe --nastavitve $nastavitve urnik sprozilci)
    if ($LASTEXITCODE -ne 0) { throw "Urnika v $nastavitve ni bilo mogoče prebrati." }
    # @(): 5.1 tabelo z enim elementom odvije, .Count pa v strogem načinu pade.
    $sprozilci = @(ConvertFrom-Sprozilci $izpis)
    if ($sprozilci.Count -eq 0) { throw "Urnik je 'ročno'; opravila ni treba." }
    Register-Opravilo $exe $nastavitve $Podatki $Racun @(New-SprozilciOpravila $sprozilci) $Poverilnica

    $izidZagona = 0
    if ($ZazeniZdaj) {
        Write-Host "5/5  Poskusni zagon pod $Racun (lahko traja nekaj minut) ..."
        $izidZagona = Invoke-PoskusniZagon $Podatki $Arhiv
    } else {
        Write-Host "5/5  Poskusni zagon preskočen (-ZazeniZdaj ga vklopi)."
    }

    Write-Host ""
    Write-Host "Gotovo."
    Write-Host "  Program:    $exe"
    Write-Host "  Nastavitve: $nastavitve"
    Write-Host "  Letaki:     $Arhiv"
    Write-Host "  Stanje:     & `"$exe`" --nastavitve `"$nastavitve`" stanje"
    Write-Host ""
    Write-Host "Servisni račun $Racun potrebuje:"
    Write-Host "  - pravico 'Log on as a batch job' na tem strežniku"
    Write-Host "  - Modify na $Arhiv in $ArhivMeso"
    if ($Racun.EndsWith("$")) {
        Write-Host "  - Install-ADServiceAccount na tem strežniku (Test-ADServiceAccount vrne True)"
    }
    if ($izidZagona -ne 0) {
        throw ("Namestitev je končana, poskusni zagon pa ni uspel (0x{0:X})." -f $izidZagona)
    }
}

function Invoke-Glavna($vezani, [string]$urnik, [string]$izvor) {
    $argumenti = @{}
    foreach ($kljuc in $vezani.Keys) { $argumenti[$kljuc] = $vezani[$kljuc] }
    if (-not $argumenti.ContainsKey("Urnik")) { $argumenti["Urnik"] = $urnik }
    if (-not $argumenti.ContainsKey("Izvor")) { $argumenti["Izvor"] = $izvor }
    Install-ArhivLetakov @argumenti
}

# Ob dot-sourcingu (testi) samo naložimo funkcije.
if ($MyInvocation.InvocationName -ne ".") {
    Invoke-Glavna $PSBoundParameters $Urnik $Izvor
}
