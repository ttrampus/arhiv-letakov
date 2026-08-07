import sqlite3
import tempfile
import unittest
from pathlib import Path

from jedro import obvestila
from jedro.baza import Archive
from jedro.nastavitve import Config


def nastavitve(**kwargs):
    return Config(root=Path("/tmp"), config_path=Path("/tmp/nastavitve.yaml"),
                  archive_dir=Path("/tmp/arhiv"), meat_dir=Path("/tmp/meso"),
                  db_path=Path("/tmp/arhiv.db"), log_dir=Path("/tmp/dnevniki"),
                  **kwargs)


class Sporocilo(unittest.TestCase):
    def vrstice(self, **stolpci):
        conn = sqlite3.connect(":memory:")
        conn.row_factory = sqlite3.Row
        conn.execute("CREATE TABLE h (store TEXT, last_ok TEXT, failures INT, reason TEXT)")
        conn.execute("INSERT INTO h VALUES (?, ?, ?, ?)",
                     (stolpci["store"], stolpci["last_ok"], stolpci["failures"],
                      stolpci["reason"]))
        return conn.execute("SELECT * FROM h").fetchall()

    def test_navede_trgovino_in_stevilo(self):
        text = obvestila.message(self.vrstice(
            store="spar", last_ok="2026-08-01T06:00:00+00:00", failures=3,
            reason="nič najdenega"))
        self.assertIn("spar: 3 zagonov zapored", text)
        self.assertIn("nič najdenega", text)
        self.assertIn("2026-08-01", text)

    def test_trgovina_brez_uspeha(self):
        text = obvestila.message(self.vrstice(
            store="lidl", last_ok=None, failures=5, reason=None))
        self.assertIn("nikoli", text)
        self.assertIn("neznano", text)


class Posiljanje(unittest.TestCase):
    def test_ukaz_dobi_sporocilo_na_vhod(self):
        with tempfile.TemporaryDirectory() as temp:
            target = Path(temp) / "obvestilo.txt"
            obvestila.send(nastavitve(notify_command=f"cat > {target}"), "pozdrav")
            self.assertEqual(target.read_text(), "pozdrav")

    def test_brez_nastavitev_ne_naredi_nicesar(self):
        obvestila.send(nastavitve(), "pozdrav")

    def test_neuspel_ukaz_ne_podre_zagona(self):
        with self.assertLogs("jedro.obvestila", "ERROR") as zapis:
            obvestila.send(nastavitve(notify_command="exit 3"), "pozdrav")
        self.assertIn("vrnil 3", zapis.output[0])
