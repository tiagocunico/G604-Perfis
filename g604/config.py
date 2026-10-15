"""Leitura do perfis.toml."""
from __future__ import annotations

import os
import re
import sys
import unicodedata
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


def _chave_nova(nome: str, existentes) -> str:
    base = unicodedata.normalize("NFKD", nome).encode("ascii", "ignore").decode().lower()
    base = re.sub(r"[^a-z0-9]+", "_", base).strip("_") or "perfil"
    chave, n = base, 2
    while chave in existentes:
        chave, n = f"{base}_{n}", n + 1
    return chave


def salvar_perfil(arquivo: Path, slot: int, nome: str) -> str:
    """Cria ou renomeia o perfil do slot no perfis.toml, mexendo só nessas linhas
    (comentários e o resto do arquivo ficam como estão). Devolve a chave do perfil."""
    arquivo = Path(arquivo)
    texto = arquivo.read_bytes().decode("utf-8-sig")  # sem read_text: preserva \r\n
    cfg = de_dict(tomllib.loads(texto), arquivo)
    nome_toml = '"' + nome.replace("\\", "\\\\").replace('"', '\\"') + '"'
    nl = "\r\n" if "\r\n" in texto else "\n"
    linhas = texto.splitlines(keepends=True)
    cabecalho = re.compile(r"^\s*\[")

    existente = next((p for p in cfg.perfis.values() if p.slot == slot), None)
    if existente:
        chave = existente.chave
        ini = next(i for i, l in enumerate(linhas)
                   if re.match(rf"^\s*\[perfis\.{re.escape(chave)}\]\s*$", l))
        fim = next((i for i in range(ini + 1, len(linhas)) if cabecalho.match(linhas[i])), len(linhas))
        for i in range(ini + 1, fim):
            if re.match(r"^\s*nome\s*=", linhas[i]):
                linhas[i] = f"nome = {nome_toml}{nl}"
                break
        else:
            linhas.insert(ini + 1, f"nome = {nome_toml}{nl}")
    else:
        chave = _chave_nova(nome, cfg.perfis)
        bloco = [nl, f"[perfis.{chave}]{nl}", f"slot = {slot}{nl}", f"nome = {nome_toml}{nl}"]
        ultimos = [i for i, l in enumerate(linhas) if re.match(r"^\s*\[perfis\.", l)]
        pos = ultimos[-1] + 1 if ultimos else len(linhas)
        while pos < len(linhas) and linhas[pos].strip() and not linhas[pos].lstrip().startswith(("#", "[")):
            pos += 1  # pula as linhas chave = valor do último perfil
        linhas[pos:pos] = bloco

    novo = "".join(linhas)
    de_dict(tomllib.loads(novo), arquivo)  # nunca salva um arquivo que não carrega
    arquivo.write_bytes(novo.encode("utf-8"))  # bytes: não converte as quebras de linha
    return chave


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
