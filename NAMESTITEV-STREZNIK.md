# Namestitev na strežnik

Za sistemce: kaj program je, kaj potrebuje in kako ga postaviti, da tedensko
sam prenaša letake. Za domačo rabo na namizju je dovolj `./namesti.sh`, opisan
v [README.md](README.md).

## Kaj to sploh je

Enkraten opravek, ne storitev. Ob vsakem zagonu obišče strani sedmih trgovin,
prenese kataloge, ki jih še ni v arhivu, in konča. Med zagoni ne teče nič.

- ne posluša na nobenih vratih, dohodnega prometa ne potrebuje
- nima podatkovnega strežnika: stanje je ena datoteka SQLite ob arhivu
- nima prijav in gesel, razen morebitnega webhooka za obveščanje
- ponovni zagon ničesar ne pokvari: kar je že v arhivu, preskoči (po URL in po
  vsebini SHA-256)

## Kaj potrebuje

| | |
|---|---|
| OS | Windows Server (kot `.exe` pod Task Schedulerjem) ali Linux (systemd, zabojnik) |
| Python | 3.11 ali novejši; pri `.exe` ga na strežniku ni treba |
| CPU / RAM | 1 jedro, 1 GB |
| Disk | okoli 10–15 GB na leto; katalog je povprečno 21 MB, mesna kopija pride zraven |
| Čas zajema | 5–20 minut, odvisno od odzivnosti trgovin |
| Zunanji paketi | neobvezno `tesseract` s slovenskim jezikom in `poppler`; brez njiju Lidlovi letaki obdržijo vse strani |

Brskalnika ne potrebuje. Vseh sedem trgovin teče prek navadnega HTTPS,
zato v `.exe` ni ničesar zunanjega.

### Odhodni promet

Samo HTTPS (443) na te gostitelje:

```
www.mercator.si          www.tus.si            www.spar.si
letak.spar.si            cdn.ipaper.io         www.e-leclerc.si
www.lidl.si
endpoints.leaflets.schwarz   assets.leaflets.schwarz
www.hofer.si             letaki.hofer.si       view.publitas.com
www.eurospin.si          digitalflyer.eurospin.it
```

Drugam program tudi sam ne gre. Zahtevo na gostitelja, ki ga ni na seznamu,
zavrne, preden jo pošlje, enako tudi preusmeritev nanj. Seznam izpiše tudi
program:

```
arhiv-letakov.exe gostitelji           # za požarni zid
arhiv-letakov.exe gostitelji --json    # za avtomatiko
```

Ko trgovina preseli datoteke na nov naslov, ga dodaj v nastavitve
(`omrezje.dovoljeni_gostitelji`); nove izdaje programa za to ni treba.

Za namestitev še PyPI (`pypi.org`, `files.pythonhosted.org`) in paketni viri
distribucije; pri `.exe` tudi tega ne, ker se gradi drugje.

### Posrednik in TLS

Posrednik vpiši v nastavitve (`omrezje.posrednik`) ali v spremenljivko
`HTTPS_PROXY`; vpis v nastavitvah ima prednost. Samodejne nastavitve (PAC,
WPAD) in nastavitve iz brskalnika ne veljajo, ker jih servisni račun nima.

- **Prijava na posrednik:** program zna samo osnovno prijavo
  (`http://uporabnik:geslo@proxy:8080`), ne pa NTLM ali Kerberos. Če
  posrednik zahteva prijavo Windows, naj strežniku za gostitelje s seznama
  zgoraj dovoli prehod brez prijave. Program v tem primeru jasno javi
  `posrednik zahteva prijavo (407)`.
- **Prestrezanje TLS:** program zaupa shrambi certifikatov Windows (prek
  paketa `truststore`), zato certifikat CA podjetja, razdeljen s skupinskim
  pravilnikom, deluje brez dodatnih nastavitev.
- V dnevnik se od posrednika zapišeta samo gostitelj in vrata, brez
  uporabnika in gesla.

## Pot A: Windows strežnik (priporočeno v okolju Active Directory)

