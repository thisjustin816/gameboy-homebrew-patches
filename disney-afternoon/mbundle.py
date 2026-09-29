"""Read Digital Eclipse .mbundle files: a binary plist dict of name -> file bytes.

Their writer departs from the bplist format in two ways, so plistlib rejects them:
the trailer's top-object field is a byte offset, not an index, and the trailer
overwrites the end of the offset table. Objects are stored back to back, so any
offsets lost under the trailer are recovered by walking on from the last good one.
"""
import struct, sys, os

def read(path):
    d = open(path, 'rb').read()
    assert d[:8] == b'bplist00'
    off_size, ref_size, nobj, top, table = struct.unpack('>6xBBQQQ', d[-32:])
    end = len(d) - 32

    def length(p, low):
        if low != 0xF: return low, p
        n = 1 << (d[p] & 0xF)
        return int.from_bytes(d[p+1:p+1+n], 'big'), p + 1 + n

    def span(p):
        """Return (type, payload start, payload end) of the object at p."""
        m = d[p]; hi, low = m >> 4, m & 0xF
        n, q = length(p + 1, low)
        size = {0x4: n, 0x5: n, 0x6: 2*n, 0xD: 2*n*ref_size}[hi]
        return hi, q, q + size, n

    offs = [int.from_bytes(d[table + i*off_size: table + (i+1)*off_size], 'big')
            for i in range((end - table) // off_size)]
    top_at = next(p for p in (top, top + 8) if d[p] >> 4 == 0xD)
    hi, q, stop, n = span(top_at)
    refs = [int.from_bytes(d[q + k*ref_size: q + (k+1)*ref_size], 'big') for k in range(2*n)]
    while len(offs) <= max(refs):                 # recover offsets hidden under the trailer
        offs.append(span(offs[-1])[2])

    def obj(i):
        hi, q, stop, _ = span(offs[i])
        if hi == 0x4: return d[q:stop]
        if hi == 0x5: return d[q:stop].decode('ascii')
        if hi == 0x6: return d[q:stop].decode('utf-16-be')
        raise ValueError(f'unexpected object type {hi:#x}')
    return {obj(refs[k]): obj(refs[n + k]) for k in range(n)}

if __name__ == '__main__':
    files = read(sys.argv[1]); out = sys.argv[2]; os.makedirs(out, exist_ok=True)
    for name, data in files.items():
        open(os.path.join(out, name.replace('/', '_')), 'wb').write(data)
    print(len(files), 'files ->', out)
