"""Linha de comando: g604 status | trocar | mostrar | backup | restaurar | processos | vigia."""
from __future__ import annotations

import argparse
import sys
import time
from pathlib import Path

from . import config as _config
from .hidpp import MODO_ONBOARD, MouseDesconectado
from .mouse import Mouse, carregar_backup
from .transporte import ReceptorNaoEncontrado


def _abrir(args) -> Mouse:
    if args.simulado:
        from .simulado import G604Simulado
        return Mouse(G604Simulado())
    return Mouse()


def _pasta_backups(args, cfg) -> Path:
    if args.simulado:  # não mistura backups do simulador com os do mouse real
        import tempfile
        return Path(tempfile.gettempdir()) / "g604_simulado"
    return cfg.pasta_backups


def cmd_status(args, cfg):
    with _abrir(args) as m:
        ativo = m.perfil_ativo()
        print(f"{m.h.nome()}  |  modo {'on-board' if m.h.modo() == MODO_ONBOARD else 'host'}")
        for slot, (_, hab) in enumerate(m.diretorio(), 1):
            marca = "*" if slot == ativo else " "
            estado = "habilitado" if hab else "vazio/desabilitado"
            print(f" {marca} slot {slot}: {cfg.nome_do_slot(slot) if hab else '-':<12} {estado}")


def cmd_trocar(args, cfg):
    p = cfg.perfil(args.perfil)
    with _abrir(args) as m:
        m.trocar(p.slot)
        print(f"perfil ativo: {p.nome} (slot {m.perfil_ativo()})")


def cmd_mostrar(args, cfg):
    with _abrir(args) as m:
        slot = cfg.perfil(args.perfil).slot if args.perfil else m.perfil_ativo()
        p = m.ler_perfil(slot)
    print(f"slot {slot}: {p.nome!r}  {p.taxa_hz} Hz  DPIs {p.dpis} "
          f"(padrão {p.dpis[p.dpi_padrao]}, shift {p.dpis[p.dpi_shift]})")
    for i, (b, s) in enumerate(zip(p.botoes, p.botoes_shift), 1):
        extra = f"   | G-Shift: {s}" if s != "especial:0x00" else ""
        print(f"  G{i:<2} {b}{extra}")


def cmd_backup(args, cfg):
    with _abrir(args) as m:
        print("backup salvo em", m.backup(Path(args.pasta) if args.pasta else _pasta_backups(args, cfg)))


def cmd_restaurar(args, cfg):
    alvo = carregar_backup(Path(args.arquivo))
    with _abrir(args) as m:
        diferentes = {s: d for s, d in alvo.items() if m.ler_setor(s) != d}
        if not diferentes:
            print("o mouse já está igual ao backup; nada a gravar")
            return
        print("setores que mudariam:", ", ".join(f"{s:04x}" for s in sorted(diferentes)))
        if not args.confirmar:
            print("nada gravado. Rode de novo com --confirmar para gravar.")
            return
        bkp = m.gravar(diferentes, _pasta_backups(args, cfg))
        print(f"restaurado e conferido. Estado anterior salvo em {bkp}")


def cmd_processos(args, cfg):
    from .vigia import perfil_desejado, processos_abertos
    abertos = processos_abertos()
    filtro = (args.filtro or "").lower()
    for nome in sorted(abertos):
        if filtro in nome:
            print(" ", nome)
    print("perfil que a troca automática escolheria agora:", perfil_desejado(cfg, abertos))


def cmd_vigia(args, cfg):
    from .vigia import Vigia
    m = None

    def trocar(slot):
        nonlocal m
        if m is None:
            m = _abrir(args)
        m.trocar(slot)

    v = Vigia(cfg, trocar)
    print(f"vigiando a cada {cfg.intervalo_s}s (Ctrl+C para sair)")
    try:
        while True:
            try:
                novo = v.verificar()
                if novo:
                    print(time.strftime("%H:%M:%S"), "->", cfg.perfis[novo].nome)
            except (MouseDesconectado, ReceptorNaoEncontrado, OSError) as e:
                print(time.strftime("%H:%M:%S"), "mouse indisponível:", e)
                if m is not None:
                    m.fechar()
                m = None
            time.sleep(cfg.intervalo_s)
    except KeyboardInterrupt:
        pass
    finally:
        if m is not None:
            m.fechar()


def main(argv=None):
    ap = argparse.ArgumentParser(prog="g604", description="Perfis on-board do Logitech G604")
    ap.add_argument("--config", help="caminho do perfis.toml")
    ap.add_argument("--simulado", action="store_true", help="usa um G604 simulado (não toca no mouse)")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("status", help="perfis do mouse e qual está ativo")
    p = sub.add_parser("trocar", help="ativa um perfil (não grava na memória)")
    p.add_argument("perfil", help="chave, nome ou slot (ex.: vava, 2)")
    p = sub.add_parser("mostrar", help="botões e DPI de um perfil")
    p.add_argument("perfil", nargs="?")
    p = sub.add_parser("backup", help="salva a memória do mouse em JSON")
    p.add_argument("--pasta")
    p = sub.add_parser("restaurar", help="grava um backup de volta no mouse")
    p.add_argument("arquivo")
    p.add_argument("--confirmar", action="store_true", help="grava de fato (sem isso só mostra o que mudaria)")
    p = sub.add_parser("processos", help="lista processos abertos (para criar regras)")
    p.add_argument("filtro", nargs="?")
    sub.add_parser("vigia", help="troca de perfil automaticamente conforme os jogos abertos")
    args = ap.parse_args(argv)

    try:
        cfg = _config.carregar(args.config)
        {"status": cmd_status, "trocar": cmd_trocar, "mostrar": cmd_mostrar, "backup": cmd_backup,
         "restaurar": cmd_restaurar, "processos": cmd_processos, "vigia": cmd_vigia}[args.cmd](args, cfg)
    except (ReceptorNaoEncontrado, MouseDesconectado, _config.ConfigInvalida, ValueError) as e:
        print("erro:", e, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