Program se zgradi v mapo `arhiv-letakov\` z `arhiv-letakov.exe` in teče kot
opravilo v Task Schedulerju. Ni storitve, ni vrat, ni Pythona na strežniku.

Namenoma mapa in ne en sam `.exe`: enodatotečni program se ob vsakem zagonu
razpakira v `%TEMP%` in od tam nalaga DLL, kar AppLocker/WDAC na utrjenih
strežnikih blokira, protivirusni programi pa takšne `.exe` radi označijo. Če
ima podjetje certifikat za podpisovanje kode, podpiši `arhiv-letakov.exe`.

### 1. Program

Potrebuješ skladišče (**Code → Download ZIP**) in zgrajeni program v mapi
`dist\arhiv-letakov\` znotraj njega. Program dobiš na enega od dveh načinov:

- **iz CI:** Actions → zadnji uspešen zagon na `main` → Artifacts →
  `arhiv-letakov-windows` (za prenos je potrebna prijava v GitHub; artefakt
  velja 90 dni)
- **sam:** na Windows stroju s Pythonom 3.12 x64
  `powershell -ExecutionPolicy Bypass -File zgradi.ps1`

Oba načina uporabita zaklenjene odvisnosti s kontrolnimi vsotami
(`requirements-gradnja.txt`). Na strežnik gre cela mapa, Python tam ni potreben.
Datoteke, prenesene iz interneta, pred namestitvijo odblokiraj:
`Get-ChildItem -Recurse | Unblock-File`.

### 2. Priprava v AD (enkrat, skrbnik domene)

Priporočen je gMSA, ker geslo upravlja AD in ga ni treba nikjer hraniti:

```powershell
New-ADServiceAccount -Name svc-letaki -DNSHostName svc-letaki.domena.local `
    -PrincipalsAllowedToRetrieveManagedPassword "STREZNIK01$"
# na strežniku:
Install-ADServiceAccount svc-letaki
Test-ADServiceAccount svc-letaki          # mora vrniti True
```

Račun potrebuje:

- **Modify** na delnici za letake (in za mesne kopije)
- pravico **Log on as a batch job** na strežniku (Local Security Policy →
  User Rights Assignment, ali GPO, če ga ta pravica omejuje)
- nič drugega: program ne posluša, ne potrebuje lokalnega skrbnika in ne piše
  nikamor zunaj svojih map

### 3. Namestitev na strežnik (lokalni skrbnik)

```powershell
powershell -ExecutionPolicy Bypass -File .\namesti-windows.ps1 `
    -Arhiv \\dms01\letaki\arhiv `
    -Racun DOMENA\svc-letaki$ `
    -Urnik "cet 06:00" `
    -ZazeniZdaj
```

Za navaden domenski račun (brez `$`) skripta geslo vpraša v oknu; v ukazno
vrstico ga ne vpisuj, ker bi ga videli drugi procesi in revizijski dnevnik.

Skripta:

