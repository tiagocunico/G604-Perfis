"""HID++ 2.0 sobre o receptor: Root (0x0000), Device Name (0x0005) e Onboard Profiles (0x8100)."""
from __future__ import annotations

import os
import time

from .transporte import TAMANHO, Transporte

ROOT = 0x0000
NOME_DISPOSITIVO = 0x0005
NIVEL_BATERIA = 0x1000
ONBOARD_PROFILES = 0x8100

# funções do 0x8100
_INFO, _SET_MODO, _GET_MODO, _SET_PERFIL, _GET_PERFIL = 0, 1, 2, 3, 4
_LER_MEMORIA, _INICIO_ESCRITA, _ESCREVER, _FIM_ESCRITA = 5, 6, 7, 8

MODO_ONBOARD = 1
MODO_HOST = 2


class ErroHidpp(RuntimeError):
    def __init__(self, codigo: int, msg: str):
        super().__init__(msg)
        self.codigo = codigo


class MouseDesconectado(RuntimeError):
    pass


class SemResposta(MouseDesconectado):
    pass


def crc_ccitt(dados: bytes) -> int:
    crc = 0xFFFF
    for b in dados:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc


def crc_ok(setor: bytes) -> bool:
    return crc_ccitt(setor[:-2]) == (setor[-2] << 8 | setor[-1])


def com_crc(setor: bytes) -> bytes:
    s = bytearray(setor)
    c = crc_ccitt(s[:-2])
    s[-2], s[-1] = c >> 8, c & 0xFF
    return bytes(s)


class InfoMemoria:
    def __init__(self, bruto: bytes):
        self.bruto = bytes(bruto[:16])
        self.formato_perfil = bruto[1]
        self.n_perfis = bruto[3]
        self.n_perfis_rom = bruto[4]
        self.n_botoes = bruto[5]
        self.n_setores = bruto[6]
        self.tamanho_setor = bruto[7] << 8 | bruto[8]


class Hidpp:
    def __init__(self, transporte: Transporte, indice: int = 1, timeout_s: float = 2.0):
        self.t = transporte
        self.indice = indice
        self.timeout_s = timeout_s
        # id de software próprio do processo, para não confundir respostas de outro programa
        self.sw = (os.getpid() % 15) + 1
        self._features = {ROOT: 0}

    def chamar(self, feature: int, funcao: int, params: bytes = b"") -> bytes:
        # sem resposta: reenvia uma vez (outro programa pode ter falado com o receptor ao mesmo tempo),
        # exceto na gravação, onde repetir um bloco o duplicaria na memória
        try:
            return self._chamar(feature, funcao, params)
        except SemResposta:
            if feature == ONBOARD_PROFILES and funcao in (_INICIO_ESCRITA, _ESCREVER, _FIM_ESCRITA):
                raise
            return self._chamar(feature, funcao, params)

    def _chamar(self, feature: int, funcao: int, params: bytes) -> bytes:
        idx = self._features[feature]
        cabeca = (funcao << 4) | self.sw
        pacote = bytes([0x11, self.indice, idx, cabeca]) + bytes(params)
        self.t.escrever(pacote + b"\0" * (TAMANHO - len(pacote)))
        limite = time.monotonic() + self.timeout_s
        while time.monotonic() < limite:
            r = self.t.ler(200)
            if not r or len(r) < 7 or r[1] != self.indice:
                continue
            if r[2] == idx and r[3] == cabeca:
                return r[4:]
            if r[2] == 0xFF and r[3] == idx and r[4] == cabeca:
                raise ErroHidpp(r[5], f"erro HID++ {r[5]} (feature {feature:04x} fn {funcao})")
            if r[2] == 0x8F and r[3] == idx:  # erro HID++ 1.0: mouse desligado/fora de alcance
                raise MouseDesconectado("o mouse não respondeu (desligado ou fora de alcance?)")
        raise SemResposta("sem resposta do mouse")

    def feature(self, fid: int) -> int:
        if fid not in self._features:
            r = self.chamar(ROOT, 0, bytes([fid >> 8, fid & 0xFF]))
            if r[0] == 0:
                raise ErroHidpp(0, f"feature {fid:04x} não suportada")
            self._features[fid] = r[0]
        return self._features[fid]

    # ---- Device Name

    def nome(self) -> str:
        self.feature(NOME_DISPOSITIVO)
        n = self.chamar(NOME_DISPOSITIVO, 0)[0]
        nome = b""
        while len(nome) < n:
            nome += self.chamar(NOME_DISPOSITIVO, 1, bytes([len(nome)]))[: n - len(nome)]
        return nome.decode(errors="replace")

    # ---- Battery Level Status (o G604 informa só níveis discretos, ex.: 100/50/30/10%)

    def bateria(self) -> tuple[int, int, int]:
        """(nível %, próximo nível %, status); status 0 = descarregando."""
        self.feature(NIVEL_BATERIA)
        r = self.chamar(NIVEL_BATERIA, 0)
        return r[0], r[1], r[2]

    # ---- Onboard Profiles

    def info_memoria(self) -> InfoMemoria:
        self.feature(ONBOARD_PROFILES)
        return InfoMemoria(self.chamar(ONBOARD_PROFILES, _INFO))

    def modo(self) -> int:
        self.feature(ONBOARD_PROFILES)
        return self.chamar(ONBOARD_PROFILES, _GET_MODO)[0]

    def perfil_ativo(self) -> int:
        self.feature(ONBOARD_PROFILES)
        r = self.chamar(ONBOARD_PROFILES, _GET_PERFIL)
        return r[0] << 8 | r[1]

    def ativar_perfil(self, slot: int) -> None:
        self.feature(ONBOARD_PROFILES)
        self.chamar(ONBOARD_PROFILES, _SET_PERFIL, bytes([slot >> 8, slot & 0xFF]))

    def ler_setor(self, setor: int, tamanho: int) -> bytes:
        self.feature(ONBOARD_PROFILES)
        dados = b""
        off = 0
        while off < tamanho:
            o = min(off, tamanho - 16)  # a leitura sempre devolve 16 bytes dentro do setor
            r = self.chamar(ONBOARD_PROFILES, _LER_MEMORIA,
                            bytes([setor >> 8, setor & 0xFF, o >> 8, o & 0xFF]))[:16]
            dados = dados[:o] + r
            off = o + 16
        return dados

    def gravar_setor(self, setor: int, dados: bytes) -> None:
        """Grava o setor inteiro; o CRC dos 2 últimos bytes é recalculado aqui."""
        self.feature(ONBOARD_PROFILES)
        n = len(dados)
        dados = com_crc(dados)
        self.chamar(ONBOARD_PROFILES, _INICIO_ESCRITA,
                    bytes([setor >> 8, setor & 0xFF, 0, 0, n >> 8, n & 0xFF]))
        buf = dados + b"\0" * (-n % 16)
        for i in range(0, len(buf), 16):
            self.chamar(ONBOARD_PROFILES, _ESCREVER, buf[i:i + 16])
        self.chamar(ONBOARD_PROFILES, _FIM_ESCRITA)
