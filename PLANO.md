# Plano — app de perfis do G604

Objetivo: controlar os perfis on-board do G604 sem G Hub, no Windows e no Bazzite (KDE),
com troca automática de perfil quando um jogo abre.

## Decisões

- **Python**, reaproveitando o protocolo HID++ já validado nos `scripts/`.
- **Transporte por sistema**: Windows usa `hidapi`; Linux fala direto com `/dev/hidraw*`
  (o backend libusb do `hidapi` desconectaria o mouse do sistema).
- **Configuração em `perfis.toml`** no repositório: os dois PCs usam a mesma, via git.
  Adicionar perfil ou jogo = adicionar um bloco no arquivo.
- **Bandeja + vigia no mesmo processo** (PySide6). No Bazzite o uso é no desktop KDE,
  então não precisa de serviço separado para o Modo Jogo.
- Receptor Lightspeed `046d:c539` nos dois PCs (sem Bluetooth).
- Trocar de perfil não grava na memória; só gravações de setor (restaurar/aplicar) gravam,
  sempre com backup antes, checagem de CRC e leitura de volta.

## Estrutura

```
g604/
├── transporte.py   Windows: hidapi | Linux: /dev/hidraw | Simulado (testes)
├── hidpp.py        HID++ 2.0: features, Onboard Profiles (0x8100), CRC-CCITT
├── perfil.py       setor ⇄ Perfil (botões, DPI, taxa, nome) preservando bytes desconhecidos
├── mouse.py        API: perfil ativo, trocar, backup, restaurar (com verificação)
├── config.py       leitura do perfis.toml
├── vigia.py        regras "processo → perfil"
├── cli.py          g604 status | trocar | mostrar | backup | restaurar | vigia
├── bandeja.py      ícone na bandeja com menu de perfis e troca automática
└── editor.py       janela de edição de perfis (aberta pela bandeja)
instalar/           windows.ps1, linux.sh, regra udev, autostart do KDE
tests/              testes offline com mouse simulado alimentado pelos dumps reais
```

## Fases

| Fase | Conteúdo | Status |
|---|---|---|
| 0 | Pacote, transporte por SO, testes offline com mouse simulado | feito |
| 1 | CLI nos dois sistemas; regra udev no Bazzite | Windows testado no mouse real; falta Bazzite |
| 2 | Vigia por processo + bandeja (PySide6), início automático | Windows testado no mouse real e instalado; falta Bazzite |
| 3 | Editor visual (botões, DPI, taxa, nome, habilitar slots) | feito; gravação testada no mouse real |
| 4 | `.exe` único no Windows (PyInstaller) | a fazer |

Fora do escopo: macros na memória do mouse, iluminação (o G604 não tem RGB).

## Pendências

- Testar no Bazzite: `./instalar/linux.sh`, `g604 status`, `g604 trocar`, bandeja.
- Windows (14/10/2026): status/mostrar/backup/trocar/vigia/bandeja validados no mouse real;
  memória real idêntica ao dump simulado (`tests/dados/g604_atual.json`). `restaurar` só
  validado no simulador (no real, apenas a etapa sem `--confirmar`).
- Descobrir o que fazem os especiais `0x10`/`0x11` (G14/G15) e confirmar os demais
  códigos especiais (DPI+, ciclo de perfis…) no G604.
- Editor (15/10/2026): gravação validada no mouse real (taxa do Vava 1000→500→1000, memória
  final idêntica à inicial). Habilitar slot novo só testado no simulador.
- Editor ainda não edita os botões com G-Shift (são preservados) nem as regras de jogos.
- Valorant não roda no Linux (Vanguard); no Bazzite as regras valem para outros jogos.
- Não rodar junto com G Hub/OMM (Windows) nem Piper/ratbagd/Solaar (Linux).
