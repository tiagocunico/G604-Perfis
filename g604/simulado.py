"""G604 simulado a partir de um dump real, para testar sem o mouse (testes e --simulado)."""
from __future__ import annotations

import json
from collections import deque
from pathlib import Path

from .hidpp import crc_ok
from .perfil import entradas_diretorio
from .transporte import TAMANHO, Transporte

# estado da memória depois da gravação do Vava (slots 1 e 2 habilitados)
DUMP_PADRAO = Path(__file__).resolve().parent.parent / "tests" / "dados" / "g604_atual.json"

_IDX = {0x0005: 0x03, 0x1000: 0x06, 0x8100: 0x0E}  # índices iguais aos do G604 real
_ERRO_ARG_INVALIDO = 0x02
_ERRO_HARDWARE = 0x04


class G604Simulado(Transporte):
    def __init__(self, dump: Path | str = DUMP_PADRAO):
        dados = json.loads(Path(dump).read_text())
        self.info = bytes.fromhex(dados["info"])
        setores = dados.get("setores") or dados.get("sectors")
        self.memoria = {int(k, 16): bytes.fromhex(v) for k, v in setores.items()
                        if int(k, 16) < 0x0100}
        self.tamanho = self.info[7] << 8 | self.info[8]
        self.nome = b"G604 Wireless Gaming Mouse"
        self.modo = 1
        self.perfil = 1
        self.ligado = True
        self.bateria = 50  # %, como o G604 real informou em 15/10/2026
        self.trocas: list[int] = []
        self.gravacoes: list[int] = []
        self._fila: deque[bytes] = deque()
        self._escrita: tuple[int, int, bytearray] | None = None

    # ---- Transporte

    def escrever(self, pacote: bytes) -> None:
        assert len(pacote) == TAMANHO and pacote[0] == 0x11
        if not self.ligado:
            self._fila.append(bytes([0x10, pacote[1], 0x8F, pacote[2], pacote[3], 0x09, 0]))
            return
        dev, idx, cabeca, params = pacote[1], pacote[2], pacote[3], pacote[4:]
        try:
            r = self._tratar(idx, cabeca >> 4, params)
            resp = bytes([0x11, dev, idx, cabeca]) + r
        except _Erro as e:
            resp = bytes([0x11, dev, 0xFF, idx, cabeca, e.codigo])
        self._fila.append(resp + b"\0" * (TAMANHO - len(resp)))

    def ler(self, timeout_ms):
        return self._fila.popleft() if self._fila else None

    # ---- dispositivo

    def _tratar(self, idx: int, fn: int, p: bytes) -> bytes:
        if idx == 0x00:
            fid = p[0] << 8 | p[1]
            return bytes([_IDX.get(fid, 0)])
        if idx == _IDX[0x0005]:
            return bytes([len(self.nome)]) if fn == 0 else self.nome[p[0]:p[0] + 16]
        if idx == _IDX[0x1000] and fn == 0:
            return bytes([self.bateria, 30 if self.bateria > 30 else 10, 0])
        if idx != _IDX[0x8100]:
            raise _Erro(_ERRO_ARG_INVALIDO)
        if fn == 0:
            return self.info
        if fn == 2:
            return bytes([self.modo])
        if fn == 3:
            slot = p[0] << 8 | p[1]
            dir_ = entradas_diretorio(self.memoria[0], self.info[3])
            if not 1 <= slot <= len(dir_) or not dir_[slot - 1][1]:
                raise _Erro(_ERRO_ARG_INVALIDO)
            self.perfil = slot
            self.trocas.append(slot)
            return b""
        if fn == 4:
            return bytes([0, self.perfil])
        if fn == 5:
            setor, off = p[0] << 8 | p[1], p[2] << 8 | p[3]
            if setor not in self.memoria or off + 16 > self.tamanho:
                raise _Erro(_ERRO_ARG_INVALIDO)
            return self.memoria[setor][off:off + 16]
        if fn == 6:
            setor, n = p[0] << 8 | p[1], p[4] << 8 | p[5]
            if n != self.tamanho or setor >= 0x0100:
                raise _Erro(_ERRO_ARG_INVALIDO)
            self._escrita = (setor, n, bytearray())
            return b""
        if fn == 7:
            if self._escrita is None:
                raise _Erro(_ERRO_ARG_INVALIDO)
            self._escrita[2].extend(p[:16])
            return b""
        if fn == 8:
            if self._escrita is None:
                raise _Erro(_ERRO_ARG_INVALIDO)
            setor, n, buf = self._escrita
            self._escrita = None
            dados = bytes(buf[:n])
            if len(dados) != n or not crc_ok(dados):
                raise _Erro(_ERRO_HARDWARE)
            self.memoria[setor] = dados
            self.gravacoes.append(setor)
            return b""
        raise _Erro(_ERRO_ARG_INVALIDO)


class _Erro(Exception):
    def __init__(self, codigo):
        self.codigo = codigo
