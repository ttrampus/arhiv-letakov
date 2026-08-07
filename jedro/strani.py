from __future__ import annotations

import logging
import shutil
import subprocess
import tempfile
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from .meso import DEFAULT_PATTERN, page_has_meat

log = logging.getLogger(__name__)

MIN_TEXT_CHARS = 40
OCR_DPI = 150


class PageFilterResult:
    def __init__(self, total, kept, ocr_pages, unreadable):
        self.total = total
        self.kept = kept
        self.ocr_pages = ocr_pages
        self.unreadable = unreadable

    def __str__(self) -> str:
        extra = []
        if self.ocr_pages:
            extra.append(f"{self.ocr_pages} z OCR")
        if self.unreadable:
            extra.append(f"{len(self.unreadable)} neberljivih obdržanih")
        return f"{len(self.kept)}/{self.total} strani" + (f" ({', '.join(extra)})" if extra else "")


def ocr_available() -> bool:
    return bool(shutil.which("tesseract") and shutil.which("pdftoppm"))


def filter_pdf(source: Path, destination: Path, *, use_ocr: bool = True,
               pattern=DEFAULT_PATTERN) -> PageFilterResult:
    reader = PdfReader(str(source))
    texts = [page.extract_text() or "" for page in reader.pages]

    missing = [i for i, t in enumerate(texts) if len(t.strip()) < MIN_TEXT_CHARS]
    ocr_count = 0
    if missing and use_ocr:
        if ocr_available():
            log.info("  OCR: toliko strani brez besedilne plasti: %s", len(missing))
            for index, text in _ocr_pages(source, missing).items():
                texts[index] = text
                ocr_count += 1
        else:
            log.warning("  toliko strani je brez besedilne plasti, tesseract pa manjka: %s, "
                        "zato jih obdržimo cele (glej README)", len(missing))

    kept, unreadable = [], []
    for index, text in enumerate(texts):
        if len(text.strip()) < MIN_TEXT_CHARS:
            unreadable.append(index)
            kept.append(index)
        elif page_has_meat(text, pattern)[0]:
            kept.append(index)

    if not kept:
        log.info("  v %s ni mesnih strani", source.name)
        destination.unlink(missing_ok=True)
        return PageFilterResult(len(reader.pages), [], ocr_count, unreadable)

    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for index in kept:
        writer.add_page(reader.pages[index])
    part = destination.with_suffix(destination.suffix + ".part")
    with part.open("wb") as handle:
        writer.write(handle)
    part.replace(destination)

    return PageFilterResult(len(reader.pages), kept, ocr_count, unreadable)


def _ocr_pages(source: Path, indices: list[int]) -> dict[int, str]:
    results = {}
    langs = _ocr_languages()
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        for index in indices:
            page = index + 1
            stem = tmp_path / f"page-{page}"
            try:
                subprocess.run(
                    ["pdftoppm", "-f", str(page), "-l", str(page), "-r", str(OCR_DPI),
                     "-gray", "-png", str(source), str(stem)],
                    check=True, capture_output=True, timeout=180)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                log.warning("  strani %s ni bilo mogoče izrisati (%s)", page, exc)
                continue

            images = sorted(tmp_path.glob(f"page-{page}*.png"))
            if not images:
                continue
            try:
                done = subprocess.run(["tesseract", str(images[0]), "stdout", "-l", langs],
                                      check=True, capture_output=True, timeout=180)
                results[index] = done.stdout.decode("utf-8", "ignore")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired) as exc:
                log.warning("  OCR na strani %s ni uspel (%s)", page, exc)
            finally:
                for image in images:
                    image.unlink(missing_ok=True)
    return results


def _ocr_languages() -> str:
    try:
        listed = subprocess.run(["tesseract", "--list-langs"], capture_output=True,
                                timeout=30).stdout.decode("utf-8", "ignore")
    except Exception:
        return "eng"
    return "slv+eng" if "slv" in listed.split() else "eng"
