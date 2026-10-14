import hid, time

def crc_ccitt(data):
    crc = 0xFFFF
    for b in data:
        crc ^= b << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021) & 0xFFFF if crc & 0x8000 else (crc << 1) & 0xFFFF
    return crc

def crc_ok(sector):
    return crc_ccitt(sector[:-2]) == (sector[-2] << 8 | sector[-1])

class G604:
    def __init__(self):
        path = next(d['path'] for d in hid.enumerate(0x046d, 0xc539)
                    if d['usage_page'] == 0xff00 and d['usage'] == 0x2)
        self.dev = hid.device(); self.dev.open_path(path)
        self.idx = {0x0000: 0}
        self.feature(0x8100)
        info = self.call(0x8100, 0)
        self.n_prof = info[3]
        self.sector_size = info[7] << 8 | info[8]

    def call(self, feature, fn, params=b''):
        idx = self.idx[feature]; sw = 0x0a
        pkt = bytes([0x11, 1, idx, (fn << 4) | sw]) + bytes(params)
        self.dev.write(pkt + b'\0' * (20 - len(pkt)))
        t = time.time()
        while time.time() - t < 3:
            r = bytes(self.dev.read(20, 500))
            if not r: continue
            if r[1] == 1 and r[2] == idx and r[3] == ((fn << 4) | sw):
                return r[4:]
            if r[1] == 1 and r[2] == 0xff and r[3] == idx:
                raise RuntimeError('erro HID++ %d (fn %d)' % (r[5], fn))
        raise TimeoutError('sem resposta')

    def feature(self, fid):
        r = self.call(0x0000, 0, bytes([fid >> 8, fid & 0xff]))
        if r[0] == 0: raise RuntimeError('feature ausente')
        self.idx[fid] = r[0]

    def read_sector(self, sector):
        size = self.sector_size; out = b''; off = 0
        while off < size:
            o = min(off, size - 16)
            r = self.call(0x8100, 5, bytes([sector >> 8, sector & 0xff, o >> 8, o & 0xff]))[:16]
            out = out[:o] + r; off = o + 16
        return out

    def write_sector(self, sector, data):
        size = self.sector_size
        assert len(data) == size and sector != 0x0001, 'protecao: nunca gravar o perfil 1'
        data = bytearray(data)
        c = crc_ccitt(data[:-2]); data[-2] = c >> 8; data[-1] = c & 0xff
        self.call(0x8100, 6, bytes([sector >> 8, sector & 0xff, 0, 0, size >> 8, size & 0xff]))
        buf = bytes(data) + b'\0' * (-len(data) % 16)
        for i in range(0, len(buf), 16):
            self.call(0x8100, 7, buf[i:i+16])
        self.call(0x8100, 8)

    def get_mode(self): return self.call(0x8100, 2)[0]
    def get_profile(self): return self.call(0x8100, 4)[:2]
    def set_profile(self, n): return self.call(0x8100, 3, bytes([0, n]))
