from __future__ import annotations

from .osnova import BaseStore
from .eurospin import EurospinStore
from .hofer import HoferStore
from .leclerc import LeclercStore
from .lidl import LidlStore
from .mercator import MercatorStore
from .spar import SparStore
from .tus import TusStore

ALL_STORES: list[type[BaseStore]] = [
    MercatorStore,
    TusStore,
    SparStore,
    LeclercStore,
    LidlStore,
    HoferStore,
    EurospinStore,
]


def get_stores(names: list[str] | None = None) -> list[BaseStore]:
    if not names:
        return [cls() for cls in ALL_STORES]

    by_name = {cls.name: cls for cls in ALL_STORES}
    unknown = [n for n in names if n not in by_name]
    if unknown:
        raise SystemExit(
            f"Neznane trgovine: {', '.join(unknown)}. "
            f"Na voljo: {', '.join(sorted(by_name))}"
        )
    return [by_name[name]() for name in names]
