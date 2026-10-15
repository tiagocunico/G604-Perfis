import os
import tempfile
import unittest
from pathlib import Path

from g604 import config
from g604.transporte import ReceptorNaoEncontrado, achar_hidraw
from g604.vigia import Vigia, perfil_desejado

BASE = {"perfis": {"padrao": {"slot": 1, "nome": "Padrão"}, "vava": {"slot": 2, "nome": "Vava"}},
        "regras": [{"processo": "VALORANT-Win64-Shipping.exe", "perfil": "vava"}],
        "vigia": {"perfil_padrao": "padrao"}}


class TestConfig(unittest.TestCase):
    def test_perfis_toml_do_repositorio(self):
        cfg = config.carregar()
        self.assertEqual({k: p.slot for k, p in cfg.perfis.items()}, {"padrao": 1, "vava": 2})
        self.assertEqual(cfg.regras[0].processos, ["VALORANT-Win64-Shipping.exe"])
        self.assertEqual(cfg.perfil_padrao, "padrao")

    def test_arquivo_com_bom_e_invalido(self):
        with tempfile.TemporaryDirectory() as d:
            arq = Path(d, "perfis.toml")
            arq.write_bytes(b"\xef\xbb\xbf" + config.caminho_padrao().read_bytes())
            self.assertEqual(len(config.carregar(arq).perfis), 2)
            arq.write_text("[perfis\n")
            with self.assertRaises(config.ConfigInvalida):
                config.carregar(arq)

    def test_busca_por_chave_nome_ou_slot(self):
        cfg = config.de_dict(BASE)
        for alvo in ("vava", "Vava", "2", " VAVA "):
            self.assertEqual(cfg.perfil(alvo).slot, 2)
        with self.assertRaises(config.ConfigInvalida):
            cfg.perfil("csgo")

    def test_invalidas(self):
        for dados in ({"perfis": {}},
                      {"perfis": {"a": {"nome": "sem slot"}}},
                      {"perfis": {"a": {"slot": 1}, "b": {"slot": 1}}},
                      {**BASE, "regras": [{"processo": "x.exe", "perfil": "naoexiste"}]},
                      {**BASE, "regras": [{"perfil": "vava"}]},
                      {**BASE, "vigia": {"perfil_padrao": "naoexiste"}}):
            with self.assertRaises(config.ConfigInvalida, msg=str(dados)):
                config.de_dict(dados)


class TestVigia(unittest.TestCase):
    def setUp(self):
        dados = dict(BASE, regras=[{"processo": ["a.exe", "b.exe"], "perfil": "vava"},
                                   {"processo": "c.exe", "perfil": "padrao"}])
        self.cfg = config.de_dict(dados)

    def test_perfil_desejado(self):
        self.assertEqual(perfil_desejado(self.cfg, []), "padrao")
        self.assertEqual(perfil_desejado(self.cfg, ["B.EXE"]), "vava")
        self.assertEqual(perfil_desejado(self.cfg, ["c.exe", "a.exe"]), "vava")  # primeira regra ganha

    def test_so_troca_quando_muda(self):
        abertos = [set(), set(), {"a.exe"}, {"a.exe"}, {"a.exe", "x"}, set()]
        trocas = []
        v = Vigia(self.cfg, trocas.append, listar=lambda: abertos.pop(0))
        resultados = [v.verificar() for _ in range(6)]
        self.assertEqual(trocas, [1, 2, 1])
        self.assertEqual(resultados, ["padrao", None, "vava", None, None, "padrao"])

    def test_falha_tenta_de_novo(self):
        tentativas = []

        def trocar(slot):
            tentativas.append(slot)
            if len(tentativas) == 1:
                raise OSError("mouse desligado")

        v = Vigia(self.cfg, trocar, listar=lambda: {"a.exe"})
        with self.assertRaises(OSError):
            v.verificar()
        self.assertEqual(v.verificar(), "vava")
        self.assertEqual(tentativas, [2, 2])

    def test_reiniciar_reaplica(self):
        trocas = []
        v = Vigia(self.cfg, trocas.append, listar=lambda: set())
        v.verificar()
        v.reiniciar()
        v.verificar()
        self.assertEqual(trocas, [1, 1])


class TestHidraw(unittest.TestCase):
    def _hidraw(self, raiz, nome, hid_id, descritor):
        d = Path(raiz, nome, "device")
        d.mkdir(parents=True)
        (d / "uevent").write_text(f"DRIVER=hid-generic\nHID_ID={hid_id}\nHID_NAME=Logitech\n")
        (d / "report_descriptor").write_bytes(descritor)

    def test_acha_interface_hidpp_longa(self):
        with tempfile.TemporaryDirectory() as raiz:
            receptor = "0003:0000046D:0000C539"
            self._hidraw(raiz, "hidraw0", receptor, b"\x05\x01\x09\x02")           # mouse comum
            self._hidraw(raiz, "hidraw1", "0003:00001234:00005678", b"\x06\x00\xff\x85\x11")
            self._hidraw(raiz, "hidraw2", receptor, b"\x06\x00\xff\x09\x01\x85\x10\x85\x11")
            self.assertEqual(achar_hidraw(raiz), "/dev/hidraw2")

    def test_sem_receptor(self):
        with tempfile.TemporaryDirectory() as raiz:
            with self.assertRaises(ReceptorNaoEncontrado):
                achar_hidraw(raiz)


if __name__ == "__main__":
    unittest.main()
