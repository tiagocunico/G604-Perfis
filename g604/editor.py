"""Janela de edição dos perfis: botões, DPI, taxa e nome; habilita slots vazios.

    python -m g604.editor [--simulado] [--config perfis.toml]
(normalmente aberta pelo menu da bandeja, que já tem o mouse conectado)
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QEvent, Qt, Signal
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import (QApplication, QComboBox, QFormLayout, QGridLayout, QGroupBox,
                               QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton,
                               QScrollArea, QSpinBox, QStackedWidget, QVBoxLayout, QWidget)

from . import config as _config
from .hidpp import MouseDesconectado
from .mouse import GravacaoRecusada, Mouse
from .perfil import (BOTOES_MOUSE, DPI_MAX, DPI_MIN, ESPECIAIS, MIDIA, N_BOTOES_FISICOS,
                     NOMES_BOTAO_MOUSE, TAM_NOME, TAXAS_HZ, AcaoInvalida, Perfil, diferencas,
                     texto_para_acao)
from .transporte import ReceptorNaoEncontrado

ERROS_MOUSE = (MouseDesconectado, ReceptorNaoEncontrado, GravacaoRecusada, OSError)

# ---- captura de tecla: evento do Qt -> nome usado em perfil.TECLAS

_QT_TECLAS = {
    Qt.Key_Return: "Enter", Qt.Key_Escape: "Esc", Qt.Key_Backspace: "Backspace", Qt.Key_Tab: "Tab",
    Qt.Key_Backtab: "Tab", Qt.Key_Space: "Espaco", Qt.Key_Minus: "-", Qt.Key_Equal: "=",
    Qt.Key_BracketLeft: "[", Qt.Key_BracketRight: "]", Qt.Key_Backslash: "\\", Qt.Key_Semicolon: ";",
    Qt.Key_Apostrophe: "'", Qt.Key_QuoteLeft: "`", Qt.Key_Comma: ",", Qt.Key_Period: ".",
    Qt.Key_Slash: "/", Qt.Key_CapsLock: "CapsLock", Qt.Key_Print: "PrintScreen",
    Qt.Key_ScrollLock: "ScrollLock", Qt.Key_Pause: "Pause", Qt.Key_Insert: "Insert",
    Qt.Key_Home: "Home", Qt.Key_PageUp: "PgUp", Qt.Key_Delete: "Delete", Qt.Key_End: "End",
    Qt.Key_PageDown: "PgDn", Qt.Key_Right: "Direita", Qt.Key_Left: "Esquerda", Qt.Key_Down: "Baixo",
    Qt.Key_Up: "Cima", Qt.Key_NumLock: "NumLock", Qt.Key_Menu: "Menu",
}
_QT_NUMPAD = {Qt.Key_Slash: "Num/", Qt.Key_Asterisk: "Num*", Qt.Key_Minus: "Num-",
              Qt.Key_Plus: "Num+", Qt.Key_Enter: "NumEnter", Qt.Key_Return: "NumEnter",
              Qt.Key_Period: "Num.", Qt.Key_Comma: "Num."}
_QT_SO_MODIFICADOR = {Qt.Key_Control, Qt.Key_Shift, Qt.Key_Alt, Qt.Key_Meta, Qt.Key_AltGr}


def tecla_do_evento(ev: QKeyEvent) -> str | None:
    """'Ctrl+Shift+S' a partir de um evento de teclado, ou None se for só um modificador."""
    k = ev.key()
    if k in _QT_SO_MODIFICADOR:
        return None
    mods = ev.modifiers()
    numpad = bool(mods & Qt.KeypadModifier)
    if Qt.Key_A <= k <= Qt.Key_Z:
        tecla = chr(k)
    elif Qt.Key_0 <= k <= Qt.Key_9:
        tecla = ("Num" if numpad else "") + chr(k)
    elif Qt.Key_F1 <= k <= Qt.Key_F24:
        tecla = f"F{k - Qt.Key_F1 + 1}"
    elif numpad and k in _QT_NUMPAD:
        tecla = _QT_NUMPAD[k]
    elif k in _QT_TECLAS:
        tecla = _QT_TECLAS[k]
    elif k == Qt.Key_Enter:
        tecla = "Enter"
    else:
        # símbolo com Shift (ex.: '!' de Shift+1): usa a tecla física quando o Windows informa
        vk = ev.nativeVirtualKey()
        if sys.platform == "win32" and (0x30 <= vk <= 0x39 or 0x41 <= vk <= 0x5A):
            tecla = chr(vk)
        else:
            return None
    partes = [n for flag, n in ((Qt.ControlModifier, "Ctrl"), (Qt.ShiftModifier, "Shift"),
                                (Qt.AltModifier, "Alt"), (Qt.MetaModifier, "Win")) if mods & flag]
    return "+".join(partes + [tecla])


class CampoTecla(QLineEdit):
    """Campo de texto ('Ctrl+S') que também captura a combinação apertada no teclado."""
    capturado = Signal(str)

    def __init__(self):
        super().__init__()
        self.capturando = False
        self.setPlaceholderText("ex.: Ctrl+S")

    def iniciar_captura(self):
        self.capturando = True
        self._antes = self.text()
        self.setText("aperte a tecla…")
        self.setFocus()

    def cancelar_captura(self):
        if self.capturando:
            self.capturando = False
            self.setText(self._antes)

    def event(self, ev):
        if self.capturando and ev.type() == QEvent.KeyPress:  # event(): pega até Tab
            texto = tecla_do_evento(ev)
            if texto:
                self.capturando = False
                self.setText(texto)
                self.capturado.emit(texto)
            return True
        if self.capturando and ev.type() == QEvent.FocusOut:
            self.cancelar_captura()
        return super().event(ev)


# ---- uma linha da tabela de botões

TIPOS = [("botao", "Botão do mouse"), ("tecla", "Tecla"), ("midia", "Mídia"),
         ("especial", "Especial"), ("bruto", "Avançado (bytes)")]


class EditorAcao(QWidget):
    mudou = Signal()

    def __init__(self):
        super().__init__()
        lay = QHBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        self.tipo = QComboBox()
        for chave, rotulo in TIPOS:
            self.tipo.addItem(rotulo, chave)
        self.pilha = QStackedWidget()

        self.botao = QComboBox()
        for b in BOTOES_MOUSE:
            self.botao.addItem(NOMES_BOTAO_MOUSE[b], b)

        tecla = QWidget()
        lt = QHBoxLayout(tecla)
        lt.setContentsMargins(0, 0, 0, 0)
        self.tecla = CampoTecla()
        self.capturar = QPushButton("Capturar")
        self.capturar.setToolTip("Clique e aperte a tecla ou combinação no teclado")
        lt.addWidget(self.tecla, 1)
        lt.addWidget(self.capturar)

        self.midia = QComboBox()
        for nome in MIDIA.values():
            self.midia.addItem(nome, nome)

        self.especial = QComboBox()
        for nome in ESPECIAIS.values():
            self.especial.addItem(f"{nome} (não testado)", nome)

        self.bruto = QLineEdit()
        self.bruto.setPlaceholderText("8 dígitos hexa, ex.: 80020016")

        self._pilha_de = {}
        for chave, w in (("botao", self.botao), ("tecla", tecla), ("midia", self.midia),
                         ("especial", self.especial), ("bruto", self.bruto)):
            self._pilha_de[chave] = self.pilha.addWidget(w)
        lay.addWidget(self.tipo)
        lay.addWidget(self.pilha, 1)

        self.tipo.currentIndexChanged.connect(self._tipo_mudou)
        self.capturar.clicked.connect(self.tecla.iniciar_captura)
        for sinal in (self.botao.currentIndexChanged, self.midia.currentIndexChanged,
                      self.especial.currentIndexChanged, self.tecla.textChanged, self.bruto.textChanged):
            sinal.connect(self._mudou)

    def _tipo_mudou(self):
        self.pilha.setCurrentIndex(self._pilha_de[self.tipo.currentData()])
        self._mudou()

    def _mudou(self, *_):
        valido = True
        try:
            self.texto()
        except AcaoInvalida:
            valido = False
        alvo = {"tecla": self.tecla, "bruto": self.bruto}.get(self.tipo.currentData())
        if alvo is not None and not (alvo is self.tecla and self.tecla.capturando):
            alvo.setStyleSheet("" if valido else "background: #f6c9c9; color: #000;")
        self.mudou.emit()

    def definir(self, texto: str):
        for w in (self.tipo, self.botao, self.midia, self.especial, self.tecla, self.bruto):
            w.blockSignals(True)
        tipo, _, valor = texto.partition(":")
        if tipo == "especial" and self.especial.findData(valor) < 0:
            # código que o G604 usa mas ainda sem nome conhecido (ex.: G14/G15)
            self.especial.addItem(f"{valor} (função original do mouse)", valor)
        self.tipo.setCurrentIndex(self.tipo.findData(tipo if tipo in dict(TIPOS) else "bruto"))
        if tipo == "botao":
            self.botao.setCurrentIndex(self.botao.findData(valor))
        elif tipo == "tecla":
            self.tecla.setText(valor)
        elif tipo == "midia":
            self.midia.setCurrentIndex(self.midia.findData(valor))
        elif tipo == "especial":
            self.especial.setCurrentIndex(self.especial.findData(valor))
        else:
            self.bruto.setText(valor if tipo == "bruto" else texto_para_acao(texto).hex())
        self.pilha.setCurrentIndex(self._pilha_de[self.tipo.currentData()])
        for w in (self.tipo, self.botao, self.midia, self.especial, self.tecla, self.bruto):
            w.blockSignals(False)
        self.tecla.setStyleSheet("")
        self.bruto.setStyleSheet("")

    def texto(self) -> str:
        """Ação em texto validada; levanta AcaoInvalida se o campo estiver errado."""
        t = self.tipo.currentData()
        valor = {"botao": lambda: self.botao.currentData(), "tecla": lambda: self.tecla.text().strip(),
                 "midia": lambda: self.midia.currentData(), "especial": lambda: self.especial.currentData(),
                 "bruto": lambda: self.bruto.text().strip()}[t]()
        texto = f"{t}:{valor}"
        texto_para_acao(texto)
        return texto


# ---- janela

class EditorPerfis(QWidget):
    def __init__(self, obter_mouse: Callable[[], Mouse], cfg: _config.Config,
                 ao_salvar: Callable[[], None] | None = None, pasta_backups: Path | None = None):
        super().__init__()
        self.obter_mouse = obter_mouse
        self.cfg = cfg
        self.ao_salvar = ao_salvar
        self.pasta_backups = pasta_backups or cfg.pasta_backups
        self.confirmar = self._confirmar_dialogo  # trocado nos testes
        self.originais: dict[int, Perfil] = {}
        self.bases: dict[int, bytes] = {}
        self.diretorio: list[tuple[int, bool]] = []
        self.slot: int | None = None

        self.setWindowTitle("G604 — Editar perfis")
        self.resize(640, 760)
        raiz = QVBoxLayout(self)

        topo = QHBoxLayout()
        topo.addWidget(QLabel("Perfil:"))
        self.combo_slot = QComboBox()
        topo.addWidget(self.combo_slot, 1)
        self.btn_recarregar = QPushButton("Ler do mouse")
        topo.addWidget(self.btn_recarregar)
        raiz.addLayout(topo)

        self.paginas = QStackedWidget()
        raiz.addWidget(self.paginas, 1)
        self.paginas.addWidget(self._pagina_edicao())
        self.paginas.addWidget(self._pagina_vazia())

        self.resumo = QLabel()
        self.resumo.setWordWrap(True)
        self.resumo.setTextInteractionFlags(Qt.TextSelectableByMouse)
        raiz.addWidget(self.resumo)
        baixo = QHBoxLayout()
        baixo.addStretch(1)
        self.btn_descartar = QPushButton("Descartar")
        self.btn_gravar = QPushButton("Gravar no mouse")
        self.btn_gravar.setDefault(True)
        baixo.addWidget(self.btn_descartar)
        baixo.addWidget(self.btn_gravar)
        raiz.addLayout(baixo)

        self.combo_slot.activated.connect(lambda _: self._trocar_slot(self.combo_slot.currentData()))
        self.btn_recarregar.clicked.connect(self._recarregar_clicado)
        self.btn_descartar.clicked.connect(lambda: self.mostrar(self.slot))
        self.btn_gravar.clicked.connect(self.gravar)

    # ---- montagem

    def _pagina_edicao(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)

        geral = QGroupBox("Geral")
        form = QFormLayout(geral)
        self.nome = QLineEdit()
        self.nome.setMaxLength(TAM_NOME // 2)
        form.addRow("Nome:", self.nome)
        self.taxa = QComboBox()
        for hz in TAXAS_HZ:
            self.taxa.addItem(f"{hz} Hz", hz)
        form.addRow("Taxa de atualização:", self.taxa)

        linha_dpi = QHBoxLayout()
        self.dpis = []
        for _ in range(5):
            s = QSpinBox()
            s.setRange(0, DPI_MAX)
            s.setSingleStep(50)
            s.setSpecialValueText("—")
            s.setToolTip(f"{DPI_MIN}–{DPI_MAX}; '—' (0) deixa vazio")
            linha_dpi.addWidget(s)
            self.dpis.append(s)
        form.addRow("DPIs:", linha_dpi)
        linha_idx = QHBoxLayout()
        self.dpi_padrao = QComboBox()
        self.dpi_shift = QComboBox()
        linha_idx.addWidget(QLabel("padrão"))
        linha_idx.addWidget(self.dpi_padrao)
        linha_idx.addWidget(QLabel("shift"))
        linha_idx.addWidget(self.dpi_shift)
        linha_idx.addStretch(1)
        form.addRow("", linha_idx)
        lay.addWidget(geral)

        caixa = QGroupBox("Botões")
        grade = QGridLayout(caixa)
        self.acoes: list[EditorAcao] = []
        for i in range(N_BOTOES_FISICOS):
            grade.addWidget(QLabel(f"G{i + 1}"), i, 0)
            a = EditorAcao()
            grade.addWidget(a, i, 1)
            self.acoes.append(a)
            a.mudou.connect(self.atualizar_resumo)
        rolagem = QScrollArea()
        rolagem.setWidgetResizable(True)
        rolagem.setWidget(caixa)
        lay.addWidget(rolagem, 1)

        self.nome.textChanged.connect(self.atualizar_resumo)
        self.taxa.currentIndexChanged.connect(self.atualizar_resumo)
        for s in self.dpis:
            s.valueChanged.connect(self._dpis_mudaram)
        self.dpi_padrao.currentIndexChanged.connect(self.atualizar_resumo)
        self.dpi_shift.currentIndexChanged.connect(self.atualizar_resumo)
        return w

    def _pagina_vazia(self) -> QWidget:
        w = QWidget()
        lay = QVBoxLayout(w)
        self.aviso_vazio = QLabel()
        self.aviso_vazio.setWordWrap(True)
        lay.addWidget(self.aviso_vazio)
        form = QFormLayout()
        self.copiar_de = QComboBox()
        form.addRow("Copiar de:", self.copiar_de)
        self.nome_novo = QLineEdit()
        self.nome_novo.setMaxLength(TAM_NOME // 2)
        form.addRow("Nome:", self.nome_novo)
        lay.addLayout(form)
        self.btn_habilitar = QPushButton("Habilitar este slot")
        lay.addWidget(self.btn_habilitar)
        lay.addStretch(1)
        self.btn_habilitar.clicked.connect(self.habilitar)
        self.nome_novo.textChanged.connect(
            lambda t: self.btn_habilitar.setEnabled(bool(t.strip())))
        return w

    # ---- dados

    def carregar(self, slot: int | None = None):
        """Lê diretório e perfis do mouse; mostra o slot pedido (ou o ativo)."""
        m = self.obter_mouse()
        self.diretorio = m.diretorio()
        self.originais.clear()
        self.bases.clear()
        for i, (setor, hab) in enumerate(self.diretorio, 1):
            if hab:
                self.bases[i] = m.ler_setor(setor)
                self.originais[i] = Perfil.do_setor(self.bases[i])
        if slot is None:
            slot = m.perfil_ativo()
        self.combo_slot.clear()
        for i, (_, hab) in enumerate(self.diretorio, 1):
            rotulo = f"{self._nome_slot(i)}  (slot {i})" if hab else f"Slot {i} (vazio)"
            self.combo_slot.addItem(rotulo, i)
        self.mostrar(slot)

    def _nome_slot(self, slot: int) -> str:
        for p in self.cfg.perfis.values():
            if p.slot == slot:
                return p.nome
        return self.originais[slot].nome if slot in self.originais else f"Slot {slot}"

    def mostrar(self, slot: int):
        self.slot = slot
        self.combo_slot.setCurrentIndex(self.combo_slot.findData(slot))
        if slot not in self.originais:
            self.paginas.setCurrentIndex(1)
            self.aviso_vazio.setText(
                f"O slot {slot} está vazio. Para usá-lo, escolha um perfil para copiar como ponto de "
                "partida e dê um nome; depois edite os botões normalmente.")
            self.copiar_de.clear()
            for s in self.originais:
                self.copiar_de.addItem(f"{self._nome_slot(s)} (slot {s})", s)
            self.nome_novo.setText("")
            self.btn_habilitar.setEnabled(False)
            self.btn_gravar.setEnabled(False)
            self.btn_descartar.setEnabled(False)
            self.resumo.setText("")
            return
        self.paginas.setCurrentIndex(0)
        p = self.originais[slot]
        widgets = [self.nome, self.taxa, self.dpi_padrao, self.dpi_shift, *self.dpis]
        for w in widgets:
            w.blockSignals(True)
        self.nome.setText(self._nome_slot(slot))
        self.taxa.setCurrentIndex(max(0, self.taxa.findData(p.taxa_hz)))
        for i, s in enumerate(self.dpis):
            s.setValue(p.dpis[i] if i < len(p.dpis) else 0)
        self._preencher_indices(p.dpis[p.dpi_padrao], p.dpis[p.dpi_shift])
        for w in widgets:
            w.blockSignals(False)
        for a, texto in zip(self.acoes, p.botoes):
            a.definir(texto)
        self.atualizar_resumo()

    def _dpis_validos(self) -> list[int]:
        lista = []
        for s in self.dpis:  # a lista termina no primeiro vazio
            if not s.value():
                break
            lista.append(s.value())
        return lista

    def _preencher_indices(self, padrao: int | None, shift: int | None):
        lista = self._dpis_validos()
        for combo, alvo in ((self.dpi_padrao, padrao), (self.dpi_shift, shift)):
            combo.blockSignals(True)
            combo.clear()
            for i, d in enumerate(lista):
                combo.addItem(str(d), i)
            combo.setCurrentIndex(lista.index(alvo) if alvo in lista else 0)
            combo.blockSignals(False)

    def _dpis_mudaram(self):
        self._preencher_indices(self.dpi_padrao.currentText() and int(self.dpi_padrao.currentText()),
                                self.dpi_shift.currentText() and int(self.dpi_shift.currentText()))
        self.atualizar_resumo()

    def coletar(self) -> Perfil:
        """Perfil com os valores da tela; levanta AcaoInvalida se algo estiver errado."""
        orig = self.originais[self.slot]
        dpis = self._dpis_validos()
        if not dpis:
            raise AcaoInvalida("informe pelo menos um DPI")
        botoes = list(orig.botoes)
        for i, a in enumerate(self.acoes):
            try:
                botoes[i] = a.texto()
            except AcaoInvalida as e:
                raise AcaoInvalida(f"G{i + 1}: {e}") from None
        return Perfil(nome=orig.nome, taxa_hz=self.taxa.currentData(), dpis=dpis,
                      dpi_padrao=max(0, self.dpi_padrao.currentIndex()),
                      dpi_shift=max(0, self.dpi_shift.currentIndex()),
                      botoes=botoes, botoes_shift=list(orig.botoes_shift))

    def pendencias(self) -> tuple[list[str], bool]:
        """(lista do que muda, se a mudança de nome é só no perfis.toml)."""
        if self.slot not in self.originais:
            return [], False
        novo = self.coletar()
        difs = diferencas(self.originais[self.slot], novo)
        novo.aplicar_em(self.bases[self.slot])  # valida faixas
        nome = self.nome.text().strip()
        if not nome:
            raise AcaoInvalida("o nome não pode ficar vazio")
        renomear = nome != self._nome_slot(self.slot)
        if renomear:
            difs.insert(0, f"nome {self._nome_slot(self.slot)} → {nome}")
        return difs, renomear

    def atualizar_resumo(self, *_):
        try:
            difs, _ = self.pendencias()
        except AcaoInvalida as e:
            self.resumo.setText(f"<span style='color:#c0392b'>⚠ {e}</span>")
            self.btn_gravar.setEnabled(False)
            self.btn_descartar.setEnabled(True)
            return
        if difs:
            self.resumo.setText(f"<b>{len(difs)} alteração(ões):</b> " + "; ".join(difs))
        else:
            self.resumo.setText("Sem alterações.")
        self.btn_gravar.setEnabled(bool(difs))
        self.btn_descartar.setEnabled(bool(difs))

    # ---- ações

    def _trocar_slot(self, slot: int):
        if slot == self.slot:
            return
        try:
            difs = self.pendencias()[0]
        except AcaoInvalida:
            difs = ["(campos inválidos)"]
        if difs and not self.confirmar("Descartar as alterações não gravadas deste perfil?"):
            self.combo_slot.setCurrentIndex(self.combo_slot.findData(self.slot))
            return
        self.mostrar(slot)

    def _recarregar_clicado(self):
        try:
            self.carregar(self.slot)
        except ERROS_MOUSE as e:
            self._erro(f"Não consegui ler o mouse: {e}")

    def gravar(self) -> bool:
        try:
            difs, renomear = self.pendencias()
            novo = self.coletar()
        except AcaoInvalida as e:
            self._erro(str(e))
            return False
        if not difs:
            return False
        so_nome = renomear and len(difs) == 1
        destino = "no perfis.toml" if so_nome else "na memória do mouse"
        if not self.confirmar(f"Gravar {destino}?\n\n• " + "\n• ".join(difs)):
            return False
        try:
            if not so_nome:
                dados = novo.aplicar_em(self.bases[self.slot])
                self.obter_mouse().gravar_perfil(self.slot, dados, self.pasta_backups)
            if renomear:
                _config.salvar_perfil(self.cfg.arquivo, self.slot, self.nome.text().strip())
                self.cfg = _config.carregar(self.cfg.arquivo)
            self.carregar(self.slot)
        except ERROS_MOUSE as e:
            self._erro(f"A gravação falhou: {e}\n\nO estado anterior está salvo em {self.pasta_backups}.")
            return False
        except (_config.ConfigInvalida, OSError) as e:
            self._erro(f"Gravei no mouse, mas não consegui atualizar o perfis.toml: {e}")
            return False
        if self.ao_salvar:
            self.ao_salvar()
        return True

    def habilitar(self) -> bool:
        origem = self.copiar_de.currentData()
        nome = self.nome_novo.text().strip()
        if origem is None or not nome:
            return False
        if not self.confirmar(f"Habilitar o slot {self.slot} como “{nome}”, copiando "
                              f"“{self._nome_slot(origem)}”?\n\nIsso grava na memória do mouse."):
            return False
        base = self.bases[origem]
        p = Perfil.do_setor(base)
        p.nome = nome[:TAM_NOME // 2]
        slot = self.slot
        try:
            self.obter_mouse().habilitar_slot(slot, p.aplicar_em(base), self.pasta_backups)
            _config.salvar_perfil(self.cfg.arquivo, slot, nome)
            self.cfg = _config.carregar(self.cfg.arquivo)
            self.carregar(slot)
        except ERROS_MOUSE as e:
            self._erro(f"Não consegui habilitar o slot: {e}")
            return False
        except (_config.ConfigInvalida, OSError) as e:
            self._erro(f"Slot habilitado no mouse, mas não consegui atualizar o perfis.toml: {e}")
            return False
        if self.ao_salvar:
            self.ao_salvar()
        return True

    # ---- diálogos

    def _confirmar_dialogo(self, texto: str) -> bool:
        return QMessageBox.question(self, "G604", texto) == QMessageBox.Yes

    def _erro(self, texto: str):
        QMessageBox.warning(self, "G604", texto)


def main(argv=None):
    ap = argparse.ArgumentParser(prog="g604-editor")
    ap.add_argument("--config")
    ap.add_argument("--simulado", action="store_true", help="usa um G604 simulado (não toca no mouse)")
    args = ap.parse_args(argv)
    app = QApplication(sys.argv[:1])
    cfg = _config.carregar(args.config)
    pasta = None
    if args.simulado:
        import tempfile
        from .simulado import G604Simulado
        mouse = Mouse(G604Simulado())
        pasta = Path(tempfile.gettempdir()) / "g604_simulado"  # não mistura com os backups reais
    else:
        mouse = Mouse()
    janela = EditorPerfis(lambda: mouse, cfg, pasta_backups=pasta)
    janela.carregar()
    janela.show()
    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
