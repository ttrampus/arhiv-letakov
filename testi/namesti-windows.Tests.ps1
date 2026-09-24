# Testi za namesti-windows.ps1 (Pester 5).
#
# Izvedejo pravo logiko skripte; ukazi, ki obstajajo samo na Windows (Task
# Scheduler, ACL), so nadomeščeni, da teste lahko poženemo tudi na Linuxu in
# v CI. Nastavitve, ki jih skripta zapiše, prebere pravi program (Python).
#
#   Invoke-Pester testi/namesti-windows.Tests.ps1
#
# Spremenljivka ARHIV_PYTHON pove, s katerim Pythonom brati nastavitve.

BeforeAll {
    $script:koren = Split-Path -Parent $PSScriptRoot
    $script:python = if ($env:ARHIV_PYTHON) { $env:ARHIV_PYTHON } else { "python" }

    # Nadomestki za ukaze, ki jih na Linuxu ni. Imajo parametre, ki jih skripta
    # uporablja, da jih Pester lahko preveri.
    $nadomestki = @{
        "Get-ScheduledTask"          = '[CmdletBinding()] param($TaskName, $TaskPath)'
        "Stop-ScheduledTask"         = '[CmdletBinding()] param($TaskName, $TaskPath)'
        "Start-ScheduledTask"        = '[CmdletBinding()] param($TaskName, $TaskPath)'
        "Get-ScheduledTaskInfo"      = '[CmdletBinding()] param($TaskName, $TaskPath)'
        "Unregister-ScheduledTask"   = '[CmdletBinding(SupportsShouldProcess)] param($TaskName, $TaskPath)'
        "New-ScheduledTaskTrigger"   = '[CmdletBinding()] param([switch]$Daily, [switch]$Weekly, $DaysOfWeek, $At)'
        "New-ScheduledTaskAction"    = '[CmdletBinding()] param($Execute, $Argument, $WorkingDirectory)'
        "New-ScheduledTaskSettingsSet" = '[CmdletBinding()] param($ExecutionTimeLimit, $MultipleInstances, [switch]$StartWhenAvailable, $RestartCount, $RestartInterval, $Priority, [switch]$AllowStartIfOnBatteries, [switch]$DontStopIfGoingOnBatteries)'
        "New-ScheduledTaskPrincipal" = '[CmdletBinding()] param($UserId, $LogonType, $RunLevel)'
        "Register-ScheduledTask"     = '[CmdletBinding()] param($TaskName, $TaskPath, $Action, $Trigger, $Settings, $Principal, $RunLevel, $User, $Password, [switch]$Force)'
        "Get-Acl"                    = '[CmdletBinding()] param($LiteralPath)'
    }
    foreach ($ime in $nadomestki.Keys) {
        if (-not (Get-Command $ime -ErrorAction SilentlyContinue)) {
            New-Item -Path "function:global:$ime" -Value ([scriptblock]::Create($nadomestki[$ime])) -Force | Out-Null
        }
    }

    . (Join-Path $script:koren "namesti-windows.ps1")

    # Na Windows imajo ukazi Task Schedulerja tipizirane parametre (CimInstance),
    # zato jih ustvarimo zares; nadomeščeni ostanejo registracija in poizvedbe.
    $script:naWindows = ($env:OS -eq "Windows_NT")
    # Pravi ukazi kot predmeti CommandInfo: klic prek & obide Pesterjeve nadomestke,
    # klic po imenu (tudi ScheduledTasks\...) pa bi ga Pester spet prestregel.
    $script:pravi = @{}
    if ($script:naWindows) {
        foreach ($ime in "New-ScheduledTaskTrigger", "New-ScheduledTaskAction",
                         "New-ScheduledTaskSettingsSet", "New-ScheduledTaskPrincipal") {
            $script:pravi[$ime] = Get-Command -Module ScheduledTasks -Name $ime
        }
    }
    $script:sprozilec = if ($script:naWindows) {
        @(& $script:pravi["New-ScheduledTaskTrigger"] -Daily -At ([datetime]"2026-01-01 06:00"))
    } else { @("s") }

    function script:Pripravi-Izvor([string]$koren) {
        # Na Windows (CI) pravi zgrajeni program iz ARHIV_IZVOR, drugod ovoj,
        # ki pod imenom arhiv-letakov.exe požene letaki.py.
        if ($env:OS -eq "Windows_NT") {
            if (-not $env:ARHIV_IZVOR) { Set-ItResult -Skipped -Because "ARHIV_IZVOR ni nastavljen"; return }
            return $env:ARHIV_IZVOR
        }
        $izvor = Join-Path $koren "dist"
        New-Item -ItemType Directory $izvor -Force | Out-Null
        $ovoj = Join-Path $izvor "arhiv-letakov.exe"
        Set-Content $ovoj "#!/bin/sh`nexec `"$($script:python)`" `"$(Join-Path $script:koren 'letaki.py')`" `"`$@`"`n"
        & chmod +x $ovoj
        return $izvor
    }

    function script:Preberi-Nastavitve([string]$pot) {
        # Pravi program prebere nastavitve; vrne izbrana polja kot JSON.
        $koda = @"
import json, sys
sys.path.insert(0, r'$($script:koren)')
from jedro import nastavitve
c = nastavitve.load(r'$pot')
print(json.dumps({'arhiv': str(c.archive_dir), 'meso': str(c.meat_dir), 'urnik': c.schedule,
                  'posrednik': c.proxy, 'baza': str(c.db_path), 'max_pdf_mb': c.max_pdf_mb}))
"@
        $izhod = & $script:python -c $koda
        if ($LASTEXITCODE -ne 0) { throw "Python nastavitev ni prebral: $izhod" }
        return $izhod | ConvertFrom-Json
    }
}

