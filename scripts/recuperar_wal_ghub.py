import struct, sqlite3, os, sys, hashlib, json
d = sys.argv[1]
base = open(os.path.join(d, 'settings.db'), 'rb').read()
wal = open(os.path.join(d, 'settings.db-wal'), 'rb').read()
magic, ver, psz, ckseq, s1, s2 = struct.unpack('>IIIIII', wal[:24])
print('pagesize', psz, 'salts', s1, s2)
fsz = 24 + psz
frames = []
off = 32
while off + fsz <= len(wal):
    pg, commit, fs1, fs2 = struct.unpack('>IIII', wal[off:off+16])
    frames.append((pg, commit, (fs1, fs2), wal[off+24:off+fsz]))
    off += fsz
print('frames', len(frames))
groups = {}
for f in frames:
    groups.setdefault(f[2], 0)
    groups[f[2]] += 1
print('salt groups', groups)

out = os.path.join(d, 'snapshots'); os.makedirs(out, exist_ok=True)
seen = {}

def extract(img, label):
    p = os.path.join(out, 'tmp.db')
    open(p, 'wb').write(img)
    try:
        c = sqlite3.connect(p)
        rows = c.execute('select _id,_date_created,file from data').fetchall()
        c.close()
    except Exception as e:
        return
    for r in rows:
        blob = r[2]
        h = hashlib.md5(blob).hexdigest()
        if h not in seen:
            seen[h] = label
            fn = os.path.join(out, f'{len(seen):03d}_{label}.json')
            open(fn, 'wb').write(blob)
            print('new version', fn, r[0], r[1], len(blob))

extract(base, 'base')
# replay each salt group independently on top of base, snapshot at each commit
for salt in groups:
    img = bytearray(base)
    n = 0
    for pg, commit, fs, data in frames:
        if fs != salt:
            continue
        need = pg * psz
        if len(img) < need:
            img.extend(b'\0' * (need - len(img)))
        img[(pg-1)*psz:pg*psz] = data
        if commit:
            n += 1
            extract(bytes(img[:commit*psz]), f's{salt[0]}_c{n}')
