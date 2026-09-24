# Namestitev na strežnik

Za sistemce: kaj program je, kaj potrebuje in kako ga postaviti, da tedensko
sam prenaša letake. Za domačo rabo na namizju je dovolj `./namesti.sh`, opisan
v [README.md](README.md).

## Kaj to sploh je

Enkraten opravek, ne storitev. Ob vsakem zagonu obišče strani sedmih trgovin,
prenese kataloge, ki jih še ni v arhivu, in konča. Med zagoni ne teče nič.

- **ne posluša na nobenih vratih**, dohodnega prometa ne potrebuje
- **nima podatkovnega strežnika**: stanje je ena datoteka SQLite ob arhivu
- **nima prijav in gesel**, razen morebitnega webhooka za obveščanje
- ponovni zagon ničesar ne pokvari: kar je že v arhivu, preskoči (po URL in po
  vsebini SHA-256)

## Kaj potrebuje

| | |
|---|---|
| OS | Windows Server (kot `.exe` pod Task Schedulerjem) ali Linux (systemd, zabojnik) |
| Python | 3.11 ali novejši; pri `.exe` ga na strežniku ni treba |
| CPU / RAM | 1 jedro, 1 GB |
| Disk | okoli **10–15 GB na leto**; katalog je povprečno 21 MB, mesna kopija pride zraven |
| Čas zajema | 5–20 minut, odvisno od odzivnosti trgovin |
| Zunanji paketi | neobvezno `tesseract` s slovenskim jezikom in `poppler`; brez njiju Lidlovi letaki obdržijo vse strani |

Brskalnika **ne potrebuje**. Vseh sedem trgovin teče prek navadnega HTTPS,
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

Ta seznam ni le dokumentacija: **program sam ne sme nikamor drugam**. Kar ni na
seznamu, zavrne, preden zahtevo pošlje, in prav tako zavrne vsako preusmeritev,
ki bi ga s teh gostiteljev odpeljala drugam. Zato ga izpiše tudi program sam,
da ga ni treba prepisovati:

```
arhiv-letakov.exe gostitelji           # za požarni zid
arhiv-letakov.exe gostitelji --json    # za avtomatiko
```

Ko trgovina preseli datoteke na nov naslov, ga dodaj v nastavitve
(`omrezje.dovoljeni_gostitelji`) — nove izdaje programa za to ni treba.

Za namestitev še PyPI (`pypi.org`, `files.pythonhosted.org`) in paketni viri
distribucije; pri `.exe` tudi tega ne, ker se gradi drugje.

### Posrednik in TLS

Posrednik vpiši v nastavitve (`omrezje.posrednik`) ali v spremenljivko
`HTTPS_PROXY`; vpis v nastavitvah ima prednost. Samodejne nastavitve (PAC,
WPAD) in nastavitve iz brskalnika **ne veljajo** — servisni račun jih nima.

- **Prijava na posrednik:** program zna samo osnovno prijavo
  (`http://uporabnik:geslo@proxy:8080`), **ne pa NTLM ali Kerberos**. Če
  posrednik zahteva prijavo Windows, naj strežniku za gostitelje s seznama
  zgoraj dovoli prehod brez prijave. Program v tem primeru jasno javi
  `posrednik zahteva prijavo (407)`.
- **Prestrezanje TLS:** program zaupa shrambi certifikatov Windows (prek
  paketa `truststore`), zato certifikat CA podjetja, razdeljen s skupinskim
  pravilnikom, deluje brez dodatnih nastavitev.
- Poverilnice posrednika so v dnevniku zamaskirane — zapiše se samo gostitelj
  in vrata.

## Pot A: Windows strežnik (priporočeno v okolju Active Directory)

