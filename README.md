# Arhiv trgovinskih letakov

Prenaša tedenske kataloge slovenskih živilskih trgovin in jih zlaga v
`arhiv/<trgovina>/<leto>/`. Ob vsakem letaku shrani še kopijo, ki ima samo
strani z mesom. Teče sam, iz Task Schedulerja na Windows ali časovnika systemd.

Trgovine: Mercator, Tuš, Spar/Interspar, E.Leclerc, Lidl, Hofer, Eurospin.

## Namestitev na Windows strežnik

Na kratko; podrobnosti, pravice in odpravljanje težav so v
[NAMESTITEV-STREZNIK.md](NAMESTITEV-STREZNIK.md).

1. Prenesi to skladišče (**Code → Download ZIP**) in ga razpakiraj.
2. Prenesi zgrajeni program: **Actions → zadnji uspešen zagon na `main` →
   Artifacts → `arhiv-letakov-windows`** in ga razpakiraj v `dist\arhiv-letakov\`
   znotraj razpakiranega skladišča. Lahko ga tudi zgradiš sam z `zgradi.ps1`.
3. V PowerShellu kot skrbnik, v razpakirani mapi:
   ```powershell
   Get-ChildItem -Recurse | Unblock-File
   powershell -ExecutionPolicy Bypass -File .\namesti-windows.ps1 `
       -Arhiv \\dms01\letaki\arhiv -Racun DOMENA\svc-letaki$ -ZazeniZdaj
   ```

Pred tem mora skrbnik domene pripraviti servisni račun (gMSA) s pravico
"Log on as a batch job" in pravico Modify na delnici, požarni zid pa mora
dovoliti gostitelje, ki jih izpiše `arhiv-letakov.exe gostitelji`.

## Namestitev na Linux

```bash
git clone https://github.com/ttrampus/arhiv-letakov.git
cd arhiv-letakov
./namesti.sh
```

`namesti.sh` naredi virtualno okolje, namesti odvisnosti, nato pa
vpraša, kam shranjevati kataloge, katere trgovine spremljati, ali naj dela mesne
kopije in kako pogosto naj preverja. Odgovori se zapišejo v `nastavitve.yaml`.
Vsako vprašanje ima privzeti odgovor, tako da Enter skozi vsa da vseh sedem
trgovin in dnevni zagon ob 06:00.

Za OCR (Lidlovi letaki so slike) potrebuješ še tesseract:

```bash
sudo pacman -S tesseract tesseract-data-slv poppler        # Arch
sudo apt install tesseract-ocr tesseract-ocr-slv poppler-utils   # Debian
```

Brskalnika program ne potrebuje: vseh sedem trgovin teče prek navadnega HTTPS.

## Uporaba

```bash
./letaki                             stanje arhiva in seznam ukazov
./letaki prenesi                     prenesi vse novo
./letaki prenesi --poskusno          pokaži, kaj je novega, ne prenašaj
./letaki prenesi --trgovina mercator samo ena trgovina
./letaki prenesi --vse               tudi tematske brošure
./letaki seznam                      kaj je v arhivu
./letaki meso                        zgradi manjkajoče mesne kopije
./letaki meso --znova                naredi jih vse na novo
./letaki pregled                     kaj v arhivu izbor danes zavrne
./letaki pregled --izbrisi           in to izbriši
./letaki urnik                       stanje časovnika
./letaki -p prenesi                  podroben izpis
```

Ukaz `prenesi` je privzet, zato je `./letaki --poskusno` isto kot
`./letaki prenesi --poskusno`. Deluje iz katere koli mape in brez vklapljanja
virtualnega okolja.

## Na strežniku

Spodnje velja za računalnik, na katerem imaš svoj uporabniški račun. Za
namestitev v podjetju — sistemski uporabnik, koda v `/opt`, nastavitve v
`/etc`, Docker ali Kubernetes — glej **[NAMESTITEV-STREZNIK.md](NAMESTITEV-STREZNIK.md)**
in `sudo ./namesti-streznik.sh`.

```bash
./letaki urnik namesti
./letaki urnik
./letaki urnik odstrani
```

Zapiše uporabniško enoto systemd (`~/.config/systemd/user/arhiv-letakov.timer`),
zato root ni potreben, in vklopi `loginctl enable-linger`, da teče tudi, ko nisi
prijavljen. `Persistent=true` nadoknadi zagon, zamujen med izklopom, naključni
zamik do 15 minut pa razprši obisk trgovin.

Uro spremeniš v `nastavitve.yaml` in znova poženeš `./letaki urnik namesti`:

```yaml
urnik: dnevno 06:00
# urnik: dnevno 06:00,18:00
# urnik: tedensko
# urnik: pon,cet 06:15
# urnik: ročno
```

Zagon, ki ne najde nič novega, traja nekaj sekund in ne prenese ničesar, ker
naslove iz `arhiv.db` preskoči brez zahteve. Zato je dnevno preverjanje poceni,
trgovine pa ne izdajajo vse istega dne.

Brez systemd:

```cron
0 6 * * * $HOME/arhiv-letakov/letaki prenesi >> $HOME/arhiv-letakov/dnevniki/cron.log 2>&1
```

Izpis gre na zaslon in v `dnevniki/arhiv-letakov.log` (5 × 2 MB).

### Ko zajem neha delati

Spletne strani se spreminjajo in trgovina lahko tiho neha vračati kataloge.
Vsak zagon si zapiše, ali je trgovina kaj našla. Ko jih toliko zapored ne najde
nič, program vrne izhodno kodo 1, kar systemd šteje za neuspeh, in pošlje
sporočilo:

```yaml
obvescanje:
  po_neuspehih: 3
  webhook: https://hooks.slack.com/services/...
  ukaz: mail -s "arhiv-letakov" jaz@podjetje.si
```

Za nadzorni sistem je tu `./letaki stanje` (in `--json`): izhodna koda 0 pomeni
v redu, 1 pomeni, da zajem ne dela.

`webhook` pošlje `{"text": ...}`, kar razumeta Slack in Discord; `ukaz` dobi
sporočilo na standardni vhod. Nastaviš lahko oboje ali nobenega. Prvi uspešni
zajem števec ponastavi, stanje pa vidiš tudi v izpisu golega `./letaki`.

Če hočeš ob neuspehu obvestilo prek systemd, dodaj enoti `OnFailure=`.

Prostor: en teden vseh sedmih trgovin je okoli 170 MB, mesne kopije še kakih 40 %
tega, torej računaj z 9-10 GB na leto. Arhiv se sam ne obrezuje.

## Kaj se zbira

Samo tedenski živilski letaki. Trgovine mešajo živilske kataloge z brošurami za
sončenje, šolo, nakit in vino; te odpadejo. `jedro/izbor.py` odloči v treh
korakih: zavrnjena beseda v naslovu, sprejeta beseda v naslovu, sicer dolžina
veljavnosti (privzeto do 21 dni). Vsaka zavrnitev se izpiše z razlogom:

```
preskočim Katalog Vse za šolo: ni živilski letak, veljavnost 31 dni (več kot 21)
```

Uravnavaš v `nastavitve.yaml` pod `izbor:`, z `samo_zivila: false` pa arhiviraš
vse. Mercator Cash&Carry in E.Leclerc "Best offer" štejeta za živilska letaka,
Pika zgibanka ne.

Podvojenih ni: katalog, katerega naslov je že v `arhiv.db`, preskočimo brez
zahteve, po prenosu pa primerjamo še sha256, tako da ista vsebina pod novim
naslovom odpade. Prenos gre v `<ime>.pdf.part` in se preimenuje šele, ko je cel.

## Mesne strani

Ob vsakem letaku nastane kopija v `arhiv-meso/` s samo tistimi stranmi, na
katerih je vsaj en mesni izdelek; 32-stranski katalog se navadno skrči na 12-14
strani. Izvirniki ostanejo nedotaknjeni.

Besedišče je v `jedro/meso.py`. Primerjamo brez šumnikov, da se ujameta
`piščančji` in `piscancji`, kar hkrati vsrka šum iz OCR. Ribe in morski sadeži
ne štejejo za meso; če hočeš drugače, prestavi seznam `FISH` v `STEMS`. Stran,
ki je ni mogoče prebrati, vedno obdržimo, ker "neberljivo" ni "brez mesa".

Strani brez besedilne plasti gredo skozi tesseract, kar traja kakih 7 sekund na
stran; brez njega tak letak obdrži vse strani. Preverjanje:

```bash
sqlite3 arhiv.db "SELECT m.store, m.title, v.source_pages, v.kept_pages
                  FROM meat_versions v JOIN magazines m ON m.id=v.magazine_id
                  ORDER BY m.store;"
```

Po dodajanju besede v `STEMS` poženi `./letaki meso --znova`.

## Testi

```bash
venv/bin/python -m unittest discover -s testi -t .
```

Pokrivajo branje datumov, izbor živilskih letakov, mesno besedišče, pretvorbo
urnika v `OnCalendar`, kazalo in obveščanje. Ne gredo na splet, zato tečejo v
desetinki sekunde in v GitHub Actions ob vsakem pushu.

