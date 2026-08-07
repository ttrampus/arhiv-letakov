from __future__ import annotations

import hashlib
import logging
from pathlib import Path

from .povezava import Fetchers
from .modeli import Magazine

log = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF"


class DownloadError(RuntimeError):
    pass


def target_path(archive_dir: Path, magazine: Magazine, taken: set[str] | None = None) -> Path:
    directory = archive_dir / magazine.store / str(magazine.year())
    path = directory / magazine.filename()
    if taken is not None and str(path) in taken:
        digest = hashlib.sha256(magazine.dedupe_key.encode()).hexdigest()[:6]
        path = directory / f"{path.stem}-{digest}{path.suffix}"
    return path


def fetch_magazine(magazine: Magazine, fetchers: Fetchers, destination: Path,
                   use_browser: bool = False) -> tuple[Path, str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    if magazine.file_url:
        return _download_pdf(magazine, fetchers, destination, use_browser)
    return _download_images_as_pdf(magazine, fetchers, destination, use_browser)


def _download_pdf(magazine, fetchers, destination, use_browser):
    part = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    size = 0

    if use_browser:
        data = fetchers.browser.download(magazine.file_url, referer=magazine.source_url)
        part.write_bytes(data)
        digest.update(data)
        size = len(data)
    else:
        response = fetchers.http.get(magazine.file_url, stream=True)
        with part.open("wb") as handle:
            for chunk in response.iter_content(chunk_size=256 * 1024):
                if chunk:
                    handle.write(chunk)
                    digest.update(chunk)
                    size += len(chunk)

    if size == 0:
        part.unlink(missing_ok=True)
        raise DownloadError(f"prazen odgovor z {magazine.file_url}")
    with part.open("rb") as handle:
        if handle.read(4) != PDF_MAGIC:
            part.unlink(missing_ok=True)
            raise DownloadError(f"ni PDF: {magazine.file_url}")

    part.replace(destination)
    return destination, digest.hexdigest(), size


def _download_images_as_pdf(magazine, fetchers, destination, use_browser):
    try:
        import img2pdf
    except ImportError as exc:
        raise DownloadError("za letake iz slik je potreben img2pdf") from exc

    image_dir = destination.with_suffix("")
    image_dir.mkdir(parents=True, exist_ok=True)

    saved = []
    for index, url in enumerate(magazine.image_urls, start=1):
        suffix = next((s for s in (".jpg", ".jpeg", ".png", ".webp") if s in url.lower()), ".jpg")
        image_path = image_dir / f"{index:03d}{suffix}"
        try:
            if use_browser:
                image_path.write_bytes(fetchers.browser.download(url, referer=magazine.source_url))
            else:
                image_path.write_bytes(fetchers.http.get(url).content)
            saved.append(image_path)
        except Exception as exc:
            log.warning("  stran %s ni uspela (%s)", index, exc)

    if not saved:
        raise DownloadError("nobene slike strani ni bilo mogoče prenesti")

    pages = [str(p) for p in saved if p.suffix != ".webp"]
    if len(pages) < len(saved):
        pages = [str(p) for p in _convert_webp(saved)]

    part = destination.with_suffix(destination.suffix + ".part")
    part.write_bytes(img2pdf.convert(pages))
    part.replace(destination)

    data = destination.read_bytes()
    log.info("  sestavljenih strani v PDF: %s", len(pages))
    return destination, hashlib.sha256(data).hexdigest(), len(data)


def _convert_webp(images: list[Path]) -> list[Path]:
    from PIL import Image

    result = []
    for path in images:
        if path.suffix != ".webp":
            result.append(path)
            continue
        jpeg_path = path.with_suffix(".jpg")
        with Image.open(path) as image:
            image.convert("RGB").save(jpeg_path, "JPEG", quality=92)
        result.append(jpeg_path)
    return result
