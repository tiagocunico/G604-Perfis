"""Formato do setor de perfil do G604 e das ações de botão.

Layout (setor de 255 bytes, formato de perfil 3):
  0        taxa de relatório (1000 / Hz)
  1, 2     índice do DPI padrão / do DPI shift
  3..12    5 DPIs (uint16 little-endian, 0 = vazio)
  32..95   16 botões x 4 bytes
  96..159  16 botões com G-Shift x 4 bytes
  160..207 nome (UTF-16LE)
  -2, -1   CRC-CCITT
Os demais bytes são preservados como vieram do mouse.

Ação de botão (4 bytes) e a forma em texto usada no perfis.toml:
  80 01 hh ll   botao:esquerdo | direito | meio | voltar | avancar
  80 02 mod key tecla:Ctrl+S
  80 03 hh ll   midia:volume+
  90 xx 00 00   especial:dpi+ (ou especial:0x10 quando o código não tem nome)
  qualquer      bruto:80020016
"""
from __future__ import annotations

from dataclasses import dataclass, field

from .hidpp import com_crc

N_BOTOES = 16
OFF_BOTOES = 32
OFF_SHIFT = 96
OFF_NOME = 160
TAM_NOME = 48

# ---- teclas (HID usage page 0x07)

TECLAS: dict[int, str] = {0x04 + i: chr(ord("A") + i) for i in range(26)}
TECLAS.update({0x1E + i: str((i + 1) % 10) for i in range(10)})
TECLAS.update({
    0x28: "Enter", 0x29: "Esc", 0x2A: "Backspace", 0x2B: "Tab", 0x2C: "Espaco",
    0x2D: "-", 0x2E: "=", 0x2F: "[", 0x30: "]", 0x31: "\\", 0x33: ";", 0x34: "'",
    0x35: "`", 0x36: ",", 0x37: ".", 0x38: "/", 0x39: "CapsLock",
    0x46: "PrintScreen", 0x47: "ScrollLock", 0x48: "Pause", 0x49: "Insert", 0x4A: "Home",
    0x4B: "PgUp", 0x4C: "Delete", 0x4D: "End", 0x4E: "PgDn",
    0x4F: "Direita", 0x50: "Esquerda", 0x51: "Baixo", 0x52: "Cima", 0x53: "NumLock",
    0x54: "Num/", 0x55: "Num*", 0x56: "Num-", 0x57: "Num+", 0x58: "NumEnter",
    0x62: "Num0", 0x63: "Num.", 0x65: "Menu",
})
TECLAS.update({0x59 + i: f"Num{i + 1}" for i in range(9)})
TECLAS.update({0x3A + i: f"F{i + 1}" for i in range(12)})
TECLAS.update({0x68 + i: f"F{i + 13}" for i in range(12)})
CODIGO_TECLA = {v.lower(): k for k, v in TECLAS.items()}

MODIFICADORES = ["Ctrl", "Shift", "Alt", "Win", "CtrlDir", "ShiftDir", "AltGr", "WinDir"]
CODIGO_MOD = {m.lower(): 1 << i for i, m in enumerate(MODIFICADORES)}

BOTOES_MOUSE = ["esquerdo", "direito", "meio", "voltar", "avancar"]

MIDIA = {0xE2: "mudo", 0xE9: "volume+", 0xEA: "volume-", 0xCD: "play", 0xB5: "proxima",
         0xB6: "anterior", 0xB7: "stop"}
CODIGO_MIDIA = {v: k for k, v in MIDIA.items()}

# códigos especiais do formato on-board (libratbag); 0x10/0x11 do G604 ainda sem nome
ESPECIAIS = {0x01: "scroll-esquerda", 0x02: "scroll-direita", 0x03: "bateria", 0x04: "dpi+",
             0x05: "dpi-ciclo", 0x06: "dpi-", 0x08: "perfil+", 0x09: "perfil-ciclo",
             0x0A: "perfil-", 0x0C: "g-shift", 0x0E: "dpi-shift"}
CODIGO_ESPECIAL = {v: k for k, v in ESPECIAIS.items()}


class AcaoInvalida(ValueError):
    pass


def acao_para_texto(b: bytes) -> str:
    t = b[0]
    if t == 0x80 and b[1] == 0x01:
        m = b[2] << 8 | b[3]
        nomes = [BOTOES_MOUSE[i] for i in range(5) if m >> i & 1]
        if len(nomes) == 1 and m < 32:
            return "botao:" + nomes[0]
    elif t == 0x80 and b[1] == 0x02 and b[3] in TECLAS:
        mods = [MODIFICADORES[i] for i in range(8) if b[2] >> i & 1]
        return "tecla:" + "+".join(mods + [TECLAS[b[3]]])
    elif t == 0x80 and b[1] == 0x03:
        c = b[2] << 8 | b[3]
        if c in MIDIA:
            return "midia:" + MIDIA[c]
    elif t == 0x90 and b[2:] == b"\0\0":
        return "especial:" + ESPECIAIS.get(b[1], f"0x{b[1]:02x}")
    return "bruto:" + bytes(b).hex()


