#!/usr/bin/env bash
# Namestitev na strežnik: sistemski uporabnik, koda v /opt, nastavitve v /etc,
# arhiv v /var/lib in systemd časovnik, ki zajema po urniku. Nič ne sprašuje,
# zato ga lahko poganja tudi Ansible. Znova ga lahko poženeš za nadgradnjo.
#
#   sudo ./namesti-streznik.sh --urnik "cet 06:00"
#
set -euo pipefail

MAPA=/opt/arhiv-letakov
UPORABNIK=arhiv-letakov
NASTAVITVE=/etc/arhiv-letakov/nastavitve.yaml
PODATKI=/var/lib/arhiv-letakov
DNEVNIKI=/var/log/arhiv-letakov
URNIK="cet 06:00"
PAKETI=1
CASOVNIK=1

while [ $# -gt 0 ]; do
    case "$1" in
        --mapa) MAPA="$2"; shift 2 ;;
        --uporabnik) UPORABNIK="$2"; shift 2 ;;
        --urnik) URNIK="$2"; shift 2 ;;
        --brez-paketov) PAKETI=0; shift ;;
        --brez-casovnika) CASOVNIK=0; shift ;;
        -h|--pomoc)
            sed -n '2,8p' "$0" | sed 's/^# \?//'
            echo
            echo "Možnosti:"
            echo "  --mapa POT            kam gre koda (privzeto $MAPA)"
            echo "  --uporabnik IME       sistemski uporabnik (privzeto $UPORABNIK)"
            echo "  --urnik \"cet 06:00\"   kdaj naj zajema (dnevno|tedensko|pon,cet HH:MM)"
            echo "  --brez-paketov        ne nameščaj sistemskih paketov"
            echo "  --brez-casovnika      samo namesti, časovnika ne vklopi"
            exit 0 ;;
        *) echo "neznana možnost: $1" >&2; exit 1 ;;
    esac
done

if [ "$(id -u)" -ne 0 ]; then
    echo "Poženi kot root: sudo $0 $*" >&2
    exit 1
fi

IZVOR="$(cd "$(dirname "$0")" && pwd)"
echo "==> Namestitev iz $IZVOR v $MAPA"

# sistemski paketi
if [ "$PAKETI" -eq 1 ]; then
    echo "==> Sistemski paketi"
    if command -v apt-get >/dev/null; then
        export DEBIAN_FRONTEND=noninteractive
        apt-get update -qq
        apt-get install -y -qq python3-venv python3-pip \
            tesseract-ocr tesseract-ocr-slv poppler-utils ca-certificates
    elif command -v dnf >/dev/null; then
        dnf install -y -q python3-pip tesseract tesseract-langpack-slv poppler-utils
    elif command -v zypper >/dev/null; then
        zypper --non-interactive install python3 python3-pip tesseract-ocr \
            tesseract-ocr-traineddata-slovenian poppler-tools
    elif command -v pacman >/dev/null; then
        pacman -Sy --needed --noconfirm python tesseract tesseract-data-slv poppler
    else
        echo "Neznan upravitelj paketov (znam apt, dnf, zypper, pacman)."
        echo "Namesti ročno python3-venv, tesseract s slovenskim jezikom in"
        echo "poppler, nato poženi to znova z --brez-paketov."
        exit 1
    fi
fi

# uporabnik in mape
echo "==> Uporabnik $UPORABNIK in mape"
if ! id -u "$UPORABNIK" >/dev/null 2>&1; then
    # Pot do nologin se med distribucijami razlikuje.
    LUPINA=/usr/sbin/nologin
    [ -x "$LUPINA" ] || LUPINA=/usr/bin/nologin
    [ -x "$LUPINA" ] || LUPINA=/bin/false
    useradd --system --home-dir "$PODATKI" --create-home \
            --shell "$LUPINA" "$UPORABNIK"
fi

