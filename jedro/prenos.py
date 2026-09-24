from __future__ import annotations

import hashlib
import logging
import time
from pathlib import Path

from .povezava import Fetchers, OmejitevPresezena
from .modeli import Magazine

log = logging.getLogger(__name__)

PDF_MAGIC = b"%PDF"
KOS = 256 * 1024
# Stran A4 pri 300 dpi ima ~9 milijonov točk.
NAJVEC_TOCK_SLIKE = 25_000_000


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
                   store: str | None = None) -> tuple[Path, str, int]:
    destination.parent.mkdir(parents=True, exist_ok=True)
    store = store or magazine.store
    if magazine.file_url:
        return _download_pdf(magazine, fetchers, destination, store)
    return _download_images_as_pdf(magazine, fetchers, destination, store)


def _prenesi_v_datoteko(fetchers, url, store, path: Path, limit_bytes: int,
                        digest=None, magic: bytes | None = None) -> int:
    """Pretočno shrani odgovor do meje velikosti in časa; magic preveri prve bajte."""
    response = fetchers.http.get(url, store=store, stream=True)
    try:
        size = 0
        with path.open("wb") as handle:
            for chunk in fetchers.http.kosi(response, limit_bytes,
                                            fetchers.config.download_timeout, url):
                if size == 0 and magic is not None and not chunk.startswith(magic):
                    raise DownloadError(f"ni PDF: {url}")
                size += len(chunk)
                handle.write(chunk)
                if digest is not None:
                    digest.update(chunk)
        return size
    except OmejitevPresezena as exc:
        raise DownloadError(str(exc)) from exc
    finally:
        response.close()


def _download_pdf(magazine, fetchers, destination, store):
    part = destination.with_suffix(destination.suffix + ".part")
    digest = hashlib.sha256()
    limit = fetchers.config.max_pdf_mb * 1_000_000

    try:
        size = _prenesi_v_datoteko(fetchers, magazine.file_url, store, part, limit, digest,
                                   magic=PDF_MAGIC)
    except Exception:
        part.unlink(missing_ok=True)
        raise

    if size == 0:
        part.unlink(missing_ok=True)
        raise DownloadError(f"prazen odgovor z {magazine.file_url}")
    with part.open("rb") as handle:
        if handle.read(4) != PDF_MAGIC:
            part.unlink(missing_ok=True)
            raise DownloadError(f"ni PDF: {magazine.file_url}")

    _zamenjaj(part, destination)
    return destination, digest.hexdigest(), size


def _download_images_as_pdf(magazine, fetchers, destination, store):
    try:
        import img2pdf
    except ImportError as exc:
        raise DownloadError("za letake iz slik je potreben img2pdf") from exc

    from PIL import Image

    Image.MAX_IMAGE_PIXELS = NAJVEC_TOCK_SLIKE
    cfg = fetchers.config
    image_dir = destination.with_suffix("")
    image_dir.mkdir(parents=True, exist_ok=True)

    urls = magazine.image_urls[:cfg.max_images]
    if len(magazine.image_urls) > cfg.max_images:
        log.warning("  letak ima %s strani, obdelam prvih %s",
                    len(magazine.image_urls), cfg.max_images)

    saved = []
    skupaj = 0
    limit_slike = cfg.max_image_mb * 1_000_000
    limit_letaka = cfg.max_flyer_mb * 1_000_000
    for index, url in enumerate(urls, start=1):
        suffix = next((s for s in (".jpg", ".jpeg", ".png", ".webp") if s in url.lower()), ".jpg")
        image_path = image_dir / f"{index:03d}{suffix}"
        try:
            skupaj += _prenesi_v_datoteko(fetchers, url, store, image_path, limit_slike)
            saved.append(image_path)
        except Exception as exc:
            image_path.unlink(missing_ok=True)
            log.warning("  stran %s ni uspela (%s)", index, exc)
        if skupaj > limit_letaka:
            log.warning("  letak je presegel %s MB, nehal sem pri strani %s",
                        cfg.max_flyer_mb, index)
            break

    if not saved:
        raise DownloadError("nobene slike strani ni bilo mogoče prenesti")

    pages = [str(p) for p in saved if p.suffix != ".webp"]
    if len(pages) < len(saved):
        pages = [str(p) for p in _convert_webp(saved)]

    part = destination.with_suffix(destination.suffix + ".part")
    try:
        with part.open("wb") as handle:
            img2pdf.convert(pages, outputstream=handle)
    except Exception:
        part.unlink(missing_ok=True)
        raise
    finally:
        for image in image_dir.iterdir():
            image.unlink(missing_ok=True)
        image_dir.rmdir()
    _zamenjaj(part, destination)

    digest = hashlib.sha256()
    size = 0
    with destination.open("rb") as handle:
        for chunk in iter(lambda: handle.read(KOS), b""):
            digest.update(chunk)
            size += len(chunk)
    log.info("  sestavljenih strani v PDF: %s", len(pages))
    return destination, digest.hexdigest(), size


def _zamenjaj(part: Path, destination: Path, poskusi: int = 3) -> None:
    """replace() s ponovnimi poskusi za kratke izpade delnice SMB."""
    for poskus in range(1, poskusi + 1):
        try:
            part.replace(destination)
            return
        except OSError as exc:
            if poskus == poskusi:
                raise DownloadError(
                    f"{destination} ni bilo mogoče zapisati ({exc}); "
                    f"prenos ostane v {part.name}") from exc
            log.warning("  zapis na %s ni uspel (%s), poskus %s od %s",
                        destination.parent, exc, poskus, poskusi)
            time.sleep(2 * poskus)


def _convert_webp(images: list[Path]) -> list[Path]:
    from PIL import Image

    result = []
    for path in images:
        if path.suffix != ".webp":
            result.append(path)
            continue
        jpeg_path = path.with_suffix(".jpg")
        with Image.open(path) as image:
            if image.width * image.height > NAJVEC_TOCK_SLIKE:
                raise DownloadError(f"slika {path.name} je prevelika "
                                    f"({image.width}x{image.height})")
            image.convert("RGB").save(jpeg_path, "JPEG", quality=92)
        result.append(jpeg_path)
    return result
