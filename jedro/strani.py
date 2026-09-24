from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from pypdf import PdfReader, PdfWriter

from .meso import DEFAULT_PATTERN, page_has_meat

log = logging.getLogger(__name__)

MIN_TEXT_CHARS = 40
# Stran letaka ima nekaj tisoč znakov; več je znak pokvarjenega PDF.
NAJVEC_ZNAKOV_STRANI = 200_000
OCR_DPI = 150

PRIVZETO_NAJVEC_STRANI = 300
PRIVZETI_PRORACUN_S = 900
PRIVZETI_CAS_STRANI_S = 60

# Običajne namestitve na Windows, ki pogosto niso v PATH.
WINDOWS_POTI = (
    r"C:\Program Files\Tesseract-OCR",
    r"C:\Program Files (x86)\Tesseract-OCR",
    r"C:\Program Files\poppler\bin",
)


class PrevelikPdf(RuntimeError):
    """PDF ima več strani, kot jih smemo obdelati."""


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


def _najdi(program: str) -> str | None:
    """Program v PATH, ob .exe ali na običajnih Windows poteh."""
    found = shutil.which(program)
    if found:
        return found
    kandidati = [Path(sys.executable).resolve().parent]
    if os.name == "nt":
        kandidati += [Path(p) for p in WINDOWS_POTI]
    for mapa in kandidati:
        found = shutil.which(program, path=str(mapa))
        if found:
            return found
    return None


def ocr_available() -> bool:
    return bool(_najdi("tesseract") and _najdi("pdftoppm"))


def filter_pdf(source: Path, destination: Path, *, use_ocr: bool = True,
               pattern=DEFAULT_PATTERN, max_pages: int = PRIVZETO_NAJVEC_STRANI,
               budget_s: int = PRIVZETI_PRORACUN_S,
               page_timeout_s: int = PRIVZETI_CAS_STRANI_S,
               zacasna_mapa: str | None = None) -> PageFilterResult:
    """Iz letaka naredi kopijo samo z mesnimi stranmi, v okviru meje strani in časa."""
    reader = PdfReader(str(source))
    total = len(reader.pages)
    if total > max_pages:
        raise PrevelikPdf(
            f"{source.name} ima {total} strani, meja je {max_pages}")

    rok = time.monotonic() + budget_s
    texts = []
    for index, page in enumerate(reader.pages):
        if time.monotonic() > rok:
            log.warning("  branje besedila je poteklo pri strani %s od %s",
                        index + 1, total)
            texts.extend([""] * (total - index))
            break
        try:
            texts.append(page.extract_text() or "")
        except Exception as exc:
            log.warning("  strani %s ni bilo mogoče prebrati (%s)", index + 1, exc)
            texts.append("")

    missing = [i for i, t in enumerate(texts) if len(t.strip()) < MIN_TEXT_CHARS]
    ocr_count = 0
    if missing and use_ocr:
        if ocr_available():
            log.info("  OCR: toliko strani brez besedilne plasti: %s", len(missing))
            for index, text in _ocr_pages(source, missing, rok, page_timeout_s,
                                          zacasna_mapa).items():
                texts[index] = text
                ocr_count += 1
        else:
            log.warning("  toliko strani je brez besedilne plasti, tesseract pa manjka: %s, "
                        "zato jih obdržimo cele (glej README)", len(missing))

    kept, unreadable = [], []
    texts = [t[:NAJVEC_ZNAKOV_STRANI] for t in texts]
    for index, text in enumerate(texts):
        if len(text.strip()) < MIN_TEXT_CHARS:
            unreadable.append(index)
            kept.append(index)
        elif page_has_meat(text, pattern)[0]:
            kept.append(index)

    if not kept:
        log.info("  v %s ni mesnih strani", source.name)
        destination.unlink(missing_ok=True)
        return PageFilterResult(total, [], ocr_count, unreadable)

    destination.parent.mkdir(parents=True, exist_ok=True)
    writer = PdfWriter()
    for index in kept:
        writer.add_page(reader.pages[index])
    part = destination.with_suffix(destination.suffix + ".part")
    with part.open("wb") as handle:
        writer.write(handle)
    part.replace(destination)

    return PageFilterResult(total, kept, ocr_count, unreadable)


