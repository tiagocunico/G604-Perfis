# G604-Perfis

Configuração do mouse Logitech G604 direto na memória interna (on-board), sem G Hub.
Comunicação via HID++ 2.0 pelo receptor Lightspeed (`046d:c539`), feature `0x8100` (Onboard Profiles).

Requisito: Python 3 com `pip install --user hidapi`. G Hub e Onboard Memory Manager precisam estar fechados.

## Perfis gravados

| Botão | Perfil 1 — Padrão | Perfil 2 — Vava |
|---|---|---|
| G1 / G2 / G3 | Esquerdo / Direito / Meio | Esquerdo / Direito / Meio |
| G4 | Ctrl+S | X |
| G5 | Ctrl+Z | T |
| G6 | Enter | G |
| G7 | Ctrl+X | C |
| G8 | Voltar | E |
| G9 | Avançar | Q |
| G10 | Ctrl+V | 2 |
| G11 | Ctrl+C | 1 |
| G12 | Backspace | 4 |
| G13 | Delete | 3 |
| G14 / G15 | Especial 0x10 / 0x11 | Especial 0x10 / 0x11 |
| DPI | 400 / **800** / 1600 / 3200 | 400 / **800** / 1600 / 3200 |
| Taxa | 250 Hz | 1000 Hz |

## Scripts (`scripts/`)

| Script | O que faz | Grava no mouse? |
|---|---|---|
| `trocar_perfil.py <1\|2>` | Troca o perfil ativo (usado pelos atalhos "Mouse Padrao" / "Mouse Vava" da área de trabalho) | Não |
| `ler_memoria.py <saida.json>` | Faz dump da memória on-board (diretório + perfis) | Não |
| `decodificar.py <dump.json>` | Mostra os botões/DPI do perfil 1 de um dump | Não |
| `gravar_vava.py <backup.json> [--dry]` | Grava o perfil Vava no slot 2 e habilita o slot. Salva o estado anterior em `backup.json`. `--dry` só simula | **Sim** (slot 2 e diretório) |
| `recuperar_wal_ghub.py <pasta>` | Extrai versões antigas do `settings.db` do G Hub a partir do `settings.db-wal` | Não |
| `hidpp.py` | Biblioteca comum (HID++, leitura/gravação de setores, CRC-CCITT) | — |

`hidpp.write_sector` recusa gravar o setor `0x0001` (perfil 1) como proteção.

## Formato da memória (G604)

- Setor = 255 bytes; últimos 2 bytes = CRC-CCITT (init `0xFFFF`, poly `0x1021`), big-endian.
- Setor `0x0000`: diretório, 4 bytes por perfil (`setor_hi setor_lo habilitado ff`), termina em `ffff`.
- Setores `0x0001`–`0x0005`: perfis. Byte 0 = report rate (1000/Hz), bytes 3–12 = DPIs (LE),
  bytes 32–95 = 16 botões × 4 bytes, 96–159 = botões com G-Shift, 160–207 = nome (UTF-16LE).
- Botão: `80 01 hh ll` mouse (bitmask), `80 02 mod key` teclado (HID usage), `80 03 hh ll` mídia,
  `90 xx` especial, `ff` desativado.

## Backups (`backups/`)

`GHUB_backup_20261014_1942/`:
- `settings.*` — banco do G Hub copiado em 14/10/2026 19:42.
- `g604_memoria.json` — dump da memória do mouse antes de qualquer gravação.
- `config_memoria_mouse.txt` — o dump acima decodificado.
- `g604_antes_vava.json` — setores 0000–0002 logo antes de gravar o Vava.

Para restaurar o estado original basta desabilitar o slot 2 (byte 6 do setor `0x0000` = `00`).
