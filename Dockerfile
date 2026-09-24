# Zabojnik naredi en zajem in konča; ponavlja ga zunanji urnik, zato v njem
# ni demona.
FROM python:3.12-slim-bookworm

ENV PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    ARHIV_NASTAVITVE=/etc/arhiv-letakov/nastavitve.yaml \
    TZ=Europe/Ljubljana

# tesseract bere Lidlove letake, ki so slike.
RUN apt-get update \
 && apt-get install -y --no-install-recommends \
      tesseract-ocr tesseract-ocr-slv poppler-utils ca-certificates tzdata \
 && rm -rf /var/lib/apt/lists/*

WORKDIR /opt/arhiv-letakov

COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

COPY . .

RUN useradd --system --uid 10001 --home-dir /var/lib/arhiv-letakov arhiv \
 && mkdir -p /var/lib/arhiv-letakov /var/log/arhiv-letakov /etc/arhiv-letakov \
 && chown -R arhiv /var/lib/arhiv-letakov /var/log/arhiv-letakov

USER arhiv

ENTRYPOINT ["python", "letaki.py"]
CMD ["prenesi"]
