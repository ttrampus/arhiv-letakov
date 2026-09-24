<#
.SYNOPSIS
    E2E na pravem Windows: namestitev, servisni račun, delnica SMB, Task Scheduler.

.DESCRIPTION
    Posnema strežnik pri naročniku, kolikor se da brez domene:
      - lokalni servisni račun brez skrbniških pravic, s pravico "Log on as a batch job"
      - prava delnica SMB (\\localhost\letaki), do katere račun dostopa prek omrežja
      - namestitev z namesti-windows.ps1, kot bi jo pognal skrbnik
      - opravilo v Task Schedulerju, ki teče pod servisnim računom
    in preveri rezultat na delnici, pravice ACL ter dva napada: navaden uporabnik
    podtakne nastavitve, servisni račun poskusi nastavitve spremeniti.

    Teče v CI (windows-latest) kot skrbnik. NA PRODUKCIJSKEM STREŽNIKU GA NE POGANJAJ:
    ustvari lokalna računa, delnico in namesti program.

      powershell -ExecutionPolicy Bypass -File testi\e2e\windows-streznik.ps1 -Izvor dist\arhiv-letakov
#>
param([Parameter(Mandatory = $true)][string]$Izvor)

Set-StrictMode -Version 2.0
$ErrorActionPreference = "Stop"
$koren = Split-Path -Parent (Split-Path -Parent $PSScriptRoot)
$namesti = Join-Path $koren "namesti-windows.ps1"
$Izvor = (Resolve-Path $Izvor).Path

$napake = New-Object Collections.Generic.List[string]
function Preveri([bool]$pogoj, [string]$opis) {
    if ($pogoj) { Write-Host "  OK    $opis" } else { Write-Host "  NAPAKA $opis"; $napake.Add($opis) }
}

function New-Geslo {
    # Naključno geslo naravnost v SecureString; kot navaden niz ne obstaja nikjer.
    $bajti = New-Object byte[] 24
    [Security.Cryptography.RandomNumberGenerator]::Create().GetBytes($bajti)
    $geslo = New-Object Security.SecureString
    foreach ($znak in ([Convert]::ToBase64String($bajti) + "aA1!").ToCharArray()) { $geslo.AppendChar($znak) }
    $geslo.MakeReadOnly()
    return $geslo
}

function New-Racun([string]$ime) {
    $geslo = New-Geslo
    Get-LocalUser -Name $ime -ErrorAction SilentlyContinue | Remove-LocalUser
    New-LocalUser -Name $ime -Password $geslo -PasswordNeverExpires -AccountNeverExpires | Out-Null
    return New-Object Management.Automation.PSCredential("$env:COMPUTERNAME\$ime", $geslo)
}

function Get-Sid([string]$racun) {
    return (New-Object Security.Principal.NTAccount($racun)).Translate(
        [Security.Principal.SecurityIdentifier]).Value
}

function Grant-PrijavaPaketnoOpravilo([string[]]$sidi) {
    # Kot bi skrbnik naredil v Local Security Policy ali prek GPO.
    $inf = Join-Path $env:TEMP "pravice.inf"
    $sdb = Join-Path $env:TEMP "pravice.sdb"
    secedit /export /cfg $inf /areas USER_RIGHTS | Out-Null
    $vrstice = Get-Content $inf -Encoding Unicode
    $dodatek = ($sidi | ForEach-Object { "*$_" }) -join ","
    if ($vrstice -match "^SeBatchLogonRight") {
        $vrstice = $vrstice | ForEach-Object { if ($_ -match "^SeBatchLogonRight") { "$_,$dodatek" } else { $_ } }
    } else {
        $vrstice = $vrstice | ForEach-Object { $_; if ($_ -eq "[Privilege Rights]") { "SeBatchLogonRight = $dodatek" } }
    }
    Set-Content $inf $vrstice -Encoding Unicode
    secedit /configure /db $sdb /cfg $inf /areas USER_RIGHTS | Out-Null
    if ($LASTEXITCODE -ne 0) { throw "secedit ni uspel ($LASTEXITCODE)" }
}

function Wait-Opravilo([string]$ime, [string]$pot = "\") {
    # Počaka, da opravilo res steče in konča. Sam "State" ni dovolj: takoj po
    # zagonu (in med prvo prijavo novega uporabnika) je lahko še "Ready".
    $rok = (Get-Date).AddMinutes(10)
    do {
        Start-Sleep -Seconds 2
        $info = Get-ScheduledTaskInfo -TaskName $ime -TaskPath $pot
        $stanje = (Get-ScheduledTask -TaskName $ime -TaskPath $pot).State
    } while ((Get-Date) -lt $rok -and ($stanje -eq "Running" -or
             $info.LastTaskResult -eq 267009 -or $info.LastTaskResult -eq 267011))
    return $info.LastTaskResult
}

