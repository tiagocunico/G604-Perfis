import os
import types
import unittest

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

try:
    from PySide6.QtWidgets import QApplication
except ImportError:  # PySide6 é opcional (extra "bandeja")
    QApplication = None


@unittest.skipIf(QApplication is None, "PySide6 não instalado")
class TestBandeja(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])

    def setUp(self):
        from g604 import bandeja
        self.bandeja = bandeja
        self.b = bandeja.Bandeja(self.app, types.SimpleNamespace(config=None, simulado=True))
        self.b.timer.stop()
        self.b.vigia._listar = lambda: set()
        self.avisos = []
        self.b.tray.showMessage = lambda titulo, texto, *a: self.avisos.append(texto)
        self.b._verificar()

    def tearDown(self):
        self.b.tray.hide()

    def test_mostra_bateria(self):
        self.assertEqual(self.b.bateria, 50)
        self.assertIn("bateria ~50%", self.b.titulo.text())
        self.assertIn("Bateria: ~50%", self.b.tray.toolTip())

    def test_bateria_lida_so_a_cada_minuto(self):
        self.b.mouse.t.bateria = 30
        self.b._verificar()
        self.assertEqual(self.b.bateria, 50)
        self.b._proxima_bateria = 0
        self.b._verificar()
        self.assertEqual(self.b.bateria, 30)

    def test_aviso_de_bateria_baixa_uma_vez(self):
        self.b.mouse.t.bateria = 10
        for _ in range(3):
            self.b._proxima_bateria = 0
            self.b._verificar()
        self.assertEqual([a for a in self.avisos if "Bateria" in a], [self.avisos[-1]])
        self.assertIn("~10%", self.avisos[-1])

    def test_mouse_desligado_esconde_bateria(self):
        self.b.mouse.t.ligado = False
        self.b.mouse.h.timeout_s = 0.1
        self.b._verificar()
        self.assertNotIn("bateria", self.b.titulo.text())

    def test_icone_com_e_sem_bateria(self):
        sem = self.bandeja.desenhar_icone("P", "#3d7be0").toImage()
        com = self.bandeja.desenhar_icone("P", "#3d7be0", 50).toImage()
        verde = com.pixelColor(10, 53)    # início da barra: preenchido
        vazio = com.pixelColor(52, 53)    # fim da barra: vazio
        self.assertEqual(verde.name(), "#2ecc71")
        self.assertEqual(vazio.name(), "#2a2a2a")
        self.assertNotEqual(sem.pixelColor(10, 53).name(), "#2ecc71")


if __name__ == "__main__":
    unittest.main()
