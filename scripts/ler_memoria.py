# Somente leitura: HID++ 2.0 Root.getFeature, OnboardProfiles getInfo/getMode/getCurrentProfile/memoryRead
import hid, time, json, sys

ALLOWED_FN = {0x0000: {0}, 0x8100: {0, 2, 4, 5}, 0x0005: {0, 1}}

path = next(d['path'] for d in hid.enumerate(0x046d, 0xc539)
            if d['usage_page'] == 0xff00 and d['usage'] == 0x2)
dev = hid.device(); dev.open_path(path); dev.set_nonblocking(False)
DEVIDX = 1
feat_idx = {0x0000: 0}

def call(feature, fn, params=b''):
    assert fn in ALLOWED_FN[feature], 'funcao nao permitida'
    idx = feat_idx[feature]
    sw = 0x0a
    pkt = bytes([0x11, DEVIDX, idx, (fn << 4) | sw]) + params
    pkt = pkt + b'\0' * (20 - len(pkt))
    dev.write(pkt)
    t = time.time()
    while time.time() - t < 2:
        r = bytes(dev.read(20, 500))
        if not r: continue
        if r[1] == DEVIDX and r[2] == idx and r[3] == ((fn << 4) | sw):
            return r[4:]
        if r[1] == DEVIDX and r[2] == 0xff and r[3] == idx:
            raise RuntimeError('erro HID++ %d' % r[5])
    raise TimeoutError('sem resposta')

def feature(fid):
    r = call(0x0000, 0, bytes([fid >> 8, fid & 0xff]))
    if r[0] == 0: raise RuntimeError('feature %04x ausente' % fid)
    feat_idx[fid] = r[0]

feature(0x0005)
name = b''
n = call(0x0005, 0)[0]
while len(name) < n:
    name += call(0x0005, 1, bytes([len(name)]))[:n - len(name)]
print('dispositivo:', name.decode(errors='replace'))

feature(0x8100)
info = call(0x8100, 0)
print('info:', info[:16].hex())
mem_model, prof_fmt, macro_fmt, n_prof, n_prof_oob, n_buttons, n_sectors = info[:7]
sector_size = (info[7] << 8) | info[8]
print(f'perfis={n_prof} rom={n_prof_oob} botoes={n_buttons} setor={sector_size} fmt={prof_fmt}')
print('modo onboard:', call(0x8100, 2)[0], '(1=onboard 2=host)')
cur = call(0x8100, 4)
print('perfil atual:', cur[:2].hex())

def read_sector(sector, size):
    out = b''
    off = 0
    while off < size:
        o = min(off, size - 16)
        r = call(0x8100, 5, bytes([sector >> 8, sector & 0xff, o >> 8, o & 0xff]))[:16]
        out = out[:o] + r
        off = o + 16
    return out

dump = {'info': info.hex(), 'current': cur[:2].hex(), 'sectors': {}}
d0 = read_sector(0x0000, sector_size)
dump['sectors']['0000'] = d0.hex()
print('diretorio:', d0[:4 * max(n_prof, 1) + 4].hex())
for i in range(n_prof):
    e = d0[i*4:i*4+4]
    sec = (e[0] << 8) | e[1]
    if sec == 0xffff: break
    print(f'perfil {i+1}: setor {sec:04x} habilitado={e[2]}')
    dump['sectors'][f'{sec:04x}'] = read_sector(sec, sector_size).hex()
for i in range(n_prof_oob):
    sec = 0x0101 + i
    try:
        dump['sectors'][f'{sec:04x}'] = read_sector(sec, sector_size).hex()
    except Exception as ex:
        print('rom', hex(sec), ex)
json.dump(dump, open(sys.argv[1], 'w'), indent=1)
print('salvo em', sys.argv[1])
