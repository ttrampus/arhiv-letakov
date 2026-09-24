"""Poverilnice posrednika ne smejo priti v dnevnik."""

import logging
import tempfile
import unittest
import unittest.mock
from pathlib import Path

from jedro.nastavitve import Config
from jedro.povezava import HttpFetcher

POSREDNIK = "http://sluzbeni:zelo-skrivno@proxy.podjetje.si:8080"


class Posrednik(unittest.TestCase):
    def nastavitve(self, **kwargs) -> Config:
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        return Config(root=root, config_path=root / "n.yaml", archive_dir=root / "a",
                      meat_dir=root / "m", db_path=root / "b.db", log_dir=root / "d",
                      **kwargs)

    def test_geslo_ne_pride_v_dnevnik(self):
        cfg = self.nastavitve(proxy=POSREDNIK)
        with self.assertLogs("jedro.povezava", logging.INFO) as zapis:
            HttpFetcher(cfg).close()
        izpis = "\n".join(zapis.output)
        self.assertNotIn("zelo-skrivno", izpis)
        self.assertNotIn("sluzbeni", izpis)
        self.assertIn("proxy.podjetje.si:8080", izpis)

    def test_brez_posrednika_ni_izpisa(self):
        cfg = self.nastavitve()
        logger = logging.getLogger("jedro.povezava")
        with unittest.mock.patch.object(logger, "info") as info:
            HttpFetcher(cfg).close()
        info.assert_not_called()


if __name__ == "__main__":
    import unittest.mock
    unittest.main()