Describe "ConvertTo-YamlNiz in Write-Nastavitve" {
    It "pot UNC s presledki, # in narekovajem se prebere nespremenjena" {
        $mapa = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid())
        New-Item -ItemType Directory $mapa | Out-Null
        try {
            $pot = Join-Path $mapa "nastavitve.yaml"
            $arhiv = "\\dms01\Letaki d.o.o.\arhiv #1: 'test'"
            Write-Nastavitve $pot $mapa $arhiv "\\dms01\it's\meso" "pon,cet 06:15" "http://u:g@proxy:8080"
            $c = Preberi-Nastavitve $pot
            $c.arhiv | Should -Be $arhiv
            $c.meso | Should -Be "\\dms01\it's\meso"
            $c.urnik | Should -Be "pon,cet 06:15"
            $c.posrednik | Should -Be "http://u:g@proxy:8080"
            $c.baza | Should -Be (Join-Path $mapa "arhiv.db")
            $c.max_pdf_mb | Should -Be 150
        } finally { Remove-Item $mapa -Recurse -Force }
    }

    It "brez posrednika ostane posrednik prazen" {
        $mapa = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid())
        New-Item -ItemType Directory $mapa | Out-Null
        try {
            $pot = Join-Path $mapa "nastavitve.yaml"
            Write-Nastavitve $pot $mapa "\\a\b" "\\a\b-meso" "cet 06:00" ""
            (Preberi-Nastavitve $pot).posrednik | Should -BeNullOrEmpty
        } finally { Remove-Item $mapa -Recurse -Force }
    }
}

Describe "Sprožilci opravila" {
    It "tedenski urnik da tedenski sprožilec z dnevi in uro" {
        Mock New-ScheduledTaskTrigger { "sprozilec" }
        $sprozilci = ConvertFrom-Sprozilci @('{"dnevi": ["Monday", "Thursday"], "ura": "06:15"}')
        New-SprozilciOpravila $sprozilci | Out-Null
        Should -Invoke New-ScheduledTaskTrigger -Times 1 -Exactly -ParameterFilter {
            $Weekly -and ($DaysOfWeek -join ",") -eq "Monday,Thursday" -and $At.Hour -eq 6 -and $At.Minute -eq 15
        }
    }

    It "dnevni urnik z dvema urama da dva dnevna sprožilca" {
        Mock New-ScheduledTaskTrigger { "sprozilec" }
        $izpis = @('{"dnevi": [], "ura": "06:00"}', '{"dnevi": [], "ura": "18:00"}')
        @(New-SprozilciOpravila (ConvertFrom-Sprozilci $izpis)).Count | Should -Be 2
        Should -Invoke New-ScheduledTaskTrigger -Times 2 -Exactly -ParameterFilter { $Daily }
    }

    It "vrstice, ki niso JSON (npr. dnevnik), se prezrejo" {
        $izpis = @("opozorilo: nekaj", '{"dnevi": [], "ura": "06:00"}', "")
        @(ConvertFrom-Sprozilci $izpis).Count | Should -Be 1
    }

    It "izpis pravega programa se pravilno prebere" {
        $mapa = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid())
        New-Item -ItemType Directory $mapa | Out-Null
        try {
            $pot = Join-Path $mapa "nastavitve.yaml"
            Write-Nastavitve $pot $mapa "\\a\b" "\\a\b-meso" "pon,cet 07:30" ""
            $izpis = @(& $script:python (Join-Path $script:koren "letaki.py") --nastavitve $pot urnik sprozilci)
            $s = @(ConvertFrom-Sprozilci $izpis)
            $s.Count | Should -Be 1
            ($s[0].dnevi -join ",") | Should -Be "Monday,Thursday"
            $s[0].ura | Should -Be "07:30"
        } finally { Remove-Item $mapa -Recurse -Force }
    }
}

