"""API de alto nível do G604: perfil ativo, troca, backup e gravação segura."""
from __future__ import annotations

import json
import time
from datetime import datetime
from pathlib import Path

from . import transporte as _transporte
from .hidpp import ErroHidpp, Hidpp, com_crc, crc_ok
from .perfil import Perfil, entradas_diretorio

SETOR_DIRETORIO = 0x0000


class GravacaoRecusada(RuntimeError):
    pass


class Mouse:
    def __init__(self, t: _transporte.Transporte | None = None):
        self.t = t or _transporte.abrir()
        self.h = Hidpp(self.t)
        self.info = self.h.info_memoria()

    def fechar(self):
        self.t.fechar()

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.fechar()

    # ---- leitura

    @property
    def tamanho_setor(self) -> int:
        return self.info.tamanho_setor

    def ler_setor(self, setor: int) -> bytes:
        return self.h.ler_setor(setor, self.tamanho_setor)

    def diretorio(self) -> list[tuple[int, bool]]:
        return entradas_diretorio(self.ler_setor(SETOR_DIRETORIO), self.info.n_perfis)

    def ler_perfil(self, slot: int) -> Perfil:
        return Perfil.do_setor(self.ler_setor(self._setor_do_slot(slot)))

    def perfil_ativo(self) -> int:
        return self.h.perfil_ativo()

    def bateria(self) -> int | None:
        """Nível da bateria em % (aproximado), ou None se o mouse não informar."""
        try:
            nivel, _, status = self.h.bateria()
        except ErroHidpp:
            return None
        return nivel if status == 0 and 0 < nivel <= 100 else None

    def _setor_do_slot(self, slot: int) -> int:
        for i, (setor, _) in enumerate(self.diretorio(), 1):
            if i == slot:
                return setor
        raise ValueError(f"slot {slot} não existe")

    # ---- troca (não grava na memória)

    def trocar(self, slot: int) -> None:
        habilitados = [i for i, (_, hab) in enumerate(self.diretorio(), 1) if hab]
        if slot not in habilitados:
            raise ValueError(f"slot {slot} não está habilitado (habilitados: {habilitados})")
        self.h.ativar_perfil(slot)

    # ---- backup / gravação

    def setores_usuario(self) -> list[int]:
        return [SETOR_DIRETORIO] + [s for s, _ in self.diretorio()]

    def backup(self, pasta: Path) -> Path:
        pasta.mkdir(parents=True, exist_ok=True)
        arquivo = pasta / f"g604_{datetime.now():%Y%m%d_%H%M%S}.json"
        dados = {"info": self.info.bruto.hex(),
                 "setores": {f"{s:04x}": self.ler_setor(s).hex() for s in self.setores_usuario()}}
        arquivo.write_text(json.dumps(dados, indent=1))
        return arquivo

    def gravar(self, novos: dict[int, bytes], pasta_backup: Path) -> Path:
        """Grava setores com backup antes e leitura de volta depois. Devolve o arquivo de backup."""
        validos = set(self.setores_usuario())
        for setor, dados in novos.items():
            if setor not in validos:
                raise GravacaoRecusada(f"setor {setor:04x} não é um setor de perfil do usuário")
            if len(dados) != self.tamanho_setor:
                raise GravacaoRecusada(f"setor {setor:04x}: tamanho {len(dados)} != {self.tamanho_setor}")
            if not crc_ok(dados):
                raise GravacaoRecusada(f"setor {setor:04x}: CRC inválido nos dados novos")
            if not crc_ok(self.ler_setor(setor)):
                raise GravacaoRecusada(f"setor {setor:04x}: CRC atual no mouse não confere, abortando")
        arquivo = self.backup(pasta_backup)
        # perfis antes do diretório: o diretório só passa a apontar para algo já gravado
        for setor in sorted(novos, key=lambda s: s == SETOR_DIRETORIO):
            self.h.gravar_setor(setor, novos[setor])
            time.sleep(0.2)
            if self.ler_setor(setor) != novos[setor]:
                raise GravacaoRecusada(
                    f"setor {setor:04x} lido de volta diferente do gravado; backup em {arquivo}")
        return arquivo

    def gravar_perfil(self, slot: int, dados: bytes, pasta_backup: Path) -> Path:
        return self.gravar({self._setor_do_slot(slot): dados}, pasta_backup)

    def habilitar_slot(self, slot: int, dados: bytes, pasta_backup: Path) -> Path:
        """Grava o perfil num slot desabilitado e o habilita no diretório."""
        dir_ = self.diretorio()
        if not 1 <= slot <= len(dir_):
            raise ValueError(f"slot {slot} não existe")
        setor, habilitado = dir_[slot - 1]
        if habilitado:
            raise ValueError(f"slot {slot} já está habilitado")
        d0 = bytearray(self.ler_setor(SETOR_DIRETORIO))
        d0[4 * (slot - 1) + 2] = 1
        return self.gravar({setor: dados, SETOR_DIRETORIO: com_crc(bytes(d0))}, pasta_backup)


def carregar_backup(arquivo: Path) -> dict[int, bytes]:
    """Aceita o formato do backup() e os dumps antigos de scripts/ ('sectors' ou plano)."""
    dados = json.loads(Path(arquivo).read_text())
    setores = dados.get("setores") or dados.get("sectors") or dados
    # setores >= 0x0100 são ROM (perfil de fábrica): só leitura, nunca restaurados
    return {int(k, 16): bytes.fromhex(v) for k, v in setores.items()
            if len(k) == 4 and int(k, 16) < 0x0100}
