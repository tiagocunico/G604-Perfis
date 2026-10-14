import json, sys
d = json.load(open(sys.argv[1]))
KEYS = {i: chr(ord('A') + i - 4) for i in range(4, 30)}
KEYS.update({30+i: str((i+1) % 10) for i in range(10)})
KEYS.update({0x28: 'Enter', 0x29: 'Esc', 0x2a: 'Backspace', 0x2b: 'Tab', 0x2c: 'Espaco', 0x4c: 'Delete',
             0x39: 'CapsLock', 0x49: 'Insert', 0x4a: 'Home', 0x4d: 'End', 0x4b: 'PgUp', 0x4e: 'PgDn',
             0x4f: 'Direita', 0x50: 'Esquerda', 0x51: 'Baixo', 0x52: 'Cima'})
KEYS.update({0x3a+i: f'F{i+1}' for i in range(12)})
KEYS.update({0x68+i: f'F{i+13}' for i in range(12)})
MODS = ['Ctrl', 'Shift', 'Alt', 'Win', 'RCtrl', 'RShift', 'AltGr', 'RWin']
MOUSE = ['Clique esquerdo', 'Clique direito', 'Clique do meio', 'Voltar', 'Avancar']
SPECIAL = {1: 'Scroll esquerda', 2: 'Scroll direita', 3: 'Bateria', 4: 'DPI +', 5: 'DPI ciclo +', 6: 'DPI -',
           7: 'DPI ciclo -', 8: 'DPI Shift', 9: 'Perfil seguinte', 0x0a: 'Ciclo de perfis', 0x0b: 'Perfil anterior',
           0x0c: 'Ciclo de perfis -', 0x0d: 'G-Shift', 0x0e: 'Trocar perfil'}
CONSUMER = {0xe2: 'Mudo', 0xe9: 'Volume +', 0xea: 'Volume -', 0xcd: 'Play/Pause', 0xb5: 'Proxima faixa',
            0xb6: 'Faixa anterior', 0xb7: 'Stop'}

def btn(b):
    t = b[0]
    if t == 0xff: return 'Desativado'
    if t == 0x80:
        st = b[1]
        if st == 1:
            m = (b[2] << 8) | b[3]
            return ' + '.join(MOUSE[i] if i < 5 else f'Botao{i+1}' for i in range(16) if m >> i & 1) or 'nada'
        if st == 2:
            mods = [MODS[i] for i in range(8) if b[2] >> i & 1]
            return 'Tecla ' + '+'.join(mods + [KEYS.get(b[3], hex(b[3]))])
        if st == 3:
            c = (b[2] << 8) | b[3]
            return 'Midia ' + CONSUMER.get(c, hex(c))
    if t == 0x90:
        return SPECIAL.get(b[1], 'Especial ' + hex(b[1]))
    if t == 0x00:
        return f'Macro (pagina {b[1]:02x}{b[2]:02x} offset {b[3]:02x})'
    return 'desconhecido ' + b.hex()

for sec in ['0001']:
    p = bytes.fromhex(d['sectors'][sec])
    print(f'== Perfil setor {sec}')
    rr = p[0]
    print('report rate byte:', rr, '-> ~%d Hz' % (1000 // rr if rr else 0))
    dpis = [p[3+2*i] | p[4+2*i] << 8 for i in range(5)]
    print('DPIs:', dpis, 'padrao idx', p[1], 'shift idx', p[2])
    try:
        nm = p[160:208].decode('utf-16-le').split('\0')[0]
        print('nome:', nm)
    except Exception: pass
    for i in range(16):
        b = p[32+4*i:36+4*i]; s = p[96+4*i:100+4*i]
        print(f'  idx{i:2d} (G{i+1:<2}) normal: {btn(b):<28} | G-Shift: {btn(s)}')
