import contextlib
import io
import tempfile
import unittest
from pathlib import Path

from g604 import cli
from g604.hidpp import MouseDesconectado, com_crc
from g604.mouse import GravacaoRecusada, Mouse, carregar_backup
from g604.perfil import Perfil
from g604.simulado import G604Simulado

RAIZ = Path(__file__).resolve().parent.parent
BACKUPS = RAIZ / "backups" / "GHUB_backup_20261014_1942"


class TestMouseSimulado(unittest.TestCase):
    def setUp(self):
        self.sim = G604Simulado()
        self.m = Mouse(self.sim)
        self.tmp = tempfile.TemporaryDirectory()
        self.pasta = Path(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_leitura(self):
        self.assertEqual(self.m.h.nome(), "G604 Wireless Gaming Mouse")
        self.assertEqual(self.m.tamanho_setor, 255)
        self.assertEqual(self.m.perfil_ativo(), 1)
        self.assertEqual(self.m.ler_setor(1), self.sim.memoria[1])
        self.assertEqual(self.m.ler_perfil(2).nome, "Vava")

    def test_bateria(self):
        self.assertEqual(self.m.bateria(), 50)
        self.sim.bateria = 10
        self.assertEqual(self.m.bateria(), 10)

    def test_bateria_nao_suportada(self):
        from g604.hidpp import ErroHidpp

        def sem_feature(fid):
            raise ErroHidpp(0, "não suportada")

        self.m.h.feature = sem_feature
        self.assertIsNone(self.m.bateria())

    def test_trocar_nao_grava(self):
        self.m.trocar(2)
        self.assertEqual(self.m.perfil_ativo(), 2)
        self.m.trocar(1)
        self.assertEqual(self.sim.trocas, [2, 1])
        self.assertEqual(self.sim.gravacoes, [])

    def test_trocar_para_slot_desabilitado(self):
        with self.assertRaises(ValueError):
            self.m.trocar(3)
        self.assertEqual(self.sim.trocas, [])

    def test_gravar_com_backup_e_verificacao(self):
        p = self.m.ler_perfil(2)
        p.dpis = [400, 800, 1200, 1600, 3200]
        novo = p.aplicar_em(self.m.ler_setor(2))
        antes = dict(self.sim.memoria)
        bkp = self.m.gravar({2: novo}, self.pasta)
        self.assertEqual(self.sim.memoria[2], novo)
        self.assertEqual(self.sim.memoria[1], antes[1])
        self.assertEqual(carregar_backup(bkp)[2], antes[2])

    def test_diretorio_gravado_por_ultimo(self):
        d0 = bytearray(self.m.ler_setor(0))
        d0[10] = 1  # habilita slot 3
        p3 = Perfil.do_setor(self.m.ler_setor(1)).aplicar_em(self.m.ler_setor(1))
        self.m.gravar({0: com_crc(bytes(d0)), 3: p3}, self.pasta)
        self.assertEqual(self.sim.gravacoes, [3, 0])
        self.m.trocar(3)

    def test_recusas(self):
        bom = self.m.ler_setor(2)
        ruim = bom[:-1] + bytes([bom[-1] ^ 1])
        for novos in ({2: ruim}, {2: bom[:100]}, {0x0101: bom}, {9: bom}):
            with self.assertRaises(GravacaoRecusada):
                self.m.gravar(novos, self.pasta)
        self.sim.memoria[2] = ruim  # CRC corrompido no próprio mouse
        with self.assertRaises(GravacaoRecusada):
            self.m.gravar({2: bom}, self.pasta)
        self.assertEqual(self.sim.gravacoes, [])
        self.assertEqual(list(self.pasta.iterdir()), [])

    def test_restaurar_backup(self):
        original = dict(self.sim.memoria)
        p = self.m.ler_perfil(2)
        p.taxa_hz = 500
        self.m.gravar({2: p.aplicar_em(self.m.ler_setor(2))}, self.pasta)
        self.assertNotEqual(self.sim.memoria[2], original[2])
        alvo = carregar_backup(next(self.pasta.iterdir()))
        self.m.gravar({s: d for s, d in alvo.items() if self.m.ler_setor(s) != d}, self.pasta)
        self.assertEqual(self.sim.memoria, original)

    def test_backups_antigos(self):
        self.assertEqual(set(carregar_backup(BACKUPS / "g604_memoria.json")), {0, 1, 2, 3, 4, 5})
        self.assertEqual(set(carregar_backup(BACKUPS / "g604_antes_vava.json")), {0, 1, 2})

    def test_reenvia_uma_vez_sem_resposta(self):
        self.m.h.timeout_s = 0.1
        original = self.sim.escrever
        perdidos = []

        def perde_primeira(pacote):
            if not perdidos:
                perdidos.append(pacote)  # simula resposta perdida
                return
            original(pacote)

        self.sim.escrever = perde_primeira
        self.assertEqual(self.m.perfil_ativo(), 1)
        self.assertEqual(len(perdidos), 1)

    def test_gravacao_nunca_reenvia(self):
        self.m.h.timeout_s = 0.1
        novo = self.m.ler_setor(2)
        original = self.sim.escrever
        enviados = []

        def perde_bloco(pacote):
            if pacote[3] >> 4 == 7:  # bloco de escrita: resposta perdida
                enviados.append(pacote)
                return
            original(pacote)

        self.sim.escrever = perde_bloco
        with self.assertRaises(MouseDesconectado):
            self.m.h.gravar_setor(2, novo)
        self.assertEqual(len(enviados), 1)

    def test_mouse_desligado(self):
        self.sim.ligado = False
        with self.assertRaises(MouseDesconectado):
            self.m.perfil_ativo()


class TestConexoes(unittest.TestCase):
    def test_bluetooth_usa_indice_ff(self):
        sim = G604Simulado()
        sim.indice = 0xFF
        enviados = []
        original = sim.escrever
        sim.escrever = lambda p: (enviados.append(p), original(p))
        m = Mouse(sim)
        self.assertEqual(m.perfil_ativo(), 1)
        self.assertEqual({p[1] for p in enviados}, {0xFF})

    def test_ignora_relatorios_que_nao_sao_hidpp(self):
        # no Bluetooth (Linux) movimento e teclas chegam no mesmo hidraw que o HID++
        sim = G604Simulado()
        m = Mouse(sim)
        original = sim.escrever

        def com_ruido(pacote):
            sim._fila.append(bytes([0x02, pacote[1], pacote[2], pacote[3], 9, 9, 9]))
            original(pacote)

        sim.escrever = com_ruido
        self.assertEqual(m.perfil_ativo(), 1)

    def test_tenta_a_proxima_conexao(self):
        # receptor plugado, mas o mouse está no modo Bluetooth
        from g604 import transporte
        receptor, bt = G604Simulado(), G604Simulado()
        receptor.ligado = False
        bt.indice, bt.descricao = 0xFF, "Bluetooth"
        original = transporte.candidatos
        transporte.candidatos = lambda: iter([lambda: receptor, lambda: bt])
        try:
            m = Mouse()
        finally:
            transporte.candidatos = original
        self.assertIs(m.t, bt)
        self.assertEqual(m.conexao, "Bluetooth")

    def test_nenhuma_conexao_responde(self):
        from g604 import transporte
        sim = G604Simulado()
        sim.ligado = False
        original = transporte.candidatos
        transporte.candidatos = lambda: iter([lambda: sim])
        try:
            with self.assertRaises(MouseDesconectado):
                Mouse()
        finally:
            transporte.candidatos = original


class TestCliSimulado(unittest.TestCase):
    def rodar(self, *args):
        saida = io.StringIO()
        with contextlib.redirect_stdout(saida):
            codigo = cli.main(["--simulado", *args])
        return codigo, saida.getvalue()

    def test_status(self):
        codigo, saida = self.rodar("status")
        self.assertEqual(codigo, 0)
        self.assertIn("* slot 1: Padrão", saida)
        self.assertIn("slot 2: Vava", saida)

    def test_trocar_por_nome(self):
        self.assertIn("Vava (slot 2)", self.rodar("trocar", "vava")[1])

    def test_mostrar(self):
        self.assertIn("G4  tecla:X", self.rodar("mostrar", "vava")[1])

    def test_perfil_desconhecido(self):
        with contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(self.rodar("trocar", "csgo")[0], 1)


if __name__ == "__main__":
    unittest.main()
