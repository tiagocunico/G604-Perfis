"""Ícone na bandeja: mostra o perfil ativo, troca manual e troca automática por jogo.

    python -m g604.bandeja [--simulado] [--config perfis.toml]
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from PySide6.QtCore import QLockFile, QRectF, Qt, QTimer
from PySide6.QtGui import QAction, QActionGroup, QColor, QFont, QIcon, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QApplication, QMenu, QSystemTrayIcon

from . import config as _config
from .hidpp import MouseDesconectado
from .mouse import Mouse
from .transporte import ReceptorNaoEncontrado
from .vigia import Vigia

CORES = ["#3d7be0", "#e0473d", "#2fa36b", "#d99a1e", "#8a55d6"]  # slot 1..5
INTERVALO_BATERIA_S = 60
BATERIA_BAIXA = 10  # % — o G604 informa níveis discretos (100/50/30/10)
ERROS_MOUSE = (MouseDesconectado, ReceptorNaoEncontrado, OSError)


def cor_bateria(nivel: int) -> str:
    if nivel >= 50:
        return "#2ecc71"
    if nivel >= 20:
        return "#f1c40f"
    return "#e74c3c"


def desenhar_icone(texto: str, cor: str, bateria: int | None = None) -> QPixmap:
    """Círculo com a inicial do perfil; com bateria, uma barra embaixo preenchida pelo nível."""
    pix = QPixmap(64, 64)
    pix.fill(Qt.transparent)
    p = QPainter(pix)
    p.setRenderHint(QPainter.Antialiasing)
    p.setBrush(QColor(cor))
    p.setPen(Qt.NoPen)
    # o mais largo possível: a bandeja reduz o ícone para 16–24 px; a barra cobre a base do círculo
    circulo = QRectF(0, 0, 64, 64) if bateria is None else QRectF(5, 0, 54, 54)
    p.drawEllipse(circulo)
    p.setPen(QColor("white"))
    f = QFont()
    f.setBold(True)
    f.setPixelSize(44 if bateria is None else 38)
    p.setFont(f)
    p.drawText(circulo, Qt.AlignCenter, texto)
    if bateria is not None:
        # contorno claro + fundo escuro: a parte vazia aparece em barra de tarefas clara e escura
        caixa = QRectF(2, 46, 60, 17)
        p.setPen(QPen(QColor("#d8d8d8"), 3))
        p.setBrush(QColor("#2a2a2a"))
        p.drawRoundedRect(caixa, 5, 5)
        p.setPen(Qt.NoPen)
        interno = caixa.adjusted(4, 4, -4, -4)
        largura = max(4.0, interno.width() * min(bateria, 100) / 100)
        p.setBrush(QColor(cor_bateria(bateria)))
        p.drawRoundedRect(QRectF(interno.x(), interno.y(), largura, interno.height()), 2, 2)
    p.end()
    return pix


def icone(texto: str, cor: str, bateria: int | None = None) -> QIcon:
    return QIcon(desenhar_icone(texto, cor, bateria))


class Bandeja:
    def __init__(self, app: QApplication, args):
        self.app = app
        self.args = args
        self.cfg = _config.carregar(args.config)
        self.mouse: Mouse | None = None
        self.slot_ativo: int | None = None
        self._erro: str | None = None
        self.bateria: int | None = None
        self._proxima_bateria = 0.0
        self.editor = None
        self.vigia = Vigia(self.cfg, self._trocar)

        self.tray = QSystemTrayIcon()
        self.menu = QMenu()
        self.tray.setContextMenu(self.menu)
        self.tray.activated.connect(self._clicado)
        self._montar_menu()
        self.tray.show()

        self.timer = QTimer()
        self.timer.timeout.connect(self._verificar)
        self.timer.start(int(self.cfg.intervalo_s * 1000))
        QTimer.singleShot(0, self._verificar)

    # ---- mouse

    def _conectar(self) -> Mouse:
        if self.mouse is None:
            if self.args.simulado:
                from .simulado import G604Simulado
                self.mouse = Mouse(G604Simulado())
            else:
                self.mouse = Mouse()
        return self.mouse

    def _desconectar(self):
        if self.mouse is not None:
            try:
                self.mouse.fechar()
            except OSError:
                pass
        self.mouse = None
        self.slot_ativo = None
        self._proxima_bateria = 0.0  # ao voltar, lê a bateria de novo (pode ter trocado a pilha)
        self.vigia.reiniciar()  # ao voltar, reaplica a regra do jogo aberto

    def _trocar(self, slot: int):
        self._conectar().trocar(slot)
        self.slot_ativo = slot

    # ---- ciclo

    def _verificar(self):
        try:
            if self.acao_auto.isChecked():
                novo = self.vigia.verificar()
                if novo:
                    self.tray.showMessage("G604", f"Perfil {self.cfg.perfis[novo].nome}",
                                          QSystemTrayIcon.Information, 2000)
            self.slot_ativo = self._conectar().perfil_ativo()
            if time.monotonic() >= self._proxima_bateria:
                self._ler_bateria()
            self._erro = None
        except ERROS_MOUSE as e:
            self._desconectar()
            self._erro = str(e)
        self._atualizar()

    def _ler_bateria(self):
        nivel = self.mouse.bateria()
        self._proxima_bateria = time.monotonic() + INTERVALO_BATERIA_S
        if nivel is not None and nivel <= BATERIA_BAIXA and (self.bateria is None or self.bateria > BATERIA_BAIXA):
            self.tray.showMessage("G604", f"Bateria do mouse baixa (~{nivel}%). Hora de trocar a pilha.",
                                  QSystemTrayIcon.Warning, 8000)
        self.bateria = nivel

    def _escolher(self, slot: int):
        try:
            self._trocar(slot)
        except ERROS_MOUSE as e:
            self._desconectar()
            self.tray.showMessage("G604", f"Não consegui trocar: {e}", QSystemTrayIcon.Warning, 4000)
        except ValueError as e:
            self.tray.showMessage("G604", str(e), QSystemTrayIcon.Warning, 4000)
        self._atualizar()

    def _clicado(self, motivo):
        if motivo == QSystemTrayIcon.Trigger:  # clique simples: próximo perfil
            slots = sorted(p.slot for p in self.cfg.perfis.values())
            if self.slot_ativo in slots:
                self._escolher(slots[(slots.index(self.slot_ativo) + 1) % len(slots)])

    # ---- interface

    def _montar_menu(self):
        auto_ligado = self.acao_auto.isChecked() if hasattr(self, "acao_auto") else True
        self.menu.clear()
        self.titulo = self.menu.addAction("G604")
        self.titulo.setEnabled(False)
        self.menu.addSeparator()
        grupo = QActionGroup(self.menu)
        self.acoes_perfil = {}
        for p in sorted(self.cfg.perfis.values(), key=lambda p: p.slot):
            a = QAction(f"{p.nome}  (slot {p.slot})", self.menu, checkable=True)
            a.triggered.connect(lambda _=False, s=p.slot: self._escolher(s))
            grupo.addAction(a)
            self.menu.addAction(a)
            self.acoes_perfil[p.slot] = a
        self.menu.addSeparator()
        self.acao_auto = self.menu.addAction("Troca automática por jogo")
        self.acao_auto.setCheckable(True)
        self.acao_auto.setChecked(auto_ligado)
        self.acao_auto.toggled.connect(lambda on: on and self.vigia.reiniciar())
        self.menu.addAction("Editar perfis…", self._abrir_editor)
        self.menu.addAction("Editar perfis.toml", self._abrir_config)
        self.menu.addAction("Recarregar perfis.toml", self._recarregar)
        self.menu.addSeparator()
        self.menu.addAction("Sair", self.app.quit)

    def _atualizar(self):
        erro = self._erro
        if self.slot_ativo is None:
            nome = "mouse indisponível"
            self.tray.setIcon(icone("?", "#777777"))
        else:
            nome = self.cfg.nome_do_slot(self.slot_ativo)
            self.tray.setIcon(icone(nome[:1].upper(), CORES[(self.slot_ativo - 1) % len(CORES)],
                                    self.bateria))
        for slot, a in self.acoes_perfil.items():
            a.setChecked(slot == self.slot_ativo)
        sufixo = " (simulado)" if self.args.simulado else ""
        bat = f" · bateria ~{self.bateria}%" if self.bateria is not None and self.slot_ativo else ""
        self.titulo.setText(f"G604 — {nome}{bat}{sufixo}")
        conexao = f"\nConexão: {self.mouse.conexao}" if self.mouse is not None and self.slot_ativo else ""
        self.tray.setToolTip(f"G604: {nome}{sufixo}" + (f"\nBateria: ~{self.bateria}%" if bat else "")
                             + conexao
                             + (f"\n{erro}" if erro else ""))

    def _recarregar(self):
        try:
            self.cfg = _config.carregar(self.args.config)
        except (_config.ConfigInvalida, OSError, ValueError) as e:
            self.tray.showMessage("G604", f"perfis.toml inválido: {e}", QSystemTrayIcon.Warning, 6000)
            return
        self.vigia = Vigia(self.cfg, self._trocar)
        self._montar_menu()
        self.timer.setInterval(int(self.cfg.intervalo_s * 1000))
        self._verificar()

    def _abrir_editor(self):
        from .editor import EditorPerfis
        if self.editor is None:
            pasta = None
            if self.args.simulado:
                pasta = Path(tempfile.gettempdir()) / "g604_simulado"
            self.editor = EditorPerfis(self._conectar, self.cfg, ao_salvar=self._recarregar,
                                       pasta_backups=pasta)
        self.editor.cfg = self.cfg
        try:
            self.editor.carregar(self.slot_ativo)
        except ERROS_MOUSE as e:
            self._desconectar()
            self.tray.showMessage("G604", f"Não consegui ler o mouse: {e}", QSystemTrayIcon.Warning, 4000)
            return
        self.editor.show()
        self.editor.raise_()
        self.editor.activateWindow()

    def _abrir_config(self):
        caminho = str(self.cfg.arquivo)
        if sys.platform == "win32":
            os.startfile(caminho)
        else:
            subprocess.Popen(["xdg-open", caminho])


def main(argv=None):
    ap = argparse.ArgumentParser(prog="g604-bandeja")
    ap.add_argument("--config")
    ap.add_argument("--simulado", action="store_true", help="usa um G604 simulado (não toca no mouse)")
    args = ap.parse_args(argv)

    trava = QLockFile(os.path.join(tempfile.gettempdir(), "g604-bandeja.lock"))
    if not trava.tryLock(100):
        print("a bandeja do G604 já está aberta", file=sys.stderr)
        return 1

    app = QApplication(sys.argv[:1])
    app.setQuitOnLastWindowClosed(False)
    if not QSystemTrayIcon.isSystemTrayAvailable():
        print("bandeja do sistema indisponível", file=sys.stderr)
        return 1
    _b = Bandeja(app, args)
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
