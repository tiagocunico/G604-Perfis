import os
import shutil
import tempfile
import unittest
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtCore import Qt
    from PySide6.QtGui import QKeyEvent
    from PySide6.QtCore import QEvent
    from PySide6.QtWidgets import QApplication
except ImportError:  # PySide6 é opcional (extra "bandeja")
    QApplication = None

from g604 import config
from g604.mouse import Mouse
from g604.perfil import Perfil, diferencas
from g604.simulado import G604Simulado

RAIZ = Path(__file__).resolve().parent.parent


class TestSalvarPerfil(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.arq = Path(self.tmp.name, "perfis.toml")
        shutil.copy(RAIZ / "perfis.toml", self.arq)

    def tearDown(self):
        self.tmp.cleanup()

    def test_renomear_mantem_comentarios(self):
        antes = self.arq.read_text(encoding="utf-8")
        config.salvar_perfil(self.arq, 2, 'Vava "ranked"')
        depois = self.arq.read_text(encoding="utf-8")
        self.assertEqual(config.carregar(self.arq).perfis["vava"].nome, 'Vava "ranked"')
        self.assertEqual([l for l in antes.splitlines() if l.startswith("#")],
                         [l for l in depois.splitlines() if l.startswith("#")])
        self.assertEqual(len(antes.splitlines()), len(depois.splitlines()))

    def test_criar_perfil_novo(self):
        chave = config.salvar_perfil(self.arq, 3, "Counter-Strike 2")
        self.assertEqual(chave, "counter_strike_2")
        cfg = config.carregar(self.arq)
        self.assertEqual(cfg.perfis[chave].slot, 3)
        self.assertEqual(cfg.regras[0].perfil, "vava")  # regras intactas
        texto = self.arq.read_text(encoding="utf-8")
        self.assertLess(texto.index("[perfis.counter_strike_2]"), texto.index("[[regras]]"))

    def test_chave_repetida_e_acentos(self):
        self.assertEqual(config.salvar_perfil(self.arq, 3, "Padrão"), "padrao_2")

    def test_preserva_crlf(self):
        self.arq.write_bytes(self.arq.read_bytes().replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
        config.salvar_perfil(self.arq, 4, "Novo")
        dados = self.arq.read_bytes()
        self.assertEqual(dados.count(b"\n"), dados.count(b"\r\n"))


class TestDiferencas(unittest.TestCase):
    def test_lista_legivel(self):
        s = G604Simulado().memoria[2]
        a, b = Perfil.do_setor(s), Perfil.do_setor(s)
        b.taxa_hz, b.dpi_padrao = 500, 2
        b.botoes[3] = "tecla:Ctrl+Z"
        b.botoes[7] = "botao:voltar"
        self.assertEqual(diferencas(a, b), ["taxa 1000 → 500 Hz", "DPI padrão 800 → 1600",
                                            "G4: X → Ctrl+Z", "G8: E → Voltar"])
        self.assertEqual(diferencas(a, a), [])


@unittest.skipIf(QApplication is None, "PySide6 não instalado")
class TestEditor(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from g604.editor import EditorPerfis
        self.tmp = tempfile.TemporaryDirectory()
        self.arq = Path(self.tmp.name, "perfis.toml")
        shutil.copy(RAIZ / "perfis.toml", self.arq)
        self.sim = G604Simulado()
        self.mouse = Mouse(self.sim)
        self.salvos = []
        self.ed = EditorPerfis(lambda: self.mouse, config.carregar(self.arq),
                               ao_salvar=lambda: self.salvos.append(1),
                               pasta_backups=Path(self.tmp.name, "bkp"))
        self.perguntas = []
        self.ed.confirmar = lambda t: self.perguntas.append(t) or True
        self.ed._erro = lambda t: self.fail(f"erro inesperado: {t}")
        self.ed.carregar()

    def tearDown(self):
        self.ed.close()
        self.tmp.cleanup()

    def test_carrega_perfil_ativo(self):
        self.assertEqual(self.ed.slot, 1)
        self.assertEqual(self.ed.nome.text(), "Padrão")
        self.assertEqual(self.ed.acoes[3].texto(), "tecla:Ctrl+S")
        self.assertEqual(self.ed.acoes[13].texto(), "especial:0x10")
        self.assertEqual([self.ed.combo_slot.itemText(i) for i in range(3)],
                         ["Padrão  (slot 1)", "Vava  (slot 2)", "Slot 3 (vazio)"])
        self.assertFalse(self.ed.btn_gravar.isEnabled())

    def test_sem_mudanca_grava_identico(self):
        self.ed.mostrar(2)
        self.assertEqual(self.ed.coletar().aplicar_em(self.ed.bases[2]), self.sim.memoria[2])

    def test_editar_e_gravar(self):
        self.ed.mostrar(2)
        self.ed.acoes[3].definir("tecla:Z")
        self.ed.taxa.setCurrentIndex(self.ed.taxa.findData(500))
        self.ed.dpis[4].setValue(6400)
        self.ed.atualizar_resumo()
        self.assertIn("G4: X → Z", self.ed.resumo.text())
        self.assertTrue(self.ed.btn_gravar.isEnabled())
        self.assertTrue(self.ed.gravar())
        p = Perfil.do_setor(self.sim.memoria[2])
        self.assertEqual((p.botoes[3], p.taxa_hz, p.dpis), ("tecla:Z", 500, [400, 800, 1600, 3200, 6400]))
        self.assertEqual(self.sim.gravacoes, [2])
        self.assertEqual(len(list(Path(self.tmp.name, "bkp").iterdir())), 1)
        self.assertEqual(self.salvos, [1])
        self.assertIn("G4: X → Z", self.perguntas[0])

    def test_so_renomear_nao_grava_no_mouse(self):
        self.ed.mostrar(2)
        self.ed.nome.setText("Valorant")
        self.assertTrue(self.ed.gravar())
        self.assertEqual(self.sim.gravacoes, [])
        self.assertEqual(config.carregar(self.arq).perfis["vava"].nome, "Valorant")
        self.assertIn("perfis.toml", self.perguntas[0])

    def test_campo_invalido_bloqueia(self):
        self.ed.acoes[4].tipo.setCurrentIndex(self.ed.acoes[4].tipo.findData("tecla"))
        self.ed.acoes[4].tecla.setText("Ctrl+Nada")
        self.assertFalse(self.ed.btn_gravar.isEnabled())
        self.assertIn("G5", self.ed.resumo.text())
        self.ed._erro = lambda t: None
        self.assertFalse(self.ed.gravar())
        self.assertEqual(self.sim.gravacoes, [])

    def test_dpi_vazio_no_meio_corta_a_lista(self):
        self.ed.dpis[1].setValue(0)
        self.assertEqual(self.ed.coletar().dpis, [400])

    def test_descartar_ao_trocar_de_slot(self):
        self.ed.acoes[3].definir("tecla:Z")
        self.ed.confirmar = lambda t: False
        self.ed._trocar_slot(2)
        self.assertEqual(self.ed.slot, 1)
        self.ed.confirmar = lambda t: True
        self.ed._trocar_slot(2)
        self.assertEqual(self.ed.slot, 2)

    def test_habilitar_slot_vazio(self):
        self.ed.mostrar(3)
        self.assertEqual(self.ed.paginas.currentIndex(), 1)
        self.ed.copiar_de.setCurrentIndex(self.ed.copiar_de.findData(2))
        self.ed.nome_novo.setText("CS2")
        self.assertTrue(self.ed.habilitar())
        self.assertEqual(self.sim.gravacoes, [3, 0])
        self.assertEqual(self.mouse.diretorio()[2], (3, True))
        p3, p2 = Perfil.do_setor(self.sim.memoria[3]), Perfil.do_setor(self.sim.memoria[2])
        self.assertEqual((p3.nome, p3.botoes), ("CS2", p2.botoes))
        self.assertEqual(config.carregar(self.arq).perfis["cs2"].slot, 3)
        self.assertEqual(self.ed.slot, 3)
        self.assertEqual(self.ed.paginas.currentIndex(), 0)
        self.mouse.trocar(3)

    def test_captura_de_tecla(self):
        a = self.ed.acoes[3]
        a.tecla.iniciar_captura()
        a.tecla.event(QKeyEvent(QEvent.KeyPress, Qt.Key_Shift, Qt.ShiftModifier))
        self.assertTrue(a.tecla.capturando)  # só modificador: continua esperando
        a.tecla.event(QKeyEvent(QEvent.KeyPress, Qt.Key_S, Qt.ControlModifier | Qt.ShiftModifier))
        self.assertFalse(a.tecla.capturando)
        self.assertEqual(a.texto(), "tecla:Ctrl+Shift+S")
        a.tecla.iniciar_captura()
        a.tecla.event(QKeyEvent(QEvent.KeyPress, Qt.Key_Tab, Qt.NoModifier))
        self.assertEqual(a.texto(), "tecla:Tab")
        a.tecla.iniciar_captura()
        a.tecla.event(QKeyEvent(QEvent.KeyPress, Qt.Key_5, Qt.KeypadModifier))
        self.assertEqual(a.texto(), "tecla:Num5")


if __name__ == "__main__":
    unittest.main()
