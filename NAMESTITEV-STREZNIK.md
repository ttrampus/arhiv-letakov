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
| OS | Linux (systemd ali zabojnik) |
| Python | 3.11 ali novejši |
| CPU / RAM | 1 jedro, 2 GB (Chromium ju porabi največ) |
| Disk | okoli **10–15 GB na leto**; katalog je povprečno 21 MB, mesna kopija pride zraven |
| Čas zajema | 5–20 minut, odvisno od odzivnosti trgovin |
| Zunanji paketi | `tesseract` s slovenskim jezikom in `poppler` (Lidlovi letaki so slike), Chromium prinese Playwright |

### Odhodni promet

Samo HTTPS (443) na te gostitelje:

```
www.mercator.si          www.tus.si            www.spar.si
www.e-leclerc.si         www.lidl.si           www.hofer.si
www.eurospin.si          digitalflyer.eurospin.it
endpoints.leaflets.schwarz
```

Za namestitev še PyPI (`pypi.org`, `files.pythonhosted.org`), Chromium
(`playwright.azureedge.net` oziroma `cdn.playwright.dev`) in paketni viri
distribucije. Po namestitvi tega ne rabi več.

Če gre promet skozi posrednika, nastavi `HTTPS_PROXY` (`requests` ga vzame sam,
Chromiumu ga program preda naprej) ali ključ `omrezje.posrednik` v nastavitvah.
Pri prestreganju TLS dodaj še `REQUESTS_CA_BUNDLE=/pot/do/podjetje-ca.pem` in
`NODE_EXTRA_CA_CERTS` za Chromium.

## Pot A: sistemska namestitev s systemd

Priporočena, kadar ima podjetje navaden strežnik.

```bash
git clone https://github.com/ttrampus/arhiv-letakov.git
cd arhiv-letakov
sudo ./namesti-streznik.sh --urnik "cet 06:00"
```

Skripta nič ne sprašuje, zato jo lahko poganja tudi Ansible. Naredi:

| | |
|---|---|
| `/opt/arhiv-letakov` | koda, `venv` in Chromium |
| `/etc/arhiv-letakov/nastavitve.yaml` | nastavitve, `root:arhiv-letakov 0640` |
| `/var/lib/arhiv-letakov` | arhiv, mesne kopije in `arhiv.db` |
| `/var/log/arhiv-letakov` | dnevniki (sami se obrezujejo, 5 × 2 MB) |
| uporabnik `arhiv-letakov` | sistemski, brez prijave |
| `/usr/local/bin/letaki` | ukaz, ki že ve za nastavitve in Chromium |
| `arhiv-letakov.timer` | zajem po urniku |

Enota teče utrjeno: `ProtectSystem=strict`, `ProtectHome`, `NoNewPrivileges`,
pisati sme samo v svoj arhiv in dnevnike.

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

## Pot B: Docker

```bash
docker build -t arhiv-letakov:latest .
docker compose run --rm letaki prenesi
```

Slika je okoli 2 GB, ker nosi Chromium in tesseract. Kjer je namesto Dockerja
Podman, delujeta ista slika in datoteka: `podman build` in `podman-compose`.

Zabojnik naredi en zajem in konča. Ponavljanje prevzame gostitelj — v
`streznik/` sta pripravljena `docker-arhiv-letakov.service` in `.timer`:

```bash
sudo cp streznik/docker-arhiv-letakov.* /etc/systemd/system/
sudo systemctl enable --now docker-arhiv-letakov.timer
```

Nastavitve so priklopljene iz `streznik/nastavitve.zabojnik.yaml`, arhiv in
dnevniki so imenovana nosilca. Zabojnik teče kot UID 10001, brez pravic in z
bralnim korenskim sistemom. `shm_size: 1gb` je nujen — Chromium prebije
privzetih 64 MB.

## Pot C: Kubernetes

```bash
kubectl create configmap arhiv-letakov-nastavitve \
    --from-file=nastavitve.yaml=streznik/nastavitve.zabojnik.yaml
kubectl apply -f streznik/kubernetes-cronjob.yaml
```

CronJob ob četrtkih ob 6:00 po ljubljanskem času, `concurrencyPolicy: Forbid`,
PVC 100 GB. Slika mora biti v registru gruče.

## Pot D: brez root pravic

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

- **Windows strežniki niso podprti.** Program predvideva Linux (`bash`, poti,
  systemd ali cron). Na Windows gre skozi WSL2 ali zabojnik.
- **Air-gapped omrežja ne pridejo v poštev.** Program mora do strani trgovin;
  brez odhodnega dostopa nima kaj prenašati.
- **Alpine (musl) ni preizkušen**, ker Playwrightov Chromium tam uradno ni
  podprt. Slika stoji na Debianu prav zato.
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

## Ko kaj ne dela

| Znak | Kaj je narobe |
|---|---|
| `Nastavitev ni: ...` | brez terminala program ne ugiba; naredi `/etc/arhiv-letakov/nastavitve.yaml` |
| samo Hofer in Eurospin odpovesta | Chromium; poženi `venv/bin/playwright install-deps chromium` |
| Lidlovi letaki obdržijo vse strani | manjka `tesseract-ocr-slv` |
| vse trgovine odpovejo naenkrat | omrežje, posrednik ali prestrezanje TLS |
| `database is locked` | dva zagona hkrati; enota `Type=oneshot` in zaklep to sicer preprečita |
| Chromium se sesuje v zabojniku | premajhen `/dev/shm`, nastavi `shm_size: 1gb` |

## Pravno

Program prenaša javno objavljene letake s spletnih strani trgovin. Preden ga
podjetje postavi v redno rabo, naj pogleda pogoje uporabe posamezne trgovine —
zlasti če bi kataloge objavljalo naprej ali iz njih delalo izdelke. Zajem je
namenoma počasen (2 sekundi med zahtevami) in se predstavi z navadnim
uporabniškim nizom brskalnika.
