import json
import unittest
from pathlib import Path

from g604.hidpp import crc_ok
from g604.perfil import (TECLAS, AcaoInvalida, Perfil, acao_para_texto, entradas_diretorio,
                         texto_para_acao)

RAIZ = Path(__file__).resolve().parent.parent
DUMP_ORIGINAL = RAIZ / "backups" / "GHUB_backup_20261014_1942" / "g604_memoria.json"
DUMP_ATUAL = RAIZ / "tests" / "dados" / "g604_atual.json"


def setores(arquivo):
    d = json.loads(arquivo.read_text())
    s = d.get("setores") or d["sectors"]
    return {int(k, 16): bytes.fromhex(v) for k, v in s.items()}


class TestSetores(unittest.TestCase):
    def test_crc_de_todos_os_setores_do_usuario(self):
        for arq in (DUMP_ORIGINAL, DUMP_ATUAL):
            for n, s in setores(arq).items():
                if n < 0x0100:
                    self.assertTrue(crc_ok(s), f"{arq.name} setor {n:04x}")

    def test_ida_e_volta_preserva_todos_os_bytes(self):
        for arq in (DUMP_ORIGINAL, DUMP_ATUAL):
            for n, s in setores(arq).items():
                if 1 <= n <= 5 and s[0] != 0xFF:
                    self.assertEqual(Perfil.do_setor(s).aplicar_em(s), s, f"{arq.name} setor {n:04x}")

    def test_diretorio(self):
        self.assertEqual(entradas_diretorio(setores(DUMP_ORIGINAL)[0], 5),
                         [(1, True), (2, False), (3, False), (4, False), (5, False)])
        self.assertEqual(entradas_diretorio(setores(DUMP_ATUAL)[0], 5)[:2], [(1, True), (2, True)])


class TestPerfil(unittest.TestCase):
    def test_perfil_padrao_decodificado(self):
        p = Perfil.do_setor(setores(DUMP_ORIGINAL)[1])
        self.assertEqual(p.taxa_hz, 250)
        self.assertEqual(p.dpis, [400, 800, 1600, 3200])
        self.assertEqual(p.dpis[p.dpi_padrao], 800)
        self.assertEqual(p.botoes[:13], [
            "botao:esquerdo", "botao:direito", "botao:meio", "tecla:Ctrl+S", "tecla:Ctrl+Z",
            "tecla:Enter", "tecla:Ctrl+X", "botao:voltar", "botao:avancar", "tecla:Ctrl+V",
            "tecla:Ctrl+C", "tecla:Backspace", "tecla:Delete"])
        self.assertEqual(p.botoes[13:15], ["especial:0x10", "especial:0x11"])

    def test_montar_vava_pela_api_igual_ao_gravado(self):
        s = setores(DUMP_ORIGINAL)
        p = Perfil.do_setor(s[1])
        p.nome, p.taxa_hz = "Vava", 1000
        for i, t in enumerate("X T G C E Q 2 1 4 3".split(), start=3):
            p.botoes[i] = "tecla:" + t
        self.assertEqual(p.aplicar_em(s[1]), setores(DUMP_ATUAL)[2])

    def test_validacoes(self):
        base = setores(DUMP_ORIGINAL)[1]
        for mudar in (lambda p: setattr(p, "taxa_hz", 300),
                      lambda p: setattr(p, "dpis", []),
                      lambda p: setattr(p, "dpi_padrao", 9),
                      lambda p: setattr(p, "nome", "x" * 25),
                      lambda p: p.botoes.__setitem__(3, "tecla:Ctrl+Nada")):
            p = Perfil.do_setor(base)
            mudar(p)
            with self.assertRaises(AcaoInvalida):
                p.aplicar_em(base)


class TestAcoes(unittest.TestCase):
    def test_ida_e_volta_de_todas_as_teclas(self):
        for codigo in TECLAS:
            for mod in (0x00, 0x01, 0x05, 0x80):
                b = bytes([0x80, 0x02, mod, codigo])
                self.assertEqual(texto_para_acao(acao_para_texto(b)), b, acao_para_texto(b))

    def test_textos(self):
        casos = {
            "botao:voltar": "80010008", "tecla:Ctrl+S": "80020116", "tecla:ctrl+shift+esc": "80020329",
            "tecla:Ctrl+Num+": "80020157", "tecla:Num+": "80020057", "midia:volume+": "800300e9",
            "especial:dpi+": "90040000", "especial:0x10": "90100000", "bruto:ff000000": "ff000000",
        }
        for texto, hexa in casos.items():
            self.assertEqual(texto_para_acao(texto).hex(), hexa, texto)

    def test_invalidas(self):
        for t in ("tecla:", "tecla:Hiper+A", "botao:quinto", "midia:alto", "bruto:12", "xyz", "especial:zz"):
            with self.assertRaises(AcaoInvalida, msg=t):
                texto_para_acao(t)


if __name__ == "__main__":
    unittest.main()