function Invoke-KotUporabnik([Management.Automation.PSCredential]$pov, [string]$ukaz) {
    # Ukaz zažene kot opravilo pod danim računom (pravi prijavni kontekst, kot
    # ga ima produkcijsko opravilo) in vrne, kar je ukaz izpisal. Vsaka napaka
    # vrže izjemo (ErrorAction Stop), izjema pa vrne "ZAVRNJENO: ...". Ves
    # izhod, tudi napake samega PowerShella, preusmeri cmd.exe v datoteko.
    $izhod = Join-Path $script:mapaIzhodov "$([guid]::NewGuid().ToString('N')).txt"
    $polni = "`$ErrorActionPreference = 'Stop'; `$ProgressPreference = 'SilentlyContinue'; & { try { $ukaz } catch { 'ZAVRNJENO: ' + `$_.Exception.Message } }"
    $koda = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($polni))
    $ps = Join-Path $env:SystemRoot "System32\WindowsPowerShell\v1.0\powershell.exe"
    $akcija = New-ScheduledTaskAction -Execute (Join-Path $env:SystemRoot "System32\cmd.exe") `
        -Argument "/c $ps -NoProfile -NonInteractive -EncodedCommand $koda > $izhod 2>&1"
    $ime = "e2e-pomocnik-$([guid]::NewGuid().ToString('N').Substring(0, 8))"
    Register-ScheduledTask -TaskName $ime -Action $akcija -User $pov.UserName `
        -Password $pov.GetNetworkCredential().Password -RunLevel Limited | Out-Null
    try {
        Start-ScheduledTask -TaskName $ime
        $izid = Wait-Opravilo $ime
        # PowerShell ob prvem zagonu novega uporabnika na izhod za napake zapiše
        # vrstico napredka v obliki CLIXML; ta ni del izida ukaza.
        $vsebina = if (Test-Path $izhod) {
            (@(Get-Content $izhod) | Where-Object { $_ -notlike "#< CLIXML*" -and $_ -notlike "<Objs *" }) -join "`n"
        } else { "" }
        if (-not $vsebina) { return ("PRAZNO (opravilo 0x{0:X})" -f $izid) }
        return $vsebina.Trim()
    } finally {
        Unregister-ScheduledTask -TaskName $ime -Confirm:$false
        Remove-Item $izhod -Force -ErrorAction SilentlyContinue
    }
}

function Invoke-Zajem {
    Start-ScheduledTask -TaskPath "\arhiv-letakov\" -TaskName "arhiv-letakov"
    return Wait-Opravilo "arhiv-letakov" "\arhiv-letakov\"
}

$podatki = Join-Path $env:ProgramData "arhiv-letakov"
$program = Join-Path $env:ProgramFiles "arhiv-letakov"
$delnica = "C:\e2e-dms\letaki"
$unc = "\\localhost\letaki"

Write-Host "== Priprava: računa, pravice, delnica"
$svc = New-Racun "svc-letaki"
$navaden = New-Racun "navaden-uporabnik"
$sidSvc = Get-Sid $svc.UserName
Grant-PrijavaPaketnoOpravilo @($sidSvc, (Get-Sid $navaden.UserName))
# Mapa za izhode pomožnih opravil: obema testnima računoma zapisljiva.
$script:mapaIzhodov = "C:\e2e-izhod"
if (Test-Path $script:mapaIzhodov) { Remove-Item $script:mapaIzhodov -Recurse -Force }
New-Item -ItemType Directory $script:mapaIzhodov | Out-Null
icacls $script:mapaIzhodov /grant "$($svc.UserName):(OI)(CI)M" "$($navaden.UserName):(OI)(CI)M" | Out-Null
$kdo = Invoke-KotUporabnik $svc "whoami"
Preveri ($kdo -like "*svc-letaki") "pomožno opravilo teče pod servisnim računom ($kdo)"
if (Test-Path $podatki) { Remove-Item $podatki -Recurse -Force }
if (Test-Path "C:\e2e-dms") { Remove-Item "C:\e2e-dms" -Recurse -Force }
New-Item -ItemType Directory $delnica | Out-Null
icacls $delnica /inheritance:r /grant "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F" "$($svc.UserName):(OI)(CI)M" | Out-Null
Get-SmbShare -Name letaki -ErrorAction SilentlyContinue | Remove-SmbShare -Force
New-SmbShare -Name letaki -Path $delnica -ChangeAccess $svc.UserName -FullAccess "Administrators" | Out-Null

Write-Host "== Napad 1: navaden uporabnik pred namestitvijo podtakne nastavitve"
$podtaknjeno = Invoke-KotUporabnik $navaden (
    "New-Item -ItemType Directory '$podatki' -Force | Out-Null; " +
    "Set-Content '$podatki\nastavitve.yaml' 'obvescanje: {ukaz: calc.exe}'; 'PODTAKNJENO'")
