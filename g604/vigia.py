"""Troca automática de perfil conforme os processos abertos."""
from __future__ import annotations

from typing import Callable, Iterable

from .config import Config


def processos_abertos() -> set[str]:
    import psutil
    nomes = set()
    for p in psutil.process_iter(["name"]):
        nome = p.info.get("name")
        if nome:
            nomes.add(nome.lower())
    return nomes


def perfil_desejado(cfg: Config, processos: Iterable[str]) -> str:
    abertos = {p.lower() for p in processos}
    for regra in cfg.regras:
        if any(p.lower() in abertos for p in regra.processos):
            return regra.perfil
    return cfg.perfil_padrao


class Vigia:
    """Só age quando o perfil desejado muda: uma troca manual não é desfeita a cada verificação."""

    def __init__(self, cfg: Config, trocar: Callable[[int], None],
                 listar: Callable[[], set[str]] = processos_abertos):
        self.cfg = cfg
        self._trocar = trocar
        self._listar = listar
        self._ultimo: str | None = None

    def reiniciar(self):
        """Força reaplicar a regra na próxima verificação (ex.: mouse religado)."""
        self._ultimo = None

    def verificar(self) -> str | None:
        """Devolve a chave do perfil aplicado agora, ou None se nada mudou."""
        desejado = perfil_desejado(self.cfg, self._listar())
        if desejado == self._ultimo:
            return None
        self._trocar(self.cfg.perfis[desejado].slot)  # se falhar, tenta de novo na próxima
        self._ultimo = desejado
        return desejado
