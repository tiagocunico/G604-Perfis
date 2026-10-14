# Uso: python gravar_vava.py <arquivo_backup.json> [--dry]
# Grava o perfil Vava no slot 2 (copia do perfil 1 com as teclas trocadas) e habilita o slot 2.
import sys, os, json, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from hidpp import G604, crc_ok

dry = '--dry' in sys.argv
m = G604()
print('setor', m.sector_size, 'modo', m.get_mode(), 'perfil atual', m.get_profile().hex())
d0 = m.read_sector(0x0000); p1 = m.read_sector(0x0001); p2_old = m.read_sector(0x0002)
assert crc_ok(d0) and crc_ok(p1), 'CRC atual invalido, abortando'
json.dump({'0000': d0.hex(), '0001': p1.hex(), '0002': p2_old.hex()},
          open(sys.argv[1], 'w'), indent=1)
print('diretorio atual:', d0[:24].hex())
print('perfil1 botoes:', p1[32:96].hex())

KEY = {'X': 0x1b, 'T': 0x17, 'G': 0x0a, 'C': 0x06, 'E': 0x08, 'Q': 0x14,
       '1': 0x1e, '2': 0x1f, '3': 0x20, '4': 0x21}
vava = {3: 'X', 4: 'T', 5: 'G', 6: 'C', 7: 'E', 8: 'Q', 9: '2', 10: '1', 11: '4', 12: '3'}
p2 = bytearray(p1)
p2[0] = 1                                  # 1000 Hz
for i, k in vava.items():
    p2[32 + 4*i: 36 + 4*i] = bytes([0x80, 0x02, 0x00, KEY[k]])
name = 'Vava'.encode('utf-16-le')
p2[160:208] = name + b'\0' * (48 - len(name))

dnew = bytearray(d0)
assert dnew[4:6] == b'\x00\x02', 'entrada do perfil 2 inesperada'
dnew[6] = 1                                # habilita perfil 2

print('perfil2 novo botoes:', bytes(p2[32:96]).hex())
print('diretorio novo:', bytes(dnew[:24]).hex())
if dry:
    print('DRY RUN, nada gravado'); sys.exit()

m.write_sector(0x0002, bytes(p2))
time.sleep(0.3)
m.write_sector(0x0000, bytes(dnew))
time.sleep(0.3)
r2 = m.read_sector(0x0002); r0 = m.read_sector(0x0000); r1 = m.read_sector(0x0001)
print('verif perfil2:', 'OK' if r2[:-2] == bytes(p2[:-2]) and crc_ok(r2) else 'DIFERENTE')
print('verif diretorio:', 'OK' if r0[:-2] == bytes(dnew[:-2]) and crc_ok(r0) else 'DIFERENTE')
print('verif perfil1 intacto:', 'OK' if r1 == p1 else 'MUDOU')
