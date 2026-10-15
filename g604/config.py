"""Leitura do perfis.toml."""
from __future__ import annotations

import os
import sys
from dataclasses import dataclass, field
from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib

RAIZ = Path(__file__).resolve().parent.parent


class ConfigInvalida(ValueError):
    pass


@dataclass
class PerfilCfg:
    chave: str
    slot: int
    nome: str


@dataclass
class Regra:
    processos: list[str]
    perfil: str


@dataclass
class Config:
    perfis: dict[str, PerfilCfg]
    regras: list[Regra] = field(default_factory=list)
    perfil_padrao: str = ""
    intervalo_s: float = 2.0
    pasta_backups: Path = RAIZ / "backups" / "automaticos"
    arquivo: Path | None = None

    def perfil(self, nome_ou_slot: str) -> PerfilCfg:
        """Aceita a chave ('vava'), o nome ('Vava') ou o número do slot ('2')."""
        alvo = nome_ou_slot.strip().lower()
        for p in self.perfis.values():
            if alvo in (p.chave.lower(), p.nome.lower(), str(p.slot)):
                return p
        raise ConfigInvalida(f"perfil '{nome_ou_slot}' não está no perfis.toml "
                             f"(conhecidos: {', '.join(self.perfis)})")

    def nome_do_slot(self, slot: int) -> str:
        for p in self.perfis.values():
            if p.slot == slot:
                return p.nome
        return f"Slot {slot}"


def caminho_padrao() -> Path:
    if os.environ.get("G604_CONFIG"):
        return Path(os.environ["G604_CONFIG"])
    return RAIZ / "perfis.toml"


def carregar(arquivo: Path | None = None) -> Config:
    arquivo = Path(arquivo or caminho_padrao())
    # utf-8-sig: o Bloco de Notas do Windows pode salvar com BOM, que o TOML não aceita
    texto = arquivo.read_text(encoding="utf-8-sig")
    try:
        dados = tomllib.loads(texto)
    except tomllib.TOMLDecodeError as e:
        raise ConfigInvalida(f"{arquivo.name}: {e}") from None
    return de_dict(dados, arquivo)


def de_dict(dados: dict, arquivo: Path | None = None) -> Config:
    perfis = {}
    for chave, p in dados.get("perfis", {}).items():
        if "slot" not in p:
            raise ConfigInvalida(f"perfil '{chave}' sem 'slot'")
        perfis[chave] = PerfilCfg(chave, int(p["slot"]), p.get("nome", chave))
    if not perfis:
        raise ConfigInvalida("nenhum perfil em [perfis]")

    slots = [p.slot for p in perfis.values()]
    if len(set(slots)) != len(slots):
        raise ConfigInvalida("dois perfis com o mesmo slot")

    regras = []
    for r in dados.get("regras", []):
        procs = r.get("processo", [])
        procs = [procs] if isinstance(procs, str) else list(procs)
        if not procs or r.get("perfil") not in perfis:
            raise ConfigInvalida(f"regra inválida: {r} (precisa de 'processo' e de um 'perfil' existente)")
        regras.append(Regra(procs, r["perfil"]))

    vigia = dados.get("vigia", {})
    padrao = vigia.get("perfil_padrao", next(iter(perfis)))
    if padrao not in perfis:
        raise ConfigInvalida(f"vigia.perfil_padrao '{padrao}' não existe em [perfis]")

    cfg = Config(perfis=perfis, regras=regras, perfil_padrao=padrao,
                 intervalo_s=float(vigia.get("intervalo", 2.0)), arquivo=arquivo)
    if "pasta_backups" in dados:
        base = arquivo.parent if arquivo else RAIZ
        cfg.pasta_backups = (base / dados["pasta_backups"]).resolve()
    return cfg
