#!/usr/bin/env bash
# Enkratna namestitev: virtualno okolje, odvisnosti, brskalnik brez okna in
# nato vodena nastavitev. Znova ga lahko poženeš kadar koli.
set -e
cd "$(dirname "$0")"

if ! command -v python3 >/dev/null; then
    echo "python3 ni nameščen. Namesti ga in poženi to znova."
    exit 1
fi

if [ ! -x venv/bin/python ]; then
    echo "Ustvarjam virtualno okolje ..."
    python3 -m venv venv
fi

echo "Nameščam odvisnosti ..."
venv/bin/pip install --quiet --upgrade pip
venv/bin/pip install --quiet -r requirements.txt

# Chromium je ~150 MB, zato ga prenesemo samo, kadar ga še ni.
if ! venv/bin/python -c 'from playwright.sync_api import sync_playwright
with sync_playwright() as p: p.chromium.launch().close()' >/dev/null 2>&1; then
    echo "Nameščam Chromium brez okna (potrebujeta ga Hofer in Eurospin) ..."
    venv/bin/playwright install chromium
fi

if ! command -v tesseract >/dev/null; then
    echo
    echo "Opomba: tesseract ni nameščen. Lidlovi katalogi so skenirane slike,"
    echo "zato njihovih strani brez njega ni mogoče izbrati po mesu (ostanejo cele)."
    echo "  Arch:   sudo pacman -S tesseract tesseract-data-slv poppler"
    echo "  Debian: sudo apt install tesseract-ocr tesseract-ocr-slv poppler-utils"
fi

chmod +x letaki

exec venv/bin/python letaki.py nastavitev