| | |
|---|---|
| `%ProgramFiles%\arhiv-letakov\` | program (pišejo samo skrbniki) |
| `%ProgramData%\arhiv-letakov\nastavitve.yaml` | nastavitve |
| `%ProgramData%\arhiv-letakov\arhiv.db` | stanje (lokalno, **ne** na delnici) |
| `%ProgramData%\arhiv-letakov\dnevniki\` | dnevniki, 5 × 2 MB |
| `\\dms01\letaki\arhiv\`, `\\dms01\letaki\arhiv-meso\` | letaki za dokumentarni sistem |
| opravilo `\arhiv-letakov\arhiv-letakov` | zajem po urniku |

Mapa `%ProgramData%\arhiv-letakov` dobi zaščitene pravice brez dedovanja
(SYSTEM, skrbniki, servisni račun). Privzete pravice na `ProgramData` namreč
dovolijo vsakemu uporabniku ustvarjati datoteke, in kdor bi pred namestitvijo
podtaknil `nastavitve.yaml`, bi lahko pod servisnim računom zagnal svoj ukaz.
Skripta zato zavrne obstoječe datoteke, ki jih ni ustvaril skrbnik, SYSTEM ali
servisni račun, in spoje ali simbolne povezave v tej mapi.

Nastavitve (`nastavitve.yaml`) servisni račun samo bere; spreminjati jih
smejo samo skrbniki. Mapo programa skripta pred namestitvijo v celoti
zamenja, zato mora `-Mapa` (če ga podaš) končati z `arhiv-letakov`.

Opravilo ima: trdo mejo trajanja 3 ure, en sam primerek hkrati, nižjo
prednost (ne izriva drugih procesov strežnika) in dva ponovna poskusa po 15
minut ob napaki. Obdelava vsakega PDF ima poleg tega svojo mejo pomnilnika
(Job Object, privzeto 2 GB) in trdi rok.

`-ZazeniZdaj` opravilo takoj zažene pod servisnim računom in pokaže izid.
To je edini pravi preizkus, da račun pride do spleta in do delnice.

### 4. Prijava na dokumentarni sistem

Program nima kode za LDAP ali Kerberos in je ne potrebuje. Opravilo teče pod
domenskim računom, Windows ob dostopu do `\\dms01\...` sam opravi Kerberos in
program samo piše datoteke. Zato tudi ni gesel, ki bi jih bilo treba hraniti.

Poti morajo biti UNC (`\\streznik\delnica\...`): zamenjanih pogonov (`Z:`)
servisni račun ne vidi; program ob zagonu na to opozori. Baza in dnevniki
namenoma ostanejo lokalno, ker se SQLite čez SMB ne zaklepa zanesljivo.

Za dokumentarni sistem: letak se najprej piše kot `ime.pdf.part` in se
preimenuje v `ime.pdf` šele, ko je v celoti prenesen in preverjen. Datoteka
`.pdf` se na delnici torej nikoli ne pojavi napol zapisana. Dokumentarni
sistem naj prezre `*.part` in datoteke, ki se začnejo s piko (program z njimi
ob zagonu preveri, ali sme pisati).

Pred vsakim zajemom program preveri, da lahko piše na delnico. Če ne more,
takoj konča z napako (Task Scheduler pokaže `0x1`) in pošlje obvestilo.

### 5. Preverjanje

```powershell
$exe = "$env:ProgramFiles\arhiv-letakov\arhiv-letakov.exe"
$cfg = "$env:ProgramData\arhiv-letakov\nastavitve.yaml"
& $exe --nastavitve $cfg gostitelji               # kaj mora dovoliti požarni zid
& $exe --nastavitve $cfg stanje                   # izhodna koda 1 = zajem ne dela
Get-ScheduledTaskInfo -TaskPath \arhiv-letakov\ -TaskName arhiv-letakov
```

Odstranitev: `.\namesti-windows.ps1 -Odstrani` (podatki v `%ProgramData%`
ostanejo).

## Pot B: sistemska namestitev s systemd

Priporočena, kadar ima podjetje navaden strežnik.

```bash
git clone https://github.com/ttrampus/arhiv-letakov.git
cd arhiv-letakov
sudo ./namesti-streznik.sh --urnik "cet 06:00"
```

Skripta nič ne sprašuje, zato jo lahko poganja tudi Ansible. Naredi:

| | |
|---|---|
| `/opt/arhiv-letakov` | koda in `venv` |
| `/etc/arhiv-letakov/nastavitve.yaml` | nastavitve, `root:arhiv-letakov 0640` |
| `/var/lib/arhiv-letakov` | arhiv, mesne kopije in `arhiv.db` |
| `/var/log/arhiv-letakov` | dnevniki (sami se obrezujejo, 5 × 2 MB) |
| uporabnik `arhiv-letakov` | sistemski, brez prijave |
| `/usr/local/bin/letaki` | ukaz, ki že ve za nastavitve |
| `arhiv-letakov.timer` | zajem po urniku |

Enota teče utrjeno: `ProtectSystem=strict`, `ProtectHome`, `NoNewPrivileges`,
pisati sme samo v svoj arhiv in dnevnike. Poleg mej v nastavitvah ima še
`MemoryMax=2G`, `CPUQuota=150%` in `TasksMax=128`.

```bash
sudo systemctl start arhiv-letakov.service     # prvi zajem takoj
systemctl list-timers arhiv-letakov.timer      # kdaj je naslednji
journalctl -u arhiv-letakov -n 50              # kaj je delal
letaki stanje                                  # kaj je v arhivu
sudo -u arhiv-letakov letaki prenesi           # ročni zajem
```

Možnosti: `--mapa`, `--uporabnik`, `--brez-paketov` (pakete namesti sam),
`--brez-casovnika` (samo namesti, ne vklopi).

Pozna `apt`, `dnf`, `zypper` in `pacman`. Kjer systemd ni (starejši strežniki,
zabojniki, chroot), urnik zapiše v `/etc/cron.d/arhiv-letakov`.

## Pot C: Docker

```bash
docker build -t arhiv-letakov:latest .
docker compose run --rm letaki prenesi
```

Slika je okoli 600 MB (tesseract in odvisnosti). Kjer je namesto Dockerja
Podman, delujeta ista slika in datoteka: `podman build` in `podman-compose`.

Zabojnik naredi en zajem in konča. Ponavljanje prevzame gostitelj; v
`streznik/` sta pripravljena `docker-arhiv-letakov.service` in `.timer`:

```bash
sudo cp streznik/docker-arhiv-letakov.* /etc/systemd/system/
sudo systemctl enable --now docker-arhiv-letakov.timer
```

Nastavitve so priklopljene iz `streznik/nastavitve.zabojnik.yaml`, arhiv in
dnevniki so imenovana nosilca. Zabojnik teče kot UID 10001, brez pravic in z
bralnim korenskim sistemom.

## Pot D: Kubernetes

```bash
kubectl create configmap arhiv-letakov-nastavitve \
    --from-file=nastavitve.yaml=streznik/nastavitve.zabojnik.yaml
