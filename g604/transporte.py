"""Canal de relatórios HID++ longos (20 bytes, report id 0x11) até o receptor.

Windows/macOS usam hidapi. Linux usa /dev/hidraw* direto, sem dependências: o backend
libusb do hidapi tiraria o mouse do kernel enquanto estivesse aberto.
"""
from __future__ import annotations

import glob
import os
import sys

from . import RECEPTOR_ID, VENDOR_ID

TAMANHO = 20


class ReceptorNaoEncontrado(RuntimeError):
    pass


class Transporte:
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
    def __init__(self):
        try:
            import hid
        except ImportError as e:
            raise ReceptorNaoEncontrado("instale o pacote 'hidapi' (pip install hidapi)") from e
        caminhos = [d["path"] for d in hid.enumerate(VENDOR_ID, RECEPTOR_ID)
                    if d["usage_page"] == 0xFF00 and d["usage"] == 0x02]
        if not caminhos:
            raise ReceptorNaoEncontrado("receptor Lightspeed (046d:c539) não encontrado")
        self._dev = hid.device()
        self._dev.open_path(caminhos[0])

    def escrever(self, pacote):
        self._dev.write(pacote)

    def ler(self, timeout_ms):
        r = self._dev.read(TAMANHO, timeout_ms)
        return bytes(r) if r else None

    def fechar(self):
        self._dev.close()


def _descritor_tem_hidpp_longo(descritor: bytes) -> bool:
    # Usage Page 0xFF00 (06 00 FF) e Report ID 0x11 (85 11)
    return b"\x06\x00\xff" in descritor and b"\x85\x11" in descritor


def achar_hidraw(raiz_sys: str = "/sys/class/hidraw") -> str:
    """Caminho /dev/hidrawN da interface HID++ longa do receptor."""
    alvo = f"HID_ID=0003:{VENDOR_ID:08X}:{RECEPTOR_ID:08X}"
    for pasta in sorted(glob.glob(os.path.join(raiz_sys, "hidraw*"))):
        try:
            with open(os.path.join(pasta, "device", "uevent")) as f:
                if alvo not in f.read().upper():
                    continue
            with open(os.path.join(pasta, "device", "report_descriptor"), "rb") as f:
                if _descritor_tem_hidpp_longo(f.read()):
                    return "/dev/" + os.path.basename(pasta)
        except OSError:
            continue
    raise ReceptorNaoEncontrado("receptor Lightspeed (046d:c539) não encontrado em /dev/hidraw*")


class TransporteHidraw(Transporte):
    def __init__(self, caminho: str | None = None):
        caminho = caminho or achar_hidraw()
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


def abrir() -> Transporte:
    if sys.platform.startswith("linux"):
        return TransporteHidraw()
    return TransporteHidapi()