Preveri ($podtaknjeno -eq "PODTAKNJENO") "privzete pravice ProgramData navadnemu uporabniku dovolijo podtakniti datoteko (izhodišče napada): $podtaknjeno"
$zavrnjeno = $false
try {
    & $namesti -Arhiv "$unc\arhiv" -Racun $svc.UserName -Poverilnica $svc -Izvor $Izvor 6>$null
} catch { $zavrnjeno = $_.Exception.Message -like "*ni ustvaril skrbnik*" }
Preveri $zavrnjeno "namestitev podtaknjene nastavitve zavrne"
Preveri (-not (Get-ScheduledTask -TaskPath "\arhiv-letakov\" -ErrorAction SilentlyContinue)) "ob zavrnitvi opravilo ni registrirano"
Remove-Item $podatki -Recurse -Force

Write-Host "== Namestitev, kot jo naredi skrbnik (s poskusnim zagonom pod servisnim računom)"
$zacetek = Get-Date
$namestitev = $true
try {
    & $namesti -Arhiv "$unc\arhiv" -Racun $svc.UserName -Poverilnica $svc -Urnik "cet 06:00" -Izvor $Izvor -ZazeniZdaj
} catch {
    $namestitev = $false
    Write-Host "   namestitev: $($_.Exception.Message)"
}
Write-Host ("   trajanje: {0:N0} s" -f ((Get-Date) - $zacetek).TotalSeconds)
Preveri $namestitev "namestitev s poskusnim zagonom se konča brez napake"

Write-Host "== Opravilo"
$opravilo = Get-ScheduledTask -TaskPath "\arhiv-letakov\" -TaskName "arhiv-letakov"
Preveri ($opravilo.Principal.UserId -like "*svc-letaki") "teče pod servisnim računom"
Preveri ($opravilo.Principal.LogonType -eq "Password") "prijava z geslom (dostop do omrežja), ne S4U"
Preveri ($opravilo.Principal.RunLevel -eq "Limited") "brez povišanih pravic"
Preveri ($opravilo.Settings.ExecutionTimeLimit -eq "PT3H") "trda meja 3 ure"
Preveri ($opravilo.Settings.MultipleInstances -eq "IgnoreNew") "en primerek hkrati"
Preveri ($opravilo.Settings.Priority -eq 7) "nižja prednost"
Preveri ((Get-ScheduledTaskInfo -TaskPath "\arhiv-letakov\" -TaskName "arhiv-letakov").LastTaskResult -eq 0) "poskusni zagon uspel (0x0)"

Write-Host "== Letaki na delnici"
$pdf = @(Get-ChildItem "$delnica\arhiv" -Recurse -Filter *.pdf -ErrorAction SilentlyContinue)
$trgovine = @($pdf | ForEach-Object { $_.Directory.Parent.Name } | Sort-Object -Unique)
Write-Host ("   {0} letakov iz: {1}" -f $pdf.Count, ($trgovine -join ", "))
Preveri ($pdf.Count -gt 0) "letaki so na delnici"
Preveri ($trgovine.Count -ge 5) "letaki iz vsaj 5 od 7 trgovin (IP-ji CI so včasih blokirani)"
$slabi = @($pdf | Where-Object {
    $glava = New-Object byte[] 4
    $tok = [IO.File]::OpenRead($_.FullName); [void]$tok.Read($glava, 0, 4); $tok.Close()
    [Text.Encoding]::ASCII.GetString($glava) -ne "%PDF" })
Preveri ($slabi.Count -eq 0) "vsaka datoteka je PDF"
$lastniki = @($pdf | ForEach-Object { (Get-Acl $_.FullName).GetOwner([Security.Principal.SecurityIdentifier]).Value } | Sort-Object -Unique)
Preveri (($lastniki.Count -eq 1) -and ($lastniki[0] -eq $sidSvc)) "vse je zapisal servisni račun prek SMB"
Preveri (@(Get-ChildItem "$delnica\arhiv-meso" -Recurse -Filter *.pdf -ErrorAction SilentlyContinue).Count -gt 0) "mesne kopije so na delnici"
Preveri (@(Get-ChildItem $delnica -Recurse -Filter *.part).Count -eq 0) "ni napol zapisanih .part"
Preveri (Test-Path "$podatki\arhiv.db") "baza je lokalno v ProgramData"
Preveri (-not (Test-Path "$delnica\arhiv.db")) "baze ni na delnici"

Write-Host "== Pravice v ProgramData"
$acl = Get-Acl $podatki
Preveri $acl.AreAccessRulesProtected "brez dedovanja iz ProgramData"
$sidi = @($acl.Access | ForEach-Object { $_.IdentityReference.Translate([Security.Principal.SecurityIdentifier]).Value })
Preveri (-not ($sidi -contains "S-1-5-32-545")) "skupina Users nima dostopa"
Preveri (-not ($sidi -contains "S-1-1-0")) "Everyone nima dostopa"
Preveri (-not ($sidi -contains "S-1-5-11")) "Authenticated Users nima dostopa"

Write-Host "== Napad 2: servisni račun poskusi spremeniti nastavitve"
$poskus = Invoke-KotUporabnik $svc "Add-Content '$podatki\nastavitve.yaml' 'obvescanje: {ukaz: calc.exe}'; 'ZAPISAL'"
Preveri ($poskus -like "ZAVRNJENO*") "servisni račun nastavitev ne more spremeniti ($poskus)"
$bere = Invoke-KotUporabnik $svc "(Get-Content '$podatki\nastavitve.yaml' -TotalCount 1) -ne `$null"
Preveri ($bere -eq "True") "servisni račun nastavitve lahko bere ($bere)"

Write-Host "== Napad 3: navaden uporabnik po namestitvi"
$poskus = Invoke-KotUporabnik $navaden "Set-Content '$podatki\nastavitve.yaml' 'x'; 'ZAPISAL'"
Preveri ($poskus -like "ZAVRNJENO*") "navaden uporabnik ne more spremeniti nastavitev ($poskus)"
$poskus = Invoke-KotUporabnik $navaden "New-Item -ItemType Directory '$podatki\dnevniki\podtaknjeno' | Out-Null; 'ZAPISAL'"
Preveri ($poskus -like "ZAVRNJENO*") "navaden uporabnik ne more ustvarjati v ProgramData\arhiv-letakov ($poskus)"
$poskus = Invoke-KotUporabnik $navaden "Set-Content '$program\arhiv-letakov.exe' 'x'; 'ZAPISAL'"
Preveri ($poskus -like "ZAVRNJENO*") "navaden uporabnik ne more zamenjati programa ($poskus)"

Write-Host "== Drugi zagon: nič novega"
$pred = @(Get-ChildItem "$delnica\arhiv" -Recurse -Filter *.pdf).Count
$izid = Invoke-Zajem
Preveri ($izid -eq 0) ("drugi zagon uspel (0x{0:X})" -f $izid)
Preveri (@(Get-ChildItem "$delnica\arhiv" -Recurse -Filter *.pdf).Count -eq $pred) "drugi zagon ni podvojil letakov"
$zadnja = @(Select-String -Path "$podatki\dnevniki\arhiv-letakov.log" -Pattern "Konec:" -Encoding UTF8)[-1].Line
Preveri ($zadnja -match "preneseno 0,") "drugi zagon: $zadnja"

Write-Host "== Okvara: servisni račun izgubi dostop do delnice"
Revoke-SmbShareAccess -Name letaki -AccountName $svc.UserName -Force | Out-Null
$izid = Invoke-Zajem
Preveri ($izid -ne 0) ("brez dostopa do delnice opravilo ne javi uspeha (0x{0:X})" -f $izid)
$dnevnik = Get-Content "$podatki\dnevniki\arhiv-letakov.log" -Raw -Encoding UTF8
Preveri ($dnevnik -match "ni mogoče pisati") "dnevnik pove, da delnica ni zapisljiva"
Grant-SmbShareAccess -Name letaki -AccountName $svc.UserName -AccessRight Change -Force | Out-Null

Write-Host "== Stanje za nadzor"
$exe = Join-Path $program "arhiv-letakov.exe"
$json = & $exe --nastavitve "$podatki\nastavitve.yaml" stanje --json | Out-String | ConvertFrom-Json
Preveri ($json.katalogov -eq $pred) "stanje pozna vse letake ($($json.katalogov))"

Write-Host "== Odstranitev"
& $namesti -Odstrani 6>$null
Preveri (-not (Get-ScheduledTask -TaskPath "\arhiv-letakov\" -ErrorAction SilentlyContinue)) "opravilo odstranjeno"
Preveri (-not (Test-Path $program)) "program odstranjen"
Preveri (Test-Path "$podatki\arhiv.db") "podatki ostanejo"
Preveri (@(Get-ChildItem "$delnica\arhiv" -Recurse -Filter *.pdf).Count -eq $pred) "letaki na delnici ostanejo"

Write-Host ""
Write-Host "== Dnevnik (zadnjih 40 vrstic)"
Get-Content "$podatki\dnevniki\arhiv-letakov.log" -Tail 40 -Encoding UTF8 -ErrorAction SilentlyContinue | Out-Host
Write-Host ""
if ($napake.Count) {
    Write-Host "E2E NI USPEL ($($napake.Count)):"
    $napake | ForEach-Object { Write-Host "  - $_" }
    exit 1
}
Write-Host "E2E USPEL"