kubectl apply -f streznik/kubernetes-cronjob.yaml
```

CronJob ob četrtkih ob 6:00 po ljubljanskem času, `concurrencyPolicy: Forbid`,
PVC 100 GB. Slika mora biti v registru gruče.

## Pot E: brez root pravic

Če administrator računa s pravicami ne da, program teče tudi povsem v domači
mapi uporabnika, tako kot ga poganja avtor:

```bash
./namesti.sh                 # vpraša za mape, trgovine in uro
./letaki urnik namesti       # uporabniška enota systemd, brez root
```

Enota gre v `~/.config/systemd/user/`, `loginctl enable-linger` pa poskrbi, da
teče tudi, ko uporabnik ni prijavljen. Brez systemd je dovolj vrstica v
uporabnikovem `crontab -e`:

```cron
0 6 * * 4 $HOME/arhiv-letakov/letaki prenesi >> $HOME/arhiv-letakov/dnevniki/cron.log 2>&1
```

## Česa program ne zna

- Brez odhodnega dostopa do strani trgovin ne dela, zato omrežja brez
  interneta ne pridejo v poštev.
- Ni storitev in nima spletnega vmesnika ali API-ja. Arhiv so datoteke v mapah.
- Prijave NTLM ali Kerberos na posredniku ne zna (glej zgoraj).
- Preklica certifikatov (CRL/OCSP) ne preverja, ker bi za to potreboval dostop
  do strežnikov CRL/OCSP vseh izdajateljev, teh pa ni na seznamu za požarni
  zid. Ostalo preverjanje TLS (veljavnost, ime, veriga) je vklopljeno.
- Ko trgovina prenovi stran, je treba popraviti njeno datoteko v `trgovine/`.

## Pogoste spremembe nastavitev

V `nastavitve.yaml` (Windows: `%ProgramData%\arhiv-letakov\`, Linux:
`/etc/arhiv-letakov/`):

```yaml
urnik: cet 06:00          # dnevno HH:MM | tedensko HH:MM | pon,cet 06:15 | ročno
trgovine:
  lidl: {vklopljeno: false}   # izklop posamezne trgovine

obvescanje:
  po_neuspehih: 3         # po treh praznih zagonih javi
  webhook: "https://hooks.slack.com/services/..."   # Slack ali Discord
  ukaz: "mail -s 'arhiv-letakov' it@podjetje.si"    # ali karkoli bere s stdin

mesne_strani:
  vklopljeno: false       # brez kopij samo z mesnimi stranmi
```

Po spremembi urnika na Windows znova poženi `namesti-windows.ps1` z istimi
parametri. Na Linuxu časovnik urnika iz nastavitev ne bere, zato poženi
`sudo ./namesti-streznik.sh --urnik "dnevno 06:00"` ali popravi `OnCalendar` v
`/etc/systemd/system/arhiv-letakov.timer`.

Privzeto je četrtek, ko izide največ letakov, a trgovine ne objavljajo vse
istega dne. Zagon, ki ne najde nič novega, traja nekaj sekund in ne prenese
ničesar, ker naslove, ki so že v bazi, preskoči brez zahteve. Zato je
`dnevno 06:00` skoraj zastonj in ne zgreši letaka, ki izide in poteče med
dvema četrtkoma.

## Nadzor

```bash
letaki stanje --json
```

Izpiše število katalogov, čas zadnjega prenosa in trgovine, pri katerih zajem
ne dela. Izhodna koda 0 pomeni v redu, 1 pa pokvarjen zajem, kar zadošča za
Nagios ali Zabbix. V zabojniku je to `docker compose run --rm letaki stanje`.

Najpogostejša težava je, da trgovina prenovi stran in zajemalnik neha najti
letake. Zato program šteje zaporedne prazne zagone po trgovinah in po
`po_neuspehih` javi na webhook ali ukaz. Isto vidiš v `stanje` in v `./letaki`
brez ukaza.

Dva zagona se ne moreta prekrivati: tekoči drži datoteko `arhiv.db.lock`, novi
se umakne in konča z 0.

## Varnostna kopija

Dovolj sta dve stvari:

- `/var/lib/arhiv-letakov/` (arhiv, mesne kopije in `arhiv.db`)
- `/etc/arhiv-letakov/nastavitve.yaml`

Na Windows sta to `%ProgramData%\arhiv-letakov\` in delnica z letaki.

Kopiraj `arhiv.db`, ko zajem ne teče, ali z `sqlite3 arhiv.db ".backup kopija.db"`.
Če se baza izgubi, arhiv ostane, program pa bo letake prenesel znova, ker o njih
ne ve več nič.

## Nadgradnja

```bash
cd arhiv-letakov && git pull
sudo ./namesti-streznik.sh --urnik "cet 06:00"   # isti urnik kot ob namestitvi
```

Nastavitev in arhiva skripta ne povozi. Na Windows prenesi nov program in znova
poženi `namesti-windows.ps1` z istimi parametri; zamenja mapo programa,
nastavitve in podatki ostanejo.

## Vzdrževanje

| Kaj | Kako pogosto | Koliko dela |
|---|---|---|
| Trgovina prenovi stran ali preseli PDF | nekajkrat letno, nepredvidljivo | od ene vrstice v nastavitvah do ure dela v `trgovine/` |
| Disk se polni (10–15 GB na leto) | preveri ob četrtletju | nič, dokler je prostor |
| Posodobitev odvisnosti (`requests`, `pypdf` …) | dvakrat letno ali ob CVE | nova gradnja `.exe` in prenos na strežnik |
| Preverjanje, da zajem sploh teče | samodejno | nič, če je obveščanje vklopljeno |

Najlažji primer prenove: trgovina preseli datoteke na nov gostitelj. Takrat je
popravek ena vrstica v `nastavitve.yaml`:

```yaml
omrezje:
  dovoljeni_gostitelji:
    spar: [nov-letak.spar.si]