install -d -m 755 "$MAPA"
install -d -m 750 -o "$UPORABNIK" -g "$UPORABNIK" "$PODATKI" "$DNEVNIKI"
# Mapo mora storitveni uporabnik smeti odpreti, sicer datoteke v njej ne
# prebere, pa čeprav jo sme brati.
install -d -m 750 -o root -g "$UPORABNIK" "$(dirname "$NASTAVITVE")"

# koda
echo "==> Koda"
if command -v rsync >/dev/null; then
    rsync -a --delete \
          --exclude venv/ --exclude arhiv/ --exclude arhiv-meso/ \
          --exclude dnevniki/ --exclude brskalniki/ --exclude .git/ \
          --exclude __pycache__/ --exclude 'nastavitve.yaml' --exclude '*.db' \
          "$IZVOR"/ "$MAPA"/
else
    for item in jedro trgovine testi letaki letaki.py requirements.txt \
                nastavitve.primer.yaml streznik README.md LICENSE; do
        if [ -e "$IZVOR/$item" ]; then cp -a "$IZVOR/$item" "$MAPA"/; fi
    done
fi
chown -R root:root "$MAPA"

# python okolje
echo "==> Virtualno okolje in odvisnosti"
[ -x "$MAPA/venv/bin/python" ] || python3 -m venv "$MAPA/venv"
"$MAPA/venv/bin/pip" install --quiet --upgrade pip
"$MAPA/venv/bin/pip" install --quiet -r "$MAPA/requirements.txt"

# Brskalnik gre v mapo s kodo; v /root/.cache ga storitveni uporabnik ne najde.
echo "==> Chromium brez okna"
export PLAYWRIGHT_BROWSERS_PATH="$MAPA/brskalniki"
"$MAPA/venv/bin/playwright" install chromium
"$MAPA/venv/bin/playwright" install-deps chromium || \
    echo "opozorilo: sistemskih knjižnic za Chromium ni bilo mogoče namestiti"
chmod -R a+rX "$MAPA/brskalniki"

# nastavitve
if [ -f "$NASTAVITVE" ]; then
    echo "==> Nastavitve že so, puščam jih pri miru: $NASTAVITVE"
else
    echo "==> Pišem $NASTAVITVE"
    URNIK="$URNIK" PODATKI="$PODATKI" DNEVNIKI="$DNEVNIKI" \
    "$MAPA/venv/bin/python" - "$MAPA/nastavitve.primer.yaml" "$NASTAVITVE" <<'PY'
import os, sys, yaml
from pathlib import Path

primer, cilj = Path(sys.argv[1]), Path(sys.argv[2])
cfg = yaml.safe_load(primer.read_text(encoding="utf-8"))

podatki = os.environ["PODATKI"]
cfg["mapa_arhiva"] = f"{podatki}/arhiv"
cfg["baza"] = f"{podatki}/arhiv.db"
cfg["mapa_dnevnikov"] = os.environ["DNEVNIKI"]
cfg["urnik"] = os.environ["URNIK"]
cfg.setdefault("mesne_strani", {})["mapa"] = f"{podatki}/arhiv-meso"
cfg.setdefault("brskalnik", {})["brez_peskovnika"] = True

cilj.write_text(yaml.safe_dump(cfg, allow_unicode=True, sort_keys=False), encoding="utf-8")
PY
    # V nastavitvah je lahko webhook, zato jih vidi samo storitveni uporabnik.
    chown root:"$UPORABNIK" "$NASTAVITVE"
    chmod 640 "$NASTAVITVE"
fi

# ukaz letaki
cat > /usr/local/bin/letaki <<UKAZ
#!/bin/sh
export PLAYWRIGHT_BROWSERS_PATH=$MAPA/brskalniki
exec $MAPA/venv/bin/python $MAPA/letaki.py --nastavitve $NASTAVITVE "\$@"
UKAZ
chmod 755 /usr/local/bin/letaki