Program se zgradi v mapo `arhiv-letakov\` z `arhiv-letakov.exe` in teče kot
opravilo v Task Schedulerju. Ni storitve, ni vrat, ni Pythona na strežniku.

Namenoma mapa in ne en sam `.exe`: enodatotečni program se ob vsakem zagonu
razpakira v `%TEMP%` in od tam nalaga DLL, kar AppLocker/WDAC na utrjenih
strežnikih blokira, protivirusni programi pa takšne `.exe` radi označijo. Če
ima podjetje certifikat za podpisovanje kode, podpišite `arhiv-letakov.exe`.

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

Priporočeno je **gMSA** — geslo upravlja AD, nikjer ga ni treba hraniti:

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

Mapa `%ProgramData%\arhiv-letakov` dobi **zaščitene pravice brez dedovanja**
(SYSTEM, skrbniki, servisni račun). Privzete pravice na `ProgramData` namreč
dovolijo vsakemu uporabniku ustvarjati datoteke — kdor bi pred namestitvijo
podtaknil `nastavitve.yaml`, bi lahko pod servisnim računom zagnal svoj ukaz.
Skripta zato zavrne obstoječe datoteke, ki jih ni ustvaril skrbnik, SYSTEM ali
servisni račun, in spoje ali simbolne povezave v tej mapi.

Nastavitve (`nastavitve.yaml`) servisni račun **samo bere**; spreminjati jih
smejo samo skrbniki. Mapo programa skripta pred namestitvijo v celoti
zamenja, zato mora `-Mapa` (če ga podaš) končati z `arhiv-letakov`.

Opravilo ima: trdo mejo trajanja 3 ure, en sam primerek hkrati, nižjo
prednost (ne izriva drugih procesov strežnika) in dva ponovna poskusa po 15
minut ob napaki. Obdelava vsakega PDF ima poleg tega svojo mejo pomnilnika
(Job Object, privzeto 2 GB) in trdi rok.

`-ZazeniZdaj` opravilo takoj zažene **pod servisnim računom** in pokaže izid.
To je edini pravi preizkus, da račun pride do spleta in do delnice.

### 4. Prijava na dokumentarni sistem

Kode za LDAP ali Kerberos v programu **ni in je ne rabi**. Opravilo teče pod
domenskim računom, Windows ob dostopu do `\\dms01\...` sam opravi Kerberos in
program samo piše datoteke. Zato tudi ni gesel, ki bi jih bilo treba hraniti.

Poti morajo biti UNC (`\\streznik\delnica\...`): zamenjanih pogonov (`Z:`)
servisni račun ne vidi; program ob zagonu na to opozori. Baza in dnevniki
namenoma ostanejo lokalno, ker se SQLite čez SMB ne zaklepa zanesljivo.

**Za dokumentarni sistem:** letak se najprej piše kot `ime.pdf.part` in se
preimenuje v `ime.pdf` šele, ko je v celoti prenesen in preverjen. Datoteka
`.pdf` se na delnici torej nikoli ne pojavi napol zapisana. Dokumentarni
sistem naj prezre `*.part` in datoteke, ki se začnejo s piko (program z njimi
ob zagonu preveri, ali sme pisati).

Pred vsakim zajemom program preveri, da lahko piše na delnico. Če ne more,
takoj konča z napako (Task Scheduler pokaže `0x1`) in pošlje obvestilo —
nedosegljiva delnica ne more ostati neopažena.

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
zabojniki, chroot), urnik zapiše v `/etc/cron.d/arhiv-letakov` — enak čas, samo
drug zapis.

## Pot C: Docker

```bash
docker build -t arhiv-letakov:latest .
docker compose run --rm letaki prenesi
```

Slika je okoli 600 MB (tesseract in odvisnosti; Chromiuma ni). Kjer je namesto Dockerja
Podman, delujeta ista slika in datoteka: `podman build` in `podman-compose`.

Zabojnik naredi en zajem in konča. Ponavljanje prevzame gostitelj — v
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
mapi uporabnika — tako ga poganja avtor:

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

Da ne bo presenečenj pri uvajanju:

- **Air-gapped omrežja ne pridejo v poštev.** Program mora do strani trgovin;
  brez odhodnega dostopa nima kaj prenašati. To je tudi edina zahteva, ki je
  ni mogoče obiti.
- **Ni storitev.** Ne posluša na nobenih vratih in med zagoni ne teče nič; kdor
  pričakuje strežniški proces, ga ne bo našel.
- **Ni spletnega vmesnika in ne API-ja.** Arhiv so datoteke v mapah; kdor hoče
  vmesnik, jih postreže z lastnim.
- **Veljavnost zajemalnikov ni zagotovljena.** Trgovina lahko kadar koli
  prenovi stran; takrat je treba popraviti datoteko v `trgovine/`. Prav zato
  program javi, ko trgovina več zagonov zapored ne vrne ničesar.

## Kar bo podjetje najbrž spremenilo

V `/etc/arhiv-letakov/nastavitve.yaml`:

```yaml
urnik: cet 06:00          # dnevno HH:MM | tedensko HH:MM | pon,cet 06:15 | ročno
trgovine:
  lidl: {vklopljeno: false}   # trgovina, ki je ne spremljajo

