"""IPS patches: writing one from a stock and a patched ROM, and applying one."""

MAX_IPS_RECORD = 0xFFFF
IPS_MERGE_GAP = 8              # bridge gaps this short: a new record costs 5 bytes of header
IPS_RLE_MIN = 12               # shortest run of one byte that an RLE record beats
IPS_EOF_OFFSET = 0x454F46       # the bytes "EOF": a record offset here ends the patch


def _run(data, start, end, limit):
    """How many bytes from start, stopping at end or limit, equal data[start]."""
    n = 1
    while start + n < end and data[start + n] == data[start] and n < limit:
        n += 1
    return n


def make_ips(original, patched, rle=True):
    """An IPS patch from original to patched. The patched image may be longer;
    the extra bytes become records past the end of the original.

    With rle=False every record is a plain data record. Hermano and Roguecraft
    build that way, which keeps their committed IPS files as they are."""
    if len(patched) < len(original):
        raise SystemExit("IPS generation expects the patched image to be at least as long")
    runs = []
    for i in range(len(patched)):
        if i < len(original) and patched[i] == original[i]:
            continue
        if runs and i - runs[-1][1] <= IPS_MERGE_GAP:
            runs[-1][1] = i + 1
        else:
            runs.append([i, i + 1])
    out = bytearray(b"PATCH")

    def header(offset):
        return bytes([(offset >> 16) & 0xFF, (offset >> 8) & 0xFF, offset & 0xFF])

    for start, end in runs:
        while start < end:
            if start == IPS_EOF_OFFSET:
                start -= 1      # this record also rewrites the byte before, with its patched value
            same = _run(patched, start, end, MAX_IPS_RECORD) if rle else 1
            if same >= IPS_RLE_MIN:
                out += header(start) + b"\x00\x00" + bytes([same >> 8, same & 0xFF, patched[start]])
                start += same
                continue
            stop = start + 1
            while stop < end and stop - start < MAX_IPS_RECORD:
                if rle and stop != IPS_EOF_OFFSET and _run(patched, stop, end, IPS_RLE_MIN) >= IPS_RLE_MIN:
                    break
                stop += 1
            out += header(start) + bytes([(stop - start) >> 8, (stop - start) & 0xFF]) + patched[start:stop]
            start = stop
    out += b"EOF"
    return bytes(out)


def apply_ips(original, ips, fill=0x00):
    """A plain IPS applier (data and RLE records), independent of make_ips. A
    record past the end grows the file, and any gap before it is filled with
    fill."""
    assert ips[:5] == b"PATCH"
    out, i = bytearray(original), 5
    while ips[i:i + 3] != b"EOF":
        offset = int.from_bytes(ips[i:i + 3], "big")
        size = int.from_bytes(ips[i + 3:i + 5], "big")
        i += 5
        if size == 0:
            size = int.from_bytes(ips[i:i + 2], "big")
            data = bytes([ips[i + 2]]) * size
            i += 3
        else:
            data = ips[i:i + size]
            i += size
        if len(out) < offset + size:
            out.extend(bytes([fill]) * (offset + size - len(out)))
        out[offset:offset + size] = data
    return bytes(out)
