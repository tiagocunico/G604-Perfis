# G604-Perfis

Configuração do mouse Logitech G604 direto na memória interna (on-board), sem G Hub.
Comunicação via HID++ 2.0 pelo receptor Lightspeed (`046d:c539`), feature `0x8100` (Onboard Profiles).

> **Aviso**
> - Projeto independente e **não oficial**: não tem nenhuma relação com a Logitech, nem é
>   endossado por ela. "Logitech", "G604", "G HUB" e "Lightspeed" são marcas da Logitech,
>   citadas só para identificar o hardware.
> - O app **grava na memória interna do mouse**. Ele faz backup antes, confere o CRC e lê
>   de volta depois de cada gravação, mas use **por sua conta e risco** (veja a [licença](LICENSE)).
> - Testado **apenas no G604 com o receptor Lightspeed** (`046d:c539`), no Windows 10.
>   O suporte a Linux foi escrito, mas **ainda não foi testado** num mouse real.
>   Bluetooth e outros modelos não são suportados.

Funciona no Windows e no Linux (Bazzite/KDE). Não rodar junto com G Hub/Onboard Memory Manager
(Windows) nem Piper/ratbagd/Solaar (Linux). Plano e status das fases em [PLANO.md](PLANO.md).

## Instalar

| Sistema | Comando |
|---|---|
| Windows | `powershell -ExecutionPolicy Bypass -File instalar\windows.ps1` |
| Bazzite / Linux | `./instalar/linux.sh` (pede `sudo` só para a regra udev) |

Os dois instalam a bandeja para iniciar junto com o sistema e o comando `g604`.
Para desfazer: `-Remover` (Windows) ou `--remover` (Linux).

## Usar

**Bandeja**: o ícone mostra a inicial e a cor do perfil ativo. Clique simples alterna o perfil;
o menu tem os perfis, liga/desliga a troca automática, abre o editor e abre/recarrega o `perfis.toml`.

**Editor** ("Editar perfis…" no menu da bandeja, ou `python -m g604.editor`):
- nome, taxa, até 5 DPIs (padrão e shift) e a ação de cada botão G1–G15
  (botão do mouse, tecla, mídia, especial ou bytes brutos);
- **Capturar**: clique e aperte a tecla/combinação no teclado; ou digite (`Ctrl+Shift+S`);
- embaixo aparece a lista do que vai mudar; "Gravar no mouse" pede confirmação, faz backup,
  grava e lê de volta. Mudar só o nome altera apenas o `perfis.toml`;
- slots vazios: "Habilitar este slot" copia um perfil existente como ponto de partida e já
  cria a entrada no `perfis.toml`.

Os especiais com "(não testado)" usam códigos do libratbag ainda não confirmados no G604.

**Linha de comando** (`g604 ...` ou `python -m g604 ...`):

| Comando | O que faz | Grava na memória? |
|---|---|---|
| `status` | slots do mouse e qual está ativo | não |
| `trocar vava` | ativa um perfil (chave, nome ou nº do slot) | não |
| `mostrar [perfil]` | botões, DPI e taxa de um perfil | não |
| `backup` | salva a memória em `backups/automaticos/` | não |
| `restaurar <arquivo>` | mostra o que mudaria; com `--confirmar` grava (faz backup antes e confere depois) | **sim** |
| `processos [filtro]` | lista processos abertos, para criar regras | não |
| `vigia` | troca automática sem a bandeja | não |

`--simulado` em qualquer comando (e na bandeja) usa um G604 simulado e não toca no mouse.

## Adicionar perfis e jogos

Tudo fica no [`perfis.toml`](perfis.toml), compartilhado entre os PCs pelo git:

```toml
[perfis.csgo]          # novo perfil: aponta para um slot da memória (precisa estar habilitado)
slot = 3
nome = "CS"

[[regras]]             # novo jogo: processo → perfil
processo = ["cs2.exe", "cs2"]
perfil = "csgo"
```

Depois, "Recarregar perfis.toml" no menu da bandeja. Para achar o nome do processo: `g604 processos <parte do nome>`.

## Testes

`python -m unittest discover -s tests -t .` — todos offline, com o mouse simulado alimentado pelos dumps reais.

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

## Scripts avulsos (`scripts/`)

Versões originais usadas na recuperação de 14/10/2026. Os atalhos "Mouse Padrao"/"Mouse Vava"
da área de trabalho ainda usam o `trocar_perfil.py`; o pacote `g604/` substitui o resto.

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

## Licença

[MIT](LICENSE). Sem garantias: veja o aviso no topo.