def texto_para_acao(texto: str) -> bytes:
    tipo, _, valor = texto.strip().partition(":")
    tipo, v = tipo.lower(), valor.strip()
    if tipo == "botao" and v.lower() in BOTOES_MOUSE:
        m = 1 << BOTOES_MOUSE.index(v.lower())
        return bytes([0x80, 0x01, m >> 8, m & 0xFF])
    if tipo == "tecla" and v:
        *mods, tecla = v.split("+")
        # "Num+" termina em '+': tratar "Ctrl+Num+" corretamente
        if tecla == "" and mods:
            tecla = mods.pop() + "+"
        mascara = 0
        for m in mods:
            if m.lower() not in CODIGO_MOD:
                raise AcaoInvalida(f"modificador desconhecido '{m}' em '{texto}'")
            mascara |= CODIGO_MOD[m.lower()]
        if tecla.lower() not in CODIGO_TECLA:
            raise AcaoInvalida(f"tecla desconhecida '{tecla}' em '{texto}'")
        return bytes([0x80, 0x02, mascara, CODIGO_TECLA[tecla.lower()]])
    if tipo == "midia" and v.lower() in CODIGO_MIDIA:
        c = CODIGO_MIDIA[v.lower()]
        return bytes([0x80, 0x03, c >> 8, c & 0xFF])
    if tipo == "especial" and v:
        c = CODIGO_ESPECIAL.get(v.lower())
        if c is None:
            try:
                c = int(v, 16)
            except ValueError:
                raise AcaoInvalida(f"especial desconhecido '{v}'") from None
        return bytes([0x90, c, 0, 0])
    if tipo == "bruto":
        try:
            b = bytes.fromhex(v)
        except ValueError:
            b = b""
        if len(b) == 4:
            return b
    raise AcaoInvalida(f"ação inválida: '{texto}'")


@dataclass
class Perfil:
    nome: str
    taxa_hz: int
    dpis: list[int]
    dpi_padrao: int
    dpi_shift: int
    botoes: list[str] = field(default_factory=list)
    botoes_shift: list[str] = field(default_factory=list)

    @classmethod
    def do_setor(cls, s: bytes) -> "Perfil":
        dpis = [s[3 + 2 * i] | s[4 + 2 * i] << 8 for i in range(5)]
        nome = s[OFF_NOME:OFF_NOME + TAM_NOME].decode("utf-16-le", errors="replace")
        return cls(
            nome=nome.split("\0")[0],
            taxa_hz=1000 // s[0] if s[0] else 0,
            dpis=[d for d in dpis if d],
            dpi_padrao=s[1],
            dpi_shift=s[2],
            botoes=[acao_para_texto(s[OFF_BOTOES + 4 * i:OFF_BOTOES + 4 * i + 4]) for i in range(N_BOTOES)],
            botoes_shift=[acao_para_texto(s[OFF_SHIFT + 4 * i:OFF_SHIFT + 4 * i + 4]) for i in range(N_BOTOES)],
        )

    def aplicar_em(self, base: bytes) -> bytes:
        """Novo setor = base com os campos deste perfil por cima (CRC recalculado)."""
        if self.taxa_hz not in (125, 250, 500, 1000):
            raise AcaoInvalida(f"taxa inválida: {self.taxa_hz} Hz (use 125/250/500/1000)")
        if not 1 <= len(self.dpis) <= 5:
            raise AcaoInvalida("informe de 1 a 5 DPIs")
        for i in (self.dpi_padrao, self.dpi_shift):
            if not 0 <= i < len(self.dpis):
                raise AcaoInvalida(f"índice de DPI fora da lista: {i}")
        nome = self.nome.encode("utf-16-le")
        if len(nome) > TAM_NOME:
            raise AcaoInvalida("nome longo demais (máx. 24 caracteres)")

        s = bytearray(base)
        s[0] = 1000 // self.taxa_hz
        s[1], s[2] = self.dpi_padrao, self.dpi_shift
        for i in range(5):
            d = self.dpis[i] if i < len(self.dpis) else 0
            s[3 + 2 * i], s[4 + 2 * i] = d & 0xFF, d >> 8
        for off, lista in ((OFF_BOTOES, self.botoes), (OFF_SHIFT, self.botoes_shift)):
            for i, texto in enumerate(lista[:N_BOTOES]):
                s[off + 4 * i:off + 4 * i + 4] = texto_para_acao(texto)
        # nome: mantém o restante do campo como estava se o nome não mudou
        if self.nome != Perfil.do_setor(base).nome:
            s[OFF_NOME:OFF_NOME + TAM_NOME] = nome + b"\0" * (TAM_NOME - len(nome))
        return com_crc(bytes(s))


def entradas_diretorio(setor0: bytes, n_perfis: int) -> list[tuple[int, bool]]:
    """[(setor, habilitado)] do diretório de perfis (setor 0x0000)."""
    saida = []
    for i in range(n_perfis):
        e = setor0[4 * i:4 * i + 4]
        if e[:2] == b"\xff\xff":
            break
        saida.append((e[0] << 8 | e[1], bool(e[2])))
    return saida
