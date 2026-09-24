"""Za teste, ki potrebujejo lokalni HTTP strežnik.

Pravila v jedro/naslovi.py lokalne naslove, gole IP in nestandardna vrata
upravičeno zavrnejo. Testni strežnik je vse troje, zato jih tu za čas testa
izklopimo. Da pravila sicer delujejo, preverjata test_naslovi in test_ip_povezave.
"""

import unittest.mock


def dovoli_lokalni_streznik(test: unittest.TestCase, vrata: int) -> None:
    zaplate = [
        unittest.mock.patch("jedro.naslovi.je_ip", return_value=False),
        unittest.mock.patch("jedro.naslovi.je_javen_ip", return_value=True),
        unittest.mock.patch.dict("jedro.naslovi._PRIVZETA_VRATA", {"http": vrata}),
    ]
    for zaplata in zaplate:
        zaplata.start()
        test.addCleanup(zaplata.stop)