```

Težji primer: stran spremeni strukturo HTML. Takrat je treba popraviti izbirnike
v `trgovine/<trgovina>.py`. Kaj trgovina vrne, pokaže
`letaki -p prenesi --trgovina <ime> --poskusno`.

## Testi

```bash
python -m pytest testi                          # brez spleta, slabih 20 sekund
ARHIV_E2E=1 python -m pytest testi/e2e          # pravi zajem vseh sedmih trgovin
```

```powershell
Invoke-Pester testi/namesti-windows.Tests.ps1   # namestitvena skripta
```

GitHub Actions jih poganja ob vsakem pushu, na Linuxu in na Windows. Na
Windows zgradi še `.exe` in ga s `testi/e2e/windows-streznik.ps1` namesti s
servisnim računom in delnico SMB, tako kot na strežniku. Odvisnosti preveri s
`pip-audit`, kodo pa z `bandit`.

## Ko kaj ne dela

| Znak | Kaj je narobe |
|---|---|
| `Nastavitev ni: ...` | brez terminala program ne ugiba; naredi `/etc/arhiv-letakov/nastavitve.yaml` |
| `povezavo preskočim: gostitelj ... ni na seznamu` | trgovina je preselila datoteke; dodaj gostitelja v `omrezje.dovoljeni_gostitelji` |
| `prenos je presegel N MB` | letak je res večji od meje ali pa odgovor ni letak; preveri in po potrebi dvigni `meje.najvecji_pdf_mb` |
| opravilo se ne zažene (`0x80070569`) | servisni račun nima `Log on as a batch job` |
| opravilo se konča z `0x1`, v dnevniku `ni mogoče pisati` | servisni račun nima Modify na delnici ali delnica ni dosegljiva |
| `posrednik zahteva prijavo (407)` | posrednik hoče prijavo NTLM/Kerberos; dovoli strežniku prehod brez nje |
| `CERTIFICATE_VERIFY_FAILED` | CA posrednika ni v shrambi Windows; uvozi jo v `Trusted Root` računalnika |
| občasno `403` pri eni trgovini (npr. Spar) | zaščita pred roboti (Cloudflare) je zavrnila posamezen zagon; naslednji zagon letake pobere, obvestilo pride šele po treh zaporednih neuspehih |
| `mesne kopije ne delam: ... prekinjena` | PDF je obdelavo zataknil; izvirnik je shranjen, manjka le mesna kopija |
| Lidlovi letaki obdržijo vse strani | manjka `tesseract-ocr-slv` |
| vse trgovine odpovejo naenkrat | omrežje, posrednik ali prestrezanje TLS |
| `database is locked` | dva zagona hkrati; enota `Type=oneshot` in zaklep to sicer preprečita |

## Pravno

Program prenaša javno objavljene letake s spletnih strani trgovin. Preden ga
podjetje postavi v redno rabo, naj pogleda pogoje uporabe posamezne trgovine,
zlasti če bi kataloge objavljalo naprej ali iz njih delalo izdelke. Zajem je
namenoma počasen (2 sekundi med zahtevami) in se predstavi z navadnim
uporabniškim nizom brskalnika.
