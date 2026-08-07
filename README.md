# Arhiv trgovinskih letakov

Prenaša tedenske kataloge slovenskih živilskih trgovin in jih zlaga v
`arhiv/<trgovina>/<leto>/`. Ob vsakem letaku shrani še kopijo, ki ima samo
strani z mesom. Teče lahko sam, iz časovnika systemd.

Trgovine: Mercator, Tuš, Spar/Interspar, E.Leclerc, Lidl, Hofer, Eurospin.

## Namestitev

```bash
git clone https://github.com/ttrampus/arhiv-letakov.git
cd arhiv-letakov
./namesti.sh
```

`namesti.sh` naredi virtualno okolje, namesti odvisnosti in Chromium, nato pa
vpraša, kam shranjevati kataloge, katere trgovine spremljati, ali naj dela mesne
kopije in kako pogosto naj preverja. Odgovori se zapišejo v `nastavitve.yaml`.
Vsako vprašanje ima privzeti odgovor, tako da Enter skozi vsa da vseh sedem
trgovin in dnevni zagon ob 06:00.

Za OCR (Lidlovi letaki so slike) potrebuješ še tesseract:

```bash
sudo pacman -S tesseract tesseract-data-slv poppler        # Arch
sudo apt install tesseract-ocr tesseract-ocr-slv poppler-utils   # Debian
```

Na golem strežniku Chromium potrebuje še sistemske knjižnice:
`./venv/bin/playwright install-deps chromium`.

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
| Lidl | JSON API `endpoints.leaflets.schwarz/v4/flyer`, brez brskalnika |
| Hofer | Akamai zavrne navaden HTTP, zato Chromium in nato PDF Publitas |
| Eurospin | pregledovalnik JS, žeton OAuth preberemo s strani in vprašamo API |

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