def _ocr_pages(source: Path, indices: list[int], rok: float,
               page_timeout_s: int, zacasna_mapa: str | None = None) -> dict[int, str]:
    results = {}
    langs = _ocr_languages()
    pdftoppm = _najdi("pdftoppm")
    tesseract = _najdi("tesseract")
    # zacasna_mapa je od starša, ki jo pobriše tudi, ko ta proces ubije.
    with tempfile.TemporaryDirectory(dir=zacasna_mapa) as tmp:
        tmp_path = Path(tmp)
        for index in indices:
            if time.monotonic() > rok:
                log.warning("  OCR je porabil ves čas, ustavljam pri %s obdelanih",
                            len(results))
                break
            page = index + 1
            stem = tmp_path / f"page-{page}"
            try:
                subprocess.run(
                    [pdftoppm, "-f", str(page), "-l", str(page), "-r", str(OCR_DPI),
                     "-gray", "-png", str(source), str(stem)],
                    check=True, capture_output=True, timeout=page_timeout_s)
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
                log.warning("  strani %s ni bilo mogoče izrisati (%s)", page, exc)
                continue

            images = sorted(tmp_path.glob(f"page-{page}*.png"))
            if not images:
                continue
            try:
                done = subprocess.run([tesseract, str(images[0]), "stdout", "-l", langs],
                                      check=True, capture_output=True,
                                      timeout=page_timeout_s)
                results[index] = done.stdout.decode("utf-8", "ignore")
            except (subprocess.CalledProcessError, subprocess.TimeoutExpired, OSError) as exc:
                log.warning("  OCR na strani %s ni uspel (%s)", page, exc)
            finally:
                for image in images:
                    image.unlink(missing_ok=True)
    return results


def _ocr_languages() -> str:
    try:
        listed = subprocess.run([_najdi("tesseract"), "--list-langs"], capture_output=True,
                                timeout=30).stdout.decode("utf-8", "ignore")
    except Exception:
        return "eng"
    return "slv+eng" if "slv" in listed.split() else "eng"


# Ena sama pokvarjena stran lahko pypdf zatakne ali mu požre pomnilnik, česar
# v istem procesu ni mogoče prekiniti. Zato filter_pdf teče v otroškem procesu.

class CasPotekel(RuntimeError):
    """Obdelava PDF je presegla trdi rok in je bila prekinjena."""


class _ZbiralnikZapisov(logging.Handler):
    def __init__(self):
        super().__init__()
        self.zapisi: list[tuple[int, str]] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.zapisi.append((record.levelno, record.getMessage()))


def _omeji_pomnilnik(mb: int | None) -> None:
    """Meja pomnilnika za ta proces in njegove otroke (RLIMIT_AS ali Job Object)."""
    if os.name == "nt":
        _windows_job(mb)
        return
    # Lastna skupina procesov, da starš ubije tudi pdftoppm in tesseract.
    try:
        os.setsid()
    except OSError:
        pass
    if not mb:
        return
    import resource
    meja = mb * 1024 * 1024
    resource.setrlimit(resource.RLIMIT_AS, (meja, meja))


def _windows_job(mb: int | None):
    """Job Object z mejo pomnilnika in KILL_ON_JOB_CLOSE; ob napaki teče brez meje."""
    try:
        import ctypes
        from ctypes import wintypes

        class IO_COUNTERS(ctypes.Structure):
            _fields_ = [(ime, ctypes.c_ulonglong) for ime in (
                "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
                "ReadTransferCount", "WriteTransferCount", "OtherTransferCount")]

        class BASIC_LIMIT(ctypes.Structure):
            _fields_ = [("PerProcessUserTimeLimit", ctypes.c_int64),
                        ("PerJobUserTimeLimit", ctypes.c_int64),
                        ("LimitFlags", wintypes.DWORD),
                        ("MinimumWorkingSetSize", ctypes.c_size_t),
                        ("MaximumWorkingSetSize", ctypes.c_size_t),
                        ("ActiveProcessLimit", wintypes.DWORD),
                        ("Affinity", ctypes.c_size_t),
                        ("PriorityClass", wintypes.DWORD),
                        ("SchedulingClass", wintypes.DWORD)]

        class EXTENDED_LIMIT(ctypes.Structure):
            _fields_ = [("BasicLimitInformation", BASIC_LIMIT),
                        ("IoInfo", IO_COUNTERS),
                        ("ProcessMemoryLimit", ctypes.c_size_t),
                        ("JobMemoryLimit", ctypes.c_size_t),
                        ("PeakProcessMemoryUsed", ctypes.c_size_t),
                        ("PeakJobMemoryUsed", ctypes.c_size_t)]

        JOB_MEMORY = 0x0200
        KILL_ON_JOB_CLOSE = 0x2000
        EXTENDED_LIMIT_INFORMATION = 9

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.CreateJobObjectW.restype = wintypes.HANDLE
        kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, wintypes.LPCWSTR]
        kernel32.SetInformationJobObject.restype = wintypes.BOOL
        kernel32.SetInformationJobObject.argtypes = [
            wintypes.HANDLE, ctypes.c_int, ctypes.c_void_p, wintypes.DWORD]
        kernel32.AssignProcessToJobObject.restype = wintypes.BOOL
        kernel32.AssignProcessToJobObject.argtypes = [wintypes.HANDLE, wintypes.HANDLE]
        kernel32.GetCurrentProcess.restype = wintypes.HANDLE

        job = kernel32.CreateJobObjectW(None, None)
        if not job:
            raise OSError(ctypes.get_last_error(), "CreateJobObjectW")
        info = EXTENDED_LIMIT()
        info.BasicLimitInformation.LimitFlags = KILL_ON_JOB_CLOSE | (JOB_MEMORY if mb else 0)
        if mb:
            info.JobMemoryLimit = mb * 1024 * 1024
        if not kernel32.SetInformationJobObject(job, EXTENDED_LIMIT_INFORMATION,
                                                ctypes.byref(info), ctypes.sizeof(info)):
            raise OSError(ctypes.get_last_error(), "SetInformationJobObject")
        if not kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess()):
            raise OSError(ctypes.get_last_error(), "AssignProcessToJobObject")
        global _JOB
        _JOB = job  # ročaj ostane odprt, dokler proces živi
        return job
    except Exception as exc:
        log.warning("  meje pomnilnika ni bilo mogoče nastaviti (%s)", exc)
        return None