Describe "Zaščita podatkov" {
    BeforeEach {
        $script:mapa = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid())
        $script:klici = [Collections.Generic.List[string]]::new()
        Mock Invoke-Icacls { $script:klici.Add($argumenti -join " ") }
    }
    AfterEach { Remove-Item $script:mapa -Recurse -Force -ErrorAction SilentlyContinue }

    It "nova mapa dobi zaščitene pravice brez dedovanja" {
        Protect-Podatki $script:mapa "DOMENA\svc$" @("S-1-5-18")
        Test-Path (Join-Path $script:mapa "dnevniki") | Should -BeTrue
        $script:klici[0] | Should -Match "/inheritance:r"
        $script:klici[0] | Should -Match ([regex]::Escape("*S-1-5-18:(OI)(CI)F"))
        $script:klici[0] | Should -Match ([regex]::Escape("*S-1-5-32-544:(OI)(CI)F"))
        $script:klici[0] | Should -Match ([regex]::Escape('DOMENA\svc$:(OI)(CI)M'))
        # Skupina Users ali Everyone ne sme dobiti ničesar.
        $dodelitve = @(($script:klici -join " ") -split " " | Where-Object { $_ -match ":\(" })
        $dodelitve.Count | Should -Be 3
        $dodelitve | Should -Not -Match "S-1-5-32-545|S-1-1-0|S-1-5-11|Users|Everyone"
    }

    It "podtaknjena datoteka neznanega lastnika ustavi namestitev" {
        New-Item -ItemType Directory $script:mapa | Out-Null
        Set-Content (Join-Path $script:mapa "nastavitve.yaml") "obvescanje: {ukaz: calc.exe}"
        Mock Get-Lastnik { "S-1-5-21-111-222-333-1001" }
        { Protect-Podatki $script:mapa "DOMENA\svc$" @("S-1-5-18", "S-1-5-32-544") } |
            Should -Throw "*ni ustvaril skrbnik*"
        $script:klici.Count | Should -Be 0
    }

    It "datoteke skrbnika ali servisnega računa so v redu" {
        New-Item -ItemType Directory $script:mapa | Out-Null
        Set-Content (Join-Path $script:mapa "arhiv.db") "x"
        Mock Get-Lastnik { "S-1-5-21-9-9-9-500" }
        { Protect-Podatki $script:mapa "DOMENA\svc$" @("S-1-5-18", "S-1-5-21-9-9-9-500") } |
            Should -Not -Throw
    }

    It "simbolna povezava v mapi ustavi namestitev" {
        New-Item -ItemType Directory $script:mapa | Out-Null
        New-Item -ItemType SymbolicLink -Path (Join-Path $script:mapa "dnevniki") -Target ([IO.Path]::GetTempPath()) | Out-Null
        { Protect-Podatki $script:mapa "DOMENA\svc$" @("S-1-5-18") } | Should -Throw "*spoji ali simbolne povezave*"
        $script:klici.Count | Should -Be 0
    }

    It "mapa podatkov, ki je sama povezava, ustavi namestitev" {
        New-Item -ItemType SymbolicLink -Path $script:mapa -Target ([IO.Path]::GetTempPath()) | Out-Null
        { Protect-Podatki $script:mapa "DOMENA\svc$" @("S-1-5-18") } | Should -Throw "*spoj ali simbolna povezava*"
    }

    It "servisni račun nastavitve samo bere" {
        Protect-Nastavitve "/x/nastavitve.yaml" 'DOMENA\svc$'
        $script:klici[0] | Should -Match ([regex]::Escape('DOMENA\svc$:R'))
        $script:klici[0] | Should -Not -Match ([regex]::Escape('DOMENA\svc$:M'))
        $script:klici[0] | Should -Match "/inheritance:r"
    }
}