obvescanje:
  po_neuspehih: 3         # po treh praznih zagonih javi
  webhook: "https://hooks.slack.com/services/..."   # Slack ali Discord
  ukaz: "mail -s 'arhiv-letakov' it@podjetje.si"    # ali karkoli bere s stdin

mesne_strani:
  vklopljeno: false       # če kopije samo z mesnimi stranmi ne rabijo
```

Po spremembi urnika pri poti A poženi `sudo ./namesti-streznik.sh` znova ali
popravi `OnCalendar` v `/etc/systemd/system/arhiv-letakov.timer`.

**Tedensko ali dnevno?** Privzeto je četrtek, ko izide največ letakov, a
trgovine ne objavljajo vse istega dne. Zagon, ki ne najde nič novega, traja
nekaj sekund in ne prenese ničesar — naslove, ki so že v bazi, preskoči brez
zahteve. Zato je `dnevno 06:00` skoraj zastonj in ne zgreši letaka, ki izide in
poteče med dvema četrtkoma.

## Nadzor

```bash
letaki stanje --json
```

Izpiše število katalogov, čas zadnjega prenosa in trgovine, pri katerih zajem
ne dela. **Izhodna koda 0 pomeni v redu, 1 pomeni pokvarjen zajem** — dovolj za
Nagios ali Zabbix. V zabojniku je to `docker compose run --rm letaki stanje`.

Prava skrb pri tem programu ni, da bi se sesul, ampak da trgovina prenovi
stran in zajemalnik tiho neha najdevati letake. Zato program šteje zaporedne
prazne zagone po trgovinah in po `po_neuspehih` javi na webhook ali ukaz. Isto
vidiš v `stanje` in v `./letaki` brez ukaza.

Dva zagona se ne moreta prekrivati: tekoči drži datoteko `arhiv.db.lock`, novi
se umakne in konča z 0.

## Varnostna kopija

Dovolj sta dve stvari:

- `/var/lib/arhiv-letakov/` — arhiv, mesne kopije in `arhiv.db`
- `/etc/arhiv-letakov/nastavitve.yaml`

Kopiraj `arhiv.db`, ko zajem ne teče, ali z `sqlite3 arhiv.db ".backup kopija.db"`.
Če se baza izgubi, arhiv ostane, program pa bo letake prenesel znova, ker o njih
ne ve več nič.

## Nadgradnja

```bash
cd arhiv-letakov && git pull
sudo ./namesti-streznik.sh          # nastavitev in arhiva ne povozi
```

Trgovine občasno prenovijo strani in takrat je treba popraviti zajemalnik v
`trgovine/`. Prav zato je obveščanje ob praznih zagonih vklopljeno privzeto —
brez njega arhiv tiho zastane.

## Vzdrževanje: kaj je res mesečno delo

Program sam po sebi ne potrebuje nege — nima baze, ki bi rasla, ne posodablja
se in med zagoni ne teče. Delo prinese samo zunanji svet, in to v treh oblikah:

| Kaj | Kako pogosto | Koliko dela |
|---|---|---|
| Trgovina prenovi stran ali preseli PDF | nekajkrat letno, nepredvidljivo | od ene vrstice v nastavitvah do ure dela v `trgovine/` |
| Disk se polni (10–15 GB na leto) | preveri ob četrtletju | nič, dokler je prostor |
| Posodobitev odvisnosti (`requests`, `pypdf` …) | dvakrat letno ali ob CVE | nova gradnja `.exe` in prenos na strežnik |
| Preverjanje, da zajem sploh teče | samodejno | nič, če je obveščanje vklopljeno |

**Prvi vrstici se ni mogoče izogniti** — zajemalnik je odvisen od tuje strani.
Zato program šteje zaporedne prazne zagone po trgovinah in po `po_neuspehih`
javi na webhook ali ukaz. Brez tega arhiv tiho zastane in se to opazi mesece
pozneje.

Najlažji primer prenove: trgovina preseli datoteke na nov gostitelj. Takrat je
popravek ena vrstica v `nastavitve.yaml`:

```yaml
omrezje:
  dovoljeni_gostitelji:
    spar: [nov-letak.spar.si]