# systemd, oziroma cron tam, kjer systemd ni
if ! command -v systemctl >/dev/null; then
    if [ "$CASOVNIK" -eq 1 ] && [ -d /etc/cron.d ]; then
        echo "==> systemd ni na voljo, urnik dam v cron"
        {
            echo "# arhiv-letakov: zajem trgovinskih letakov ($URNIK)"
            echo "# Naredil namesti-streznik.sh; ureja se v $NASTAVITVE."
            echo 'MAILTO=""'
            echo "PATH=/usr/local/bin:/usr/bin:/bin"
            MAPA="$MAPA" URNIK="$URNIK" "$MAPA/venv/bin/python" -c '
import os
import sys
sys.path.insert(0, os.environ["MAPA"])
from jedro import urnik
for vrstica in urnik.to_cron(os.environ["URNIK"]):
    print(vrstica)
' | while read -r vrstica; do
                echo "$vrstica $UPORABNIK letaki prenesi >> $DNEVNIKI/cron.log 2>&1"
            done
        } > /etc/cron.d/arhiv-letakov
        chmod 644 /etc/cron.d/arhiv-letakov
        echo "    /etc/cron.d/arhiv-letakov"
    else
        echo "==> ni ne systemd ne cron, časovnika ne nameščam"
    fi
    echo
    echo "Nameščeno."
    echo "  koda        $MAPA"
    echo "  nastavitve  $NASTAVITVE"
    echo "  arhiv       $PODATKI"
    echo "  urnik       $URNIK"
    echo
    echo "Ročni zajem:  sudo -u $UPORABNIK letaki prenesi"
    echo "Stanje:       letaki stanje --json"
    exit 0
fi

echo "==> systemd"
ONCALENDAR=$(MAPA="$MAPA" URNIK="$URNIK" "$MAPA/venv/bin/python" -c '
import os
import sys
sys.path.insert(0, os.environ["MAPA"])
from jedro import urnik
print(chr(10).join("OnCalendar=" + e for e in urnik.to_oncalendar(os.environ["URNIK"])))
')

sed -e "s|@MAPA@|$MAPA|g" -e "s|@UPORABNIK@|$UPORABNIK|g" \
    "$MAPA/streznik/arhiv-letakov.service" > /etc/systemd/system/arhiv-letakov.service
ONCALENDAR="$ONCALENDAR" URNIK="$URNIK" python3 - \
        "$MAPA/streznik/arhiv-letakov.timer" <<'PY' > /etc/systemd/system/arhiv-letakov.timer
import os
import sys
from pathlib import Path

print(Path(sys.argv[1]).read_text(encoding="utf-8")
      .replace("@ONCALENDAR@", os.environ["ONCALENDAR"])
      .replace("@URNIK@", os.environ["URNIK"]), end="")
PY

# ReadWritePaths mora ustrezati temu, kamor res pišemo.
if [ "$PODATKI" != /var/lib/arhiv-letakov ] || [ "$DNEVNIKI" != /var/log/arhiv-letakov ]; then
    sed -i "s|^ReadWritePaths=.*|ReadWritePaths=$PODATKI $DNEVNIKI|" \
        /etc/systemd/system/arhiv-letakov.service
fi

systemctl daemon-reload
if [ "$CASOVNIK" -eq 1 ]; then
    systemctl enable --now arhiv-letakov.timer
fi

echo
echo "Nameščeno."
echo "  koda        $MAPA"
echo "  nastavitve  $NASTAVITVE"
echo "  arhiv       $PODATKI"
echo "  dnevniki    $DNEVNIKI  (in journalctl -u arhiv-letakov)"
echo "  urnik       $URNIK"
echo
echo "Prvi zajem zdaj:   systemctl start arhiv-letakov.service"
echo "Naslednji zagon:   systemctl list-timers arhiv-letakov.timer"
echo "Stanje za nadzor:  letaki stanje --json"
echo "Ročni zajem:       sudo -u $UPORABNIK letaki prenesi"