_JOB = None


def _otrok(povezava, source: str, destination: str, kwargs: dict,
           pomnilnik_mb: int | None) -> None:
    zbiralnik = _ZbiralnikZapisov()
    koren = logging.getLogger()
    koren.handlers[:] = [zbiralnik]
    koren.setLevel(logging.INFO)
    logging.getLogger("pypdf").setLevel(logging.ERROR)
    try:
        _omeji_pomnilnik(pomnilnik_mb)
        rezultat = filter_pdf(Path(source), Path(destination), **kwargs)
        povezava.send(("ok", rezultat, zbiralnik.zapisi))
    except PrevelikPdf as exc:
        povezava.send(("prevelik", str(exc), zbiralnik.zapisi))
    except MemoryError:
        povezava.send(("napaka", "zmanjkalo je pomnilnika", zbiralnik.zapisi))
    except Exception as exc:
        povezava.send(("napaka", f"{type(exc).__name__}: {exc}", zbiralnik.zapisi))
    finally:
        povezava.close()


def _ubij(proces) -> None:
    """Ubije otroka in vse, kar je zagnal."""
    if os.name != "nt":
        import signal
        try:
            os.killpg(proces.pid, signal.SIGKILL)
            return
        except (ProcessLookupError, PermissionError, OSError):
            pass
    proces.kill()


def filter_pdf_izolirano(source: Path, destination: Path, *, trdi_rok_s: float,
                         pomnilnik_mb: int | None = None, **kwargs) -> PageFilterResult:
    """filter_pdf v otroškem procesu, ki ga po trdi_rok_s ubijemo."""
    import multiprocessing

    zacasna = tempfile.mkdtemp(prefix="arhiv-letakov-pdf-")
    kwargs["zacasna_mapa"] = zacasna
    kontekst = multiprocessing.get_context("spawn")
    prejemnik, oddajnik = kontekst.Pipe(duplex=False)
    proces = kontekst.Process(
        target=_otrok, args=(oddajnik, str(source), str(destination), kwargs, pomnilnik_mb),
        daemon=True)
    proces.start()
    oddajnik.close()
    try:
        if not prejemnik.poll(trdi_rok_s):
            raise CasPotekel(f"{source.name}: obdelava je presegla {trdi_rok_s:.0f} s "
                             "in je bila prekinjena")
        try:
            stanje, vsebina, zapisi = prejemnik.recv()
        except EOFError:
            raise RuntimeError(f"{source.name}: obdelava se je sesula "
                               f"(izhodna koda {proces.exitcode})") from None
    finally:
        if proces.is_alive():
            _ubij(proces)
        proces.join(10)
        prejemnik.close()
        destination.with_suffix(destination.suffix + ".part").unlink(missing_ok=True)
        shutil.rmtree(zacasna, ignore_errors=True)

    for raven, sporocilo in zapisi:
        log.log(raven, "%s", sporocilo)
    if stanje == "ok":
        return vsebina
    if stanje == "prevelik":
        raise PrevelikPdf(vsebina)
    raise RuntimeError(vsebina)