```

Težji primer: stran spremeni strukturo HTML. Takrat je treba popraviti izbirnike
v `trgovine/<trgovina>.py`. Testa `testi/test_trgovine_brez_brskalnika.py`
tečeta na shranjenih vzorcih strani in pokažeta, kaj se je spremenilo.

Realna ocena za podjetje: **nekaj ur na leto, ne nekaj ur na mesec** — pod
pogojem, da je obveščanje vklopljeno in da nekdo prevzame popravke zajemalnikov.

## Kako je bilo preverjeno

Za pregled pred predajo — kaj je preizkušeno in kako to ponoviš:

| Kaj | Kako | Kje ponoviš |
|---|---|---|
| Enotni in integracijski testi (≈170) | pytest, na Linuxu in na Windows Python 3.12 | `python -m pytest testi` |
| Namestitvena skripta (25 testov) | Pester 5, z nadomeščenim Task Schedulerjem in ACL; v CI v Windows PowerShell 5.1 s pravim `.exe` | `Invoke-Pester testi/namesti-windows.Tests.ps1` |
| **E2E: celoten program** (16 scenarijev) | pravi zajem vseh 7 trgovin kot zunanji proces; vsak PDF (SHA-256, strani), mesne kopije, ponovni zagon brez podvajanja, zaklep, pravi posrednik (brez prijave, Basic, 407), požarni zid brez enega gostitelja, nedosegljiv arhiv z obvestilom, meja velikosti; na izvorni kodi in na zgrajenem `.exe` | `ARHIV_E2E=1 python -m pytest testi/e2e` |
| **E2E: Windows strežnik** | prava namestitev, lokalni servisni račun s "Log on as a batch job", prava delnica SMB (`\\localhost`), opravilo pod servisnim računom, pravice ACL, napadi (podtaknjene nastavitve, spreminjanje nastavitev, zamenjava programa), izguba dostopa do delnice, odstranitev | CI (`e2e-windows`) ali `testi\e2e\windows-streznik.ps1` na **testnem** stroju |
| Da testi res nekaj preverjajo | vsaka varnostna zaščita posebej izklopljena → testi so padli | ročno |
| SSRF prek razlik v razčlenjevanju URL | > 1,5 milijona mutiranih naslovov proti `urllib3` in `requests`, 0 razhajanj | `testi/test_fuzz.py` (30 000 v CI) |
| TLS | badssl.com: potekel, napačen gostitelj, samopodpisan, SHA-1, RC4, DH480, NULL → vse zavrnjeno | ročno |
| Pokvarjeni PDF | 500 mutiranih letakov skozi izolirano obdelavo: 0 zataknjenj, 0 nepričakovanih napak, 0 ostankov | ročno |
| ReDoS | vsi regularni izrazi na 2 MB napadalnih vhodih; dva popravljena | `testi/test_fuzz.py` |
| Znane ranljivosti odvisnosti | `pip-audit` (izvajanje in zaklenjena gradnja): 0 | CI |
| Statična analiza | `bandit`, PSScriptAnalyzer (združljivost s PowerShell 5.1, Server 2016/2019) | CI |

Windows del je bil pred predajo preizkušen v Wine (Windows Python 3.12 in
zgrajeni `.exe`): zaklep med procesi, nedosegljiva delnica UNC, izolirana
obdelava PDF v zapakiranem programu, uboj visečega `pdftoppm` prek Job Object.
Meje pomnilnika v Job Object Wine ne izvaja; ta test teče v CI na pravem
Windows (posel `windows`). **Na njihovem strežniku z AD in delnico pa pravi
dokaz da šele `namesti-windows.ps1 -ZazeniZdaj`.**

Znane omejitve:

- Preklica certifikatov (CRL/OCSP) program ne preverja, ne na Linuxu ne na
  Windows. Vklop bi zahteval odhodni dostop do strežnikov CRL/OCSP vseh
  izdajateljev, ki niso na seznamu za požarni zid, in bi zajem za strogim
  požarnim zidom ustavil. Tveganje je majhno: napadalec bi potreboval ukraden
  (in preklican) certifikat trgovine *in* položaj v omrežju med strežnikom in
  trgovino; vse ostalo preverjanje TLS (veljavnost, ime, veriga) je vklopljeno.
- Prijava NTLM/Kerberos na posredniku ni podprta (glej zgoraj).
- Trgovina lahko prenovi stran; takrat je treba popraviti zajemalnik.

## Ko kaj ne dela

| Znak | Kaj je narobe |
|---|---|
| `Nastavitev ni: ...` | brez terminala program ne ugiba; naredi `/etc/arhiv-letakov/nastavitve.yaml` |
| `povezavo preskočim: gostitelj ... ni na seznamu` | trgovina je preselila datoteke; dodaj gostitelja v `omrezje.dovoljeni_gostitelji` |
| `prenos je presegel N MB` | letak je res večji od meje ali pa odgovor ni letak; preveri in po potrebi dvigni `meje.najvecji_pdf_mb` |
| opravilo se ne zažene (`0x80070569`) | servisni račun nima `Log on as a batch job` |
| opravilo se konča z `0x1`, v dnevniku `ni mogoče pisati` | servisni račun nima Modify na delnici ali delnica ni dosegljiva |
| `posrednik zahteva prijavo (407)` | posrednik hoče prijavo NTLM/Kerberos; strežniku dovolite prehod brez nje |
| `CERTIFICATE_VERIFY_FAILED` | CA posrednika ni v shrambi Windows; uvozite jo v `Trusted Root` računalnika |
| občasno `403` pri eni trgovini (npr. Spar) | zaščita pred roboti (Cloudflare) je zavrnila posamezen zagon; naslednji zagon letake pobere, obvestilo pride šele po treh zaporednih neuspehih |
| `mesne kopije ne delam: ... prekinjena` | PDF je obdelavo zataknil; izvirnik je shranjen, manjka le mesna kopija |
| Lidlovi letaki obdržijo vse strani | manjka `tesseract-ocr-slv` |
| vse trgovine odpovejo naenkrat | omrežje, posrednik ali prestrezanje TLS |
| `database is locked` | dva zagona hkrati; enota `Type=oneshot` in zaklep to sicer preprečita |

## Pravno

Program prenaša javno objavljene letake s spletnih strani trgovin. Preden ga
podjetje postavi v redno rabo, naj pogleda pogoje uporabe posamezne trgovine —
zlasti če bi kataloge objavljalo naprej ali iz njih delalo izdelke. Zajem je
namenoma počasen (2 sekundi med zahtevami) in se predstavi z navadnim
uporabniškim nizom brskalnika.