Describe "Registracija opravila" {
    BeforeEach {
        Mock New-ScheduledTaskAction { if ($script:naWindows) { & $script:pravi["New-ScheduledTaskAction"] @PesterBoundParameters } else { "akcija" } }
        Mock New-ScheduledTaskSettingsSet { if ($script:naWindows) { & $script:pravi["New-ScheduledTaskSettingsSet"] @PesterBoundParameters } else { "nastavitve" } }
        Mock New-ScheduledTaskPrincipal { if ($script:naWindows) { & $script:pravi["New-ScheduledTaskPrincipal"] @PesterBoundParameters } else { "nosilec" } }
        Mock Register-ScheduledTask { }
        Mock Get-Credential {
            New-Object Management.Automation.PSCredential("DOMENA\svc",
                (ConvertTo-SecureString "Skrivno-Geslo-123" -AsPlainText -Force))
        }
        Mock Invoke-Icacls { }
    }

    It "gMSA: prijava z geslom iz AD, brez vprašanja za geslo" {
        Register-Opravilo "C:\p\arhiv-letakov.exe" "C:\pd\nastavitve.yaml" "C:\pd" 'DOMENA\svc$' $script:sprozilec
        Should -Invoke New-ScheduledTaskPrincipal -Times 1 -Exactly -ParameterFilter {
            $UserId -eq 'DOMENA\svc$' -and $LogonType -eq "Password" -and $RunLevel -eq "Limited" }
        Should -Invoke Register-ScheduledTask -Times 1 -Exactly -ParameterFilter {
            $null -ne $Principal -and -not $Password -and $TaskPath -eq "\arhiv-letakov\" }
        Should -Invoke Get-Credential -Times 0 -Exactly
    }

    It "navaden račun: geslo gre samo v Register-ScheduledTask, nikamor drugam" {
        Register-Opravilo "C:\p\arhiv-letakov.exe" "C:\pd\nastavitve.yaml" "C:\pd" "DOMENA\svc" $script:sprozilec
        Should -Invoke Register-ScheduledTask -Times 1 -Exactly -ParameterFilter {
            $User -eq "DOMENA\svc" -and $Password -eq "Skrivno-Geslo-123" -and $RunLevel -eq "Limited" }
        Should -Invoke New-ScheduledTaskAction -Times 1 -Exactly -ParameterFilter {
            $Argument -notmatch "Skrivno" }
        Should -Invoke Invoke-Icacls -Times 0 -Exactly
    }

    It "opravilo ima trdo mejo, en primerek in nižjo prednost" {
        Register-Opravilo "C:\p\arhiv-letakov.exe" "C:\pd\nastavitve.yaml" "C:\pd" 'DOMENA\svc$' $script:sprozilec
        Should -Invoke New-ScheduledTaskSettingsSet -Times 1 -Exactly -ParameterFilter {
            $ExecutionTimeLimit -eq (New-TimeSpan -Hours 3) -and $MultipleInstances -eq "IgnoreNew" -and
            $Priority -eq 7 -and $StartWhenAvailable }
    }

    It "akcija zažene program z nastavitvami v narekovajih in delovno mapo podatkov" {
        Register-Opravilo "C:\Program Files\arhiv-letakov\arhiv-letakov.exe" "C:\Program Data\a\nastavitve.yaml" "C:\Program Data\a" 'D\s$' $script:sprozilec
        Should -Invoke New-ScheduledTaskAction -Times 1 -Exactly -ParameterFilter {
            $Execute -eq "C:\Program Files\arhiv-letakov\arhiv-letakov.exe" -and
            $Argument -eq '--nastavitve "C:\Program Data\a\nastavitve.yaml" prenesi' -and
            $WorkingDirectory -eq "C:\Program Data\a" }
    }

    It "podana poverilnica (avtomatizacija) ne sproži vprašanja za geslo" {
        $pov = New-Object Management.Automation.PSCredential("DOMENA\svc",
            (ConvertTo-SecureString "Iz-Ansibla-456" -AsPlainText -Force))
        Register-Opravilo "C:\p\a.exe" "C:\pd\n.yaml" "C:\pd" "DOMENA\svc" $script:sprozilec $pov
        Should -Invoke Get-Credential -Times 0 -Exactly
        Should -Invoke Register-ScheduledTask -Times 1 -Exactly -ParameterFilter { $Password -eq "Iz-Ansibla-456" }
    }

    It "brez gesla se registracija ustavi" {
        Mock Get-Credential { $null }
        { Register-Opravilo "C:\p\a.exe" "C:\pd\n.yaml" "C:\pd" "DOMENA\svc" $script:sprozilec } | Should -Throw "*Brez gesla*"
        Should -Invoke Register-ScheduledTask -Times 0 -Exactly
    }
}

Describe "Poskusni zagon" {
    BeforeEach {
        $script:podatki = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid())
        New-Item -ItemType Directory (Join-Path $script:podatki "dnevniki") -Force | Out-Null
        Set-Content (Join-Path $script:podatki "dnevniki/arhiv-letakov.log") "vrstica 1`nKonec: preneseno 3"
        Mock Start-ScheduledTask { }
        Mock Start-Sleep { }
        Mock Get-ScheduledTask { [pscustomobject]@{ State = "Ready" } }
    }
    AfterEach { Remove-Item $script:podatki -Recurse -Force }

    It "vrne natanko izid opravila, ne vrstic dnevnika" {
        Mock Get-ScheduledTaskInfo { [pscustomobject]@{ LastTaskResult = 0 } }
        $izid = Invoke-PoskusniZagon $script:podatki "\\a\b" 6>$null
        @($izid).Count | Should -Be 1
        $izid | Should -Be 0
    }

    It "neuspel zagon vrne kodo napake" {
        Mock Get-ScheduledTaskInfo { [pscustomobject]@{ LastTaskResult = 1 } }
        Invoke-PoskusniZagon $script:podatki "\\a\b" 6>$null 3>$null | Should -Be 1
    }
}

