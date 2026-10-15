#!/usr/bin/env bash
# Instala o g604 no Linux (testado para Bazzite/Fedora Atomic com KDE).
#   ./instalar/linux.sh            instala (pede sudo só para a regra udev)
#   ./instalar/linux.sh --remover  desinstala
# Tudo fica na pasta do usuário; /etc/udev é gravável mesmo no Bazzite imutável.
set -euo pipefail

REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
VENV="$HOME/.local/share/g604/venv"
REGRA="/etc/udev/rules.d/70-g604.rules"
AUTOSTART="$HOME/.config/autostart/g604-bandeja.desktop"
MENU="$HOME/.local/share/applications/g604-bandeja.desktop"
BIN="$HOME/.local/bin/g604"

if [[ "${1:-}" == "--remover" ]]; then
    rm -rf "$VENV" "$AUTOSTART" "$MENU" "$BIN"
    [[ -f "$REGRA" ]] && sudo rm -f "$REGRA" && sudo udevadm control --reload-rules
    echo "g604 removido."
    exit 0
fi

echo "==> ambiente Python em $VENV"
python3 -m venv "$VENV"
"$VENV/bin/pip" install -q --upgrade pip
"$VENV/bin/pip" install -q -e "$REPO[bandeja]"

echo "==> regra udev ($REGRA)"
if ! cmp -s "$REPO/instalar/70-g604.rules" "$REGRA" 2>/dev/null; then
    sudo install -m 644 "$REPO/instalar/70-g604.rules" "$REGRA"
    sudo udevadm control --reload-rules
    sudo udevadm trigger --subsystem-match=hidraw
fi

echo "==> comando 'g604' em $BIN"
mkdir -p "$(dirname "$BIN")"
ln -sf "$VENV/bin/g604" "$BIN"

echo "==> bandeja no menu e na inicialização do KDE"
mkdir -p "$(dirname "$AUTOSTART")" "$(dirname "$MENU")"
cat > "$MENU" <<EOF
[Desktop Entry]
Type=Application
Name=G604 Perfis
Comment=Perfis do mouse Logitech G604
Exec=$VENV/bin/g604-bandeja
Icon=input-mouse
Categories=Utility;
EOF
cp "$MENU" "$AUTOSTART"

for svc in ratbagd; do
    if systemctl is-active --quiet "$svc" 2>/dev/null; then
        echo "AVISO: o serviço $svc (Piper) está ativo e pode disputar o mouse."
    fi
done
if pgrep -x solaar >/dev/null; then
    echo "AVISO: o Solaar está aberto e pode disputar o mouse."
fi

echo
echo "Pronto. Teste com:  g604 status"
echo "Se der 'sem permissão', tire e recoloque o receptor USB."
echo "A bandeja abre no próximo login, ou agora com: $VENV/bin/g604-bandeja &"