## Zgradba

```
letaki              ovojna skripta
letaki.py           ukazi
namesti.sh          namestitev
jedro/              nastavitve, prenos, baza, izbor, meso, urnik, čarovnik
trgovine/           po ena datoteka na trgovino
```

Zajemalnik trgovine samo najde kataloge in vrne predmete `Magazine`. Prenos,
zgoščevanje, odstranjevanje podvojenih, arhiviranje in mesne strani so skupni,
zato je nova trgovina običajno 40 vrstic. Vsaka teče v svojem try/except: če ena
stran pade, se to zabeleži, ostale pa se dokončajo.

Kako pridemo do posamezne trgovine:

| Trgovina | Način |
|---|---|
| Mercator, Tuš, E.Leclerc | navaden HTTP, neposredne povezave na PDF |
| Spar | navaden HTTP, a stran zahteva glave brskalnika |
| Lidl | JSON API `endpoints.leaflets.schwarz/v4/flyer` |
| Hofer | Akamai zavrne brskalniški User-Agent, zato odkrit agent; PDF stoji pri Publitas in ga poberemo iz HTML |
| Eurospin | OAuth `client_credentials` z javno kodo odjemalca iz svežnja JS, nato navaden JSON API |

### Varnost

Program bere vsebino tujih strani, zato ji ne zaupa:

- **Kam sme:** vsak naslov iz tuje strani ali API-ja gre skozi
  `jedro/naslovi.py` — samo gostitelji te trgovine, samo https na vratih 443,
  brez poverilnic in nenavadnih znakov v naslovu. Enako velja za vsako
  preusmeritev. Ob neposredni povezavi `jedro/povezava.py` preveri še naslov IP,
  na katerega se je vtičnica res povezala, zato tudi dovoljeno ime, ki ga DNS
  usmeri v notranje omrežje, ne pride skozi.
- **Koliko sme:** vsak odgovor ima zgornjo mejo velikosti in skupnega trajanja
  (`meje` v nastavitvah); nič se ne bere v pomnilnik brez meje.
- **PDF:** obdelava letaka teče v ločenem procesu s trdim rokom in mejo
  pomnilnika (Linux: `RLIMIT_AS` in lastna skupina procesov; Windows: Job
  Object z `KILL_ON_JOB_CLOSE`). Ob izteku roka umre tudi vse, kar je proces
  zagnal (`pdftoppm`, `tesseract`), začasne slike pa pobriše starš. Pokvarjen ali
  zlonameren PDF lahko uniči samo svojo mesno kopijo, ne zajema. `pypdf` je
  zahtevan v različici brez znanih ranljivosti.
- **Regularni izrazi** nad besedilom tujih strani so linearni (preverjeno z
  ReDoS testi v `testi/test_fuzz.py`).
- **Poverilnice:** posrednik se v dnevnik zapiše brez uporabnika in gesla;
  program drugih gesel ne pozna.
- **Odvisnosti:** gradnja za Windows uporablja zaklenjene različice s
  kontrolnimi vsotami (`requirements-gradnja.txt`), CI jih preveri s
  `pip-audit`, kodo pa z `bandit`.
- **Zunanji programi** (`schtasks`, `icacls`, `tesseract`) se kličejo z
  absolutno potjo, zato podtaknjen program v trenutni mapi ne more steči.

### Nova trgovina

Recimo, da dodajaš Jager. Prepiši `trgovine/_predloga.py` v
`trgovine/jager.py`, razred preimenuj v `JagerStore` in mu nastavi
`name = "jager"`, napiši `find_magazines`, razred vpiši v
`trgovine/__init__.py` in trgovino dodaj v `nastavitve.yaml`. Uporabi
`fetchers.http`, kjer gre, in `fetchers.browser` samo, kadar navaden HTTP
odpove. Če trgovina objavi slike namesto PDF, namesto `file_url` nastavi
`image_urls` in prenos jih sešije. Preveri z:

```bash
./letaki prenesi --trgovina jager --poskusno
```

Ko trgovina neha kaj najti, zagon izpiše `nič najdenega (postavitev strani se je
morda spremenila)`. Popraviš izbirnik v datoteki te trgovine ali jo do takrat
izklopiš z `vklopljeno: false`.

## Vljudnost

Ena zahteva na dve sekundi, ponovni poskusi z zamikom, en kratek zagon na dan in
nobenega brskanja zunaj strani z letaki.

## Licenca

MIT, glej `LICENSE`. Licenca velja za kodo. Preneseni katalogi so avtorsko delo
trgovin in ta licenca zanje ne velja.