Describe "Varovala" {
    It "mapa programa, ki ni arhiv-letakov, se ne briše" {
        { Assert-MapaPrograma "C:\Program Files" } | Should -Throw "*arhiv-letakov*"
        { Assert-MapaPrograma "C:\" } | Should -Throw
        { Assert-MapaPrograma "C:\Program Files\arhiv-letakov\" } | Should -Not -Throw
    }

    It "brez skrbniških pravic se nič ne zgodi" {
        Mock Test-Skrbnik { $false }
        Mock Install-Program { throw "ne bi smel priti sem" }
        { Install-ArhivLetakov -Arhiv "\\a\b" -Racun 'D\s$' -Izvor "." -Mapa "/x/arhiv-letakov" -Podatki "/x/p" } |
            Should -Throw "*skrbnik*"
        Should -Invoke Install-Program -Times 0 -Exactly
    }

    It "podan -Urnik se posreduje enkrat, privzeti se doda le, ko manjka" {
        Mock Install-ArhivLetakov { }
        Invoke-Glavna @{ Arhiv = "\\a\b"; Urnik = "pon 05:00" } "cet 06:00" ".\dist"
        Should -Invoke Install-ArhivLetakov -Times 1 -Exactly -ParameterFilter { $Urnik -eq "pon 05:00" -and $Izvor -eq ".\dist" }
        Invoke-Glavna @{ Arhiv = "\\a\b" } "cet 06:00" ".\dist"
        Should -Invoke Install-ArhivLetakov -Times 1 -Exactly -ParameterFilter { $Urnik -eq "cet 06:00" }
    }
}

Describe "Celotna namestitev s pravim programom" {
    It "poteče od začetka do konca in registrira pravilno opravilo" {
        $koren = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid())
        $izvor = Pripravi-Izvor $koren
        $mapa = Join-Path $koren "arhiv-letakov"
        $podatki = Join-Path $koren "podatki"
        Mock Test-Skrbnik { $true }
        Mock Get-SidRacuna { "S-1-5-21-1-2-3-4001" }
        Mock Get-MojSid { "S-1-5-21-1-2-3-500" }
        Mock Invoke-Icacls { }
        Mock Get-ScheduledTask { $null }
        Mock New-ScheduledTaskTrigger { if ($script:naWindows) { & $script:pravi["New-ScheduledTaskTrigger"] @PesterBoundParameters } else { "sprozilec" } }
        Mock New-ScheduledTaskAction { if ($script:naWindows) { & $script:pravi["New-ScheduledTaskAction"] @PesterBoundParameters } else { "akcija" } }
        Mock New-ScheduledTaskSettingsSet { if ($script:naWindows) { & $script:pravi["New-ScheduledTaskSettingsSet"] @PesterBoundParameters } else { "nastavitve" } }
        Mock New-ScheduledTaskPrincipal { if ($script:naWindows) { & $script:pravi["New-ScheduledTaskPrincipal"] @PesterBoundParameters } else { "nosilec" } }
        Mock Register-ScheduledTask { }
        try {
            Install-ArhivLetakov -Arhiv "\\dms01\letaki\arhiv" -Racun 'DOMENA\svc-letaki$' -Urnik "tor,pet 05:45" `
                -Izvor $izvor -Mapa $mapa -Podatki $podatki 6>$null
            Test-Path (Join-Path $mapa "arhiv-letakov.exe") | Should -BeTrue
            $c = Preberi-Nastavitve (Join-Path $podatki "nastavitve.yaml")
            $c.arhiv | Should -Be "\\dms01\letaki\arhiv"
            $c.meso | Should -Be "\\dms01\letaki\arhiv-meso"
            $c.urnik | Should -Be "tor,pet 05:45"
            Should -Invoke New-ScheduledTaskTrigger -Times 1 -Exactly -ParameterFilter {
                $Weekly -and ($DaysOfWeek -join ",") -eq "Tuesday,Friday" -and $At.Hour -eq 5 -and $At.Minute -eq 45 }
            Should -Invoke Register-ScheduledTask -Times 1 -Exactly -ParameterFilter { $null -ne $Principal }
            Should -Invoke Invoke-Icacls -ParameterFilter { ($argumenti -join " ") -match 'svc-letaki\$:R' }
        } finally { Remove-Item $koren -Recurse -Force }
    }

    It "druga namestitev obstoječih nastavitev ne povozi" {
        $koren = Join-Path ([IO.Path]::GetTempPath()) ([guid]::NewGuid())
        $izvor = Pripravi-Izvor $koren
        $podatki = Join-Path $koren "podatki"
        Mock Invoke-Icacls { }
        Mock Register-ScheduledTask { }
        Mock New-ScheduledTaskTrigger { if ($script:naWindows) { & $script:pravi["New-ScheduledTaskTrigger"] @PesterBoundParameters } else { "x" } }
        Mock New-ScheduledTaskAction { if ($script:naWindows) { & $script:pravi["New-ScheduledTaskAction"] @PesterBoundParameters } else { "x" } }
        Mock New-ScheduledTaskSettingsSet { if ($script:naWindows) { & $script:pravi["New-ScheduledTaskSettingsSet"] @PesterBoundParameters } else { "x" } }
        Mock New-ScheduledTaskPrincipal { if ($script:naWindows) { & $script:pravi["New-ScheduledTaskPrincipal"] @PesterBoundParameters } else { "x" } }
        Mock Test-Skrbnik { $true }
        Mock Get-SidRacuna { "S-1-5-21-1-2-3-4001" }
        Mock Get-MojSid { "S-1-5-21-1-2-3-500" }
        Mock Get-ScheduledTask { $null }
        Mock Get-Lastnik { "S-1-5-21-1-2-3-500" }
        try {
            $arg = @{ Racun = 'D\s$'; Izvor = $izvor; Mapa = (Join-Path $koren "arhiv-letakov"); Podatki = $podatki }
            Install-ArhivLetakov @arg -Arhiv "\\prvi\a\arhiv" -Urnik "cet 06:00" 6>$null
            Install-ArhivLetakov @arg -Arhiv "\\drugi\b\arhiv" -Urnik "cet 06:00" 6>$null
            (Preberi-Nastavitve (Join-Path $podatki "nastavitve.yaml")).arhiv | Should -Be "\\prvi\a\arhiv"
        } finally { Remove-Item $koren -Recurse -Force }
    }
}
