"""Canal de relatórios HID++ longos (20 bytes, report id 0x11) até o mouse.

Duas conexões, tentadas nesta ordem:
- receptor Lightspeed (046d:c539), mouse no índice 1, usage page 0xFF00;
- G604 pareado por Bluetooth (046d:b024), o próprio mouse no índice 0xFF, usage page 0xFF43.

Windows/macOS usam hidapi. Linux usa /dev/hidraw* direto, sem dependências: o backend
libusb do hidapi tiraria o mouse do kernel enquanto estivesse aberto.
"""
from __future__ import annotations

import glob
import os
import sys
from typing import Callable, Iterator, NamedTuple

from . import BLUETOOTH_ID, RECEPTOR_ID, VENDOR_ID

TAMANHO = 20


class ReceptorNaoEncontrado(RuntimeError):
    pass


class Conexao(NamedTuple):
    nome: str
    barramento: int     # BUS_USB 0x03 / BUS_BLUETOOTH 0x05 (HID_ID do Linux)
    produto: int
    usage_page: int
    usage: int          # na usage page vendor da Logitech (hidapi)
    indice: int         # índice HID++ do mouse


CONEXOES = (
    Conexao("receptor Lightspeed", 0x03, RECEPTOR_ID, 0xFF00, 0x0002, 0x01),
    Conexao("Bluetooth", 0x05, BLUETOOTH_ID, 0xFF43, 0x0202, 0xFF),
)

NAO_ENCONTRADO = "G604 não encontrado (nem receptor Lightspeed 046d:c539 nem Bluetooth 046d:b024)"


class Transporte:
    indice = 0x01           # índice HID++ do mouse nesta conexão
    descricao = "simulado"

    def escrever(self, pacote: bytes) -> None:
        raise NotImplementedError

    def ler(self, timeout_ms: int) -> bytes | None:
        """Um relatório, ou None se nada chegou dentro do timeout."""
        raise NotImplementedError

    def fechar(self) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fechar()


class TransporteHidapi(Transporte):
    def __init__(self, caminho: bytes, conexao: Conexao):
        import hid
        self.indice = conexao.indice
        self.descricao = conexao.nome
        self._dev = hid.device()
        self._dev.open_path(caminho)

    def escrever(self, pacote):
        self._dev.write(pacote)

    def ler(self, timeout_ms):
        r = self._dev.read(64, timeout_ms)
        return bytes(r[:TAMANHO]) if r else None

    def fechar(self):
        self._dev.close()


def _candidatos_hidapi() -> list[Callable[[], Transporte]]:
    try:
        import hid
    except ImportError as e:
        raise ReceptorNaoEncontrado("instale o pacote 'hidapi' (pip install hidapi)") from e
    abridores = []
    for c in CONEXOES:
        for d in hid.enumerate(VENDOR_ID, c.produto):
            if d["usage_page"] == c.usage_page and d["usage"] == c.usage:
                abridores.append(lambda p=d["path"], c=c: TransporteHidapi(p, c))
                break
    return abridores


def _descritor_tem_hidpp_longo(descritor: bytes, usage_page: int) -> bool:
    # Usage Page vendor (06 lo hi) e Report ID 0x11 (85 11)
    pagina = bytes([0x06, usage_page & 0xFF, usage_page >> 8])
    return pagina in descritor and b"\x85\x11" in descritor


def achar_hidraw(raiz_sys: str = "/sys/class/hidraw") -> list[tuple[str, Conexao]]:
    """Interfaces HID++ longas do G604 em /dev/hidrawN, na ordem de CONEXOES."""
    pastas = sorted(glob.glob(os.path.join(raiz_sys, "hidraw*")))
    achados = []
    for c in CONEXOES:
        alvo = f"HID_ID={c.barramento:04X}:{VENDOR_ID:08X}:{c.produto:08X}"
        for pasta in pastas:
            try:
                with open(os.path.join(pasta, "device", "uevent")) as f:
                    if alvo not in f.read().upper():
                        continue
                with open(os.path.join(pasta, "device", "report_descriptor"), "rb") as f:
                    if _descritor_tem_hidpp_longo(f.read(), c.usage_page):
                        achados.append(("/dev/" + os.path.basename(pasta), c))
                        break
            except OSError:
                continue
    if not achados:
        raise ReceptorNaoEncontrado(NAO_ENCONTRADO + " em /dev/hidraw*")
    return achados


class TransporteHidraw(Transporte):
    def __init__(self, caminho: str, conexao: Conexao):
        self.indice = conexao.indice
        self.descricao = conexao.nome
        try:
            self._fd = os.open(caminho, os.O_RDWR | os.O_NONBLOCK)
        except PermissionError as e:
            raise ReceptorNaoEncontrado(
                f"sem permissão em {caminho}: instale a regra udev (instalar/linux.sh)") from e

    def escrever(self, pacote):
        os.write(self._fd, pacote)

    def ler(self, timeout_ms):
        import select
        prontos, _, _ = select.select([self._fd], [], [], timeout_ms / 1000)
        if not prontos:
            return None
        return os.read(self._fd, 64)[:TAMANHO]

    def fechar(self):
        os.close(self._fd)


def candidatos() -> Iterator[Callable[[], Transporte]]:
    """Abridores das conexões presentes, na ordem de preferência; ReceptorNaoEncontrado se nenhuma."""
    if sys.platform.startswith("linux"):
        abridores = [lambda p=p, c=c: TransporteHidraw(p, c) for p, c in achar_hidraw()]
    else:
        abridores = _candidatos_hidapi()
        if not abridores:
            raise ReceptorNaoEncontrado(NAO_ENCONTRADO)
    return iter(abridores)
