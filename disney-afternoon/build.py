#!/usr/bin/env python3
"""Build a Disney Afternoon Collection multicart for the Game Boy.

Four Capcom MBC1 games go into one 2 MiB MBC1 ROM, one per 512 KiB quarter.
DuckTales holds quarter 0, and a splash and game menu live in its unused banks.
Picking a game switches MBC1 to mode 1 with that game's quarter in the upper
bank bits, which puts its own bank 0 at $0000, then starts it from the state
the boot ROM leaves. B on a game's title screen goes back to the menu: each
game gets a small patch at the spot where its title checks for START.

Inputs are checked by md5: the four USA ROMs, and bundleMain.mbundle from the
PC Disney Afternoon Collection for the logos. The menu font is DuckTales 2's
own, read from its title screen in PyBoy.

    python3 build.py DUCKTALES DUCKTALES2 TALESPIN DARKWING bundleMain.mbundle -o out.gb
"""
import argparse, hashlib, io, os, sys
from PIL import Image, ImageEnhance

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
from asm import assemble
import mbundle

BANK = 0x4000
QUARTER = 0x80000
ROM_SIZE = 0x200000

# Menu order is quarter order.
#
# title: where B is added to the title screen. site is (bank, address) of the
# bytes the patch replaces with a call, and 'replaces' what must be there. new
# is where the game keeps newly pressed buttons (B is bit 1). The check goes in
# free padding in the game's bank 0, from pad to $0100. The kinds are:
#   menu    the title's menu loop, shared with other menus, told apart by HL
#   loop    a loop only the title runs
#   script  the script interpreter's button-test op; ops lists the title's ops
#           as (HL at the operands, mask, branch target) as the script holds them
GAMES = [
    dict(key='ducktales', md5='785441d3d75913393807b10b3194dc48', size=0x10000,
         label='DUCKTALES', art='GameLogoDuckTales.png',
         title=dict(kind='menu', site=(2, 0x6130), replaces='F08CE609', new=0x8C,
                    start_mask=0x09, hl=0x029C, pad=None)),   # pad: after the boot hook
    dict(key='ducktales2', md5='b4e5876c5acedd12b62e25a12973a4ae', size=0x20000,
         label='DUCKTALES 2', art='GameLogoDuckTales2.png',
         title=dict(kind='script', site=(0, 0x1651), replaces='0E922A', new=0x93,
                    ops=[(0x4DC6, 0x08, 0x4DCF), (0x4DFC, 0x09, 0x4E05)], pad=0x0061)),
    dict(key='talespin', md5='26c65da146faa09505c554447792e493', size=0x20000,
         label='TALESPIN', art='GameLogoTaleSpin.png',
         title=dict(kind='loop', site=(1, 0x4034), replaces='FAA2C0E608', new=0xC0A2,
                    start_mask=0x08, pad=0x0063)),
    dict(key='darkwing', md5='7d776329212fa7cc2b00c5a46f06dd92', size=0x20000,
         label='DARKWING DUCK', art='GameLogoDarkwingDuck.png',
         title=dict(kind='script', site=(0, 0x10F5), replaces='0E922A', new=0x93,
                    ops=[(0x78B1, 0x08, 0x78B8)], pad=0x0061)),
]
BUNDLE_MD5 = 'c20f738bd6e913e2b669cb15d87d697c'   # PC release, bundleMain.mbundle
SPLASH_ART = 'LogoDisneyAfternoon.png'
FONT_MD5 = '28356ffe0f0535fed3193648ce142cca'      # the glyphs font_glyphs picks out

# DuckTales bank 0: the entry point we redirect, and the padding the boot hook uses.
DT_ENTRY = bytes([0x00, 0xC3, 0x50, 0x01])        # nop / jp $0150
DT_START = 0x0150
HOOK = 0x0061
HOOK_END = 0x0100

MENU_BANK = 4
SPLASH_BANK = 5
FIRST_GAME_BANK = 6
MENU_STACK = 0xDFF0
SAVED_REGS = 0xFFF6
LOADER = 0xC100
LAUNCH = 0xFF80

# Shades 0-3, lightest first, as the menu's BGP ($E4) shows them.
SHADES = [(255, 255, 255), (170, 170, 170), (85, 85, 85), (0, 0, 0)]


def md5(data):
    return hashlib.md5(data).hexdigest()


def load_checked(path, want, what):
    data = open(path, 'rb').read()
    if md5(data) != want:
        sys.exit(f'{path}: md5 {md5(data)} is not the supported {what} ({want})')
    return data


# ---- font ---------------------------------------------------------------------

def font_glyphs(dt2_rom):
    """Capture DuckTales 2's font from VRAM on its title screen.

    Returns {char: 16 bytes of 2bpp}. The capture is a fixed cold boot with one
    START press, so it is the same every run; the md5 check makes sure of it.
    """
    import tempfile
    from pyboy import PyBoy
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'dt2.gb')
        open(path, 'wb').write(dt2_rom)
        pb = PyBoy(path, window='null', sound_emulated=False)
        pb.tick(400, False)
        pb.button('start', 4)
        pb.tick(124, False)
        vram = bytes(pb.memory[0x8000:0x9FFF]) + bytes([pb.memory[0x9FFF]])
        pb.stop(save=False)
    glyphs = {' ': bytes(16)}
    for ch in 'ABCDEFGHIJKLMNOPQRSTUVWXYZ':
        a = 0x1000 + (ord(ch) - 64) * 16          # tiles $01-$1A of the $9000 block
        glyphs[ch] = vram[a:a + 16]
    for d in range(10):
        a = 0x0F00 + d * 16                        # tiles $F0-$F9
        glyphs[str(d)] = vram[a:a + 16]
    glyphs['>'] = vram[0x1000 + 0x39 * 16:0x1000 + 0x3A * 16]   # the menu arrow
    digest = md5(b''.join(glyphs[k] for k in sorted(glyphs)))
    if digest != FONT_MD5:
        sys.exit(f'font capture md5 {digest} does not match {FONT_MD5}')
    return glyphs


def draw_glyph(img, glyph, px, py):
    for y in range(8):
        lo, hi = glyph[2 * y], glyph[2 * y + 1]
        for x in range(8):
            c = ((lo >> (7 - x)) & 1) | (((hi >> (7 - x)) & 1) << 1)
            img.putpixel((px + x, py + y), SHADES[c])


def draw_text(img, glyphs, col, row, text):
    for j, ch in enumerate(text):
        draw_glyph(img, glyphs[ch], (col + j) * 8, row * 8)


# ---- art ----------------------------------------------------------------------

def to_shades(png, size, contrast):
    """Scale a PC image into size and map it to four shades; transparency is white."""
    im = Image.open(io.BytesIO(png)).convert('RGBA')
    im = im.crop(im.getbbox())
    im.thumbnail(size, Image.LANCZOS)
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    grey = ImageEnhance.Contrast(bg.convert('L')).enhance(contrast)
    pal = Image.new('P', (1, 1))
    pal.putpalette(sum([list(s) for s in SHADES[::-1]], []) + [0] * 756)
    return grey.convert('RGB').quantize(palette=pal, dither=Image.Dither.NONE).convert('RGB')


def snap(x):
    return x - x % 8


def splash_screen(art, glyphs):
    img = Image.new('RGB', (160, 144), SHADES[0])
    logo = to_shades(art[SPLASH_ART], (144, 104), 1.2)
    img.paste(logo, (snap((160 - logo.width) // 2), 8))
    draw_text(img, glyphs, 4, 15, 'PRESS START')
    return img


def game_screen(art, glyphs, sel):
    img = Image.new('RGB', (160, 144), SHADES[0])
    logo = to_shades(art[GAMES[sel]['art']], (160, 80), 1.3)
    img.paste(logo, (snap((160 - logo.width) // 2), 8 + snap((80 - logo.height) // 2)))
    for i, g in enumerate(GAMES):
        if i == sel:
            draw_text(img, glyphs, 3, 12 + i, '>')
        draw_text(img, glyphs, 5, 12 + i, g['label'])
    return img


def screens(roms, art):
    """The five screens in bank order: splash, then each game highlighted."""
    glyphs = font_glyphs(roms[1])
    return [splash_screen(art, glyphs)] + [game_screen(art, glyphs, i) for i in range(len(GAMES))]


def tileize(img):
    """Return (tile data, 18x20 map) with the blank tile first, so index 0 is blank."""
    index = {SHADES[i]: i for i in range(4)}
    tiles, cells = [bytes(16)], []
    for ty in range(18):
        for tx in range(20):
            t = bytearray()
            for y in range(8):
                lo = hi = 0
                for x in range(8):
                    c = index[img.getpixel((tx * 8 + x, ty * 8 + y))]
                    lo |= (c & 1) << (7 - x)
                    hi |= (c >> 1) << (7 - x)
                t += bytes([lo, hi])
            t = bytes(t)
            if t not in tiles:
                tiles.append(t)
            cells.append(tiles.index(t))
    if len(tiles) > 256:
        sys.exit(f'screen needs {len(tiles)} tiles, the limit is 256')
    return b''.join(tiles), bytes(cells)


def screen_bank(img):
    tiles, cells = tileize(img)
    blob = len(tiles).to_bytes(2, 'little') + tiles + cells
    assert len(blob) <= BANK
    return blob


# ---- code ---------------------------------------------------------------------

def src(name):
    return open(os.path.join(HERE, name)).read()


def consts(**kw):
    return ''.join(f'{k} = ${v:X}\n' for k, v in kw.items())


def db_lines(label, data):
    out = [f'{label}:']
    for i in range(0, len(data), 16):
        out.append('    db ' + ','.join(f'${b:02X}' for b in data[i:i + 16]))
    return '\n'.join(out) + '\n'


def build_code():
    """Assemble the boot hook, loader, launch stub and menu.

    Returns (boot, menu, labels); labels merges the menu's and the launch stub's.
    """
    common = consts(MENU_BANK=MENU_BANK, MENU_STACK=MENU_STACK, SAVED_REGS=SAVED_REGS)
    boot, _, _ = assemble(common + src('boot.asm'), HOOK)
    loader, _, _ = assemble(common + src('loader.asm'), LOADER)
    launch, lab, _ = assemble(common + src('launch.asm'), LAUNCH)
    games = bytearray()
    for q, g in enumerate(GAMES):
        target = DT_START if q == 0 else 0x0100
        games += bytes([q, 1 if q else 0, target & 0xFF, target >> 8])
    menu_src = (common + consts(
        SPLASH_BANK=SPLASH_BANK, FIRST_GAME_BANK=FIRST_GAME_BANK,
        LOADER=LOADER, LOADER_LEN=len(loader), LAUNCH=LAUNCH, LAUNCH_LEN=len(launch),
        P_QUARTER=lab['launch'] + 1, P_MODE=lab['launch'] + 6,
        P_TARGET=lab['jump'] + 1, P_TARGET_HI=lab['jump'] + 2)
        + src('menu.asm') + db_lines('loader_src', loader)
        + db_lines('launch_src', launch) + db_lines('games', games))
    menu, menu_lab, _ = assemble(menu_src, 0x4000)
    # the patch points must be the operands the stub was assembled with
    assert launch[0] == 0x3E and launch[5] == 0x3E, 'launch stub no longer starts ld a,q / ... / ld a,m'
    assert launch[lab['jump'] - LAUNCH] == 0xC3
    if HOOK + len(boot) > HOOK_END:
        sys.exit(f'boot hook is {len(boot)} bytes, only {HOOK_END - HOOK} are free')
    if len(launch) > SAVED_REGS - LAUNCH:
        sys.exit('launch stub would overlap the saved registers')
    assert len(menu) <= BANK
    return boot, menu, {**menu_lab, **lab}


def title_patches(roms, labels, boot_len):
    """Return [(file offset, bytes)] adding B-to-menu to each game's title screen."""
    patches = []
    for q, (g, rom) in enumerate(zip(GAMES, roms)):
        t = g['title']
        bank, addr = t['site']
        site = bank * BANK + addr - (BANK if bank else 0)
        want = bytes.fromhex(t['replaces'])
        if rom[site:site + len(want)] != want:
            sys.exit(f"{g['key']}: the title check at {bank:02X}:{addr:04X} is not the expected code")
        pad = HOOK + boot_len if t['pad'] is None else t['pad']
        if any(rom[pad:HOOK_END]):
            sys.exit(f"{g['key']}: ${pad:04X}-$00FF is not free padding")
        stub, _, _ = assemble(consts(MENU_BANK=MENU_BANK, GAME=q, BACK=labels['back'])
                              + src('menu_stub.asm'), 0xFF80)
        c = consts(NEW=t['new'], MENU_STUB_LEN=len(stub))
        if t['kind'] == 'menu':
            c += consts(START_MASK=t['start_mask'], TITLE_HL_HI=t['hl'] >> 8, TITLE_HL_LO=t['hl'] & 0xFF)
        elif t['kind'] == 'loop':
            c += consts(START_MASK=t['start_mask'])
        text = c + src(f"title_{t['kind']}.asm") + src('go_menu.asm') + db_lines('menu_stub', stub)
        if t['kind'] == 'script':
            ops = bytearray()
            for hl, mask, target in t['ops']:
                assert hl & 0xFF, 'a zero low byte would end the list'
                assert rom[bank_of_script(rom, hl, mask, target)] == 0x11
                ops += bytes([hl & 0xFF, hl >> 8, mask, target & 0xFF, target >> 8])
            text += db_lines('title_ops', ops + b'\0')
        code, lab, _ = assemble(text, pad)
        if pad + len(code) > HOOK_END:
            sys.exit(f"{g['key']}: title check is {len(code)} bytes, only {HOOK_END - pad} are free")
        call = bytes([0xCD, lab['title_check'] & 0xFF, lab['title_check'] >> 8])
        base = q * QUARTER
        patches.append((base + pad, code))
        patches.append((base + site, call + bytes(len(want) - 3)))   # nop out the rest
    return patches


def bank_of_script(rom, hl, mask, target):
    """File offset of the op byte for a title op; exactly one bank must hold it."""
    found = [b * BANK + hl - BANK - 1 for b in range(1, len(rom) // BANK)
             if rom[b * BANK + hl - BANK:b * BANK + hl - BANK + 4]
             in (bytes([o, mask, target & 0xFF, target >> 8]) for o in (0, 1))]
    if len(found) != 1:
        sys.exit(f'title op at ${hl:04X} found in {len(found)} banks, expected one')
    return found[0]


# ---- layout -------------------------------------------------------------------

def header_checksum(rom):
    x = 0
    for b in rom[0x134:0x14D]:
        x = (x - b - 1) & 0xFF
    return x


def global_checksum(rom):
    return (sum(rom) - rom[0x14E] - rom[0x14F]) & 0xFFFF


def build(roms, art):
    for g, r in zip(GAMES, roms):
        assert len(r) == g['size'] and r[0x147] == 0x01, f"{g['key']}: expected plain MBC1"
    dt = roms[0]
    if dt[0x100:0x104] != DT_ENTRY:
        sys.exit('DuckTales entry point is not the expected nop / jp $0150')
    if any(dt[HOOK:HOOK_END]):
        sys.exit('DuckTales $0061-$00FF is not free padding')

    boot, menu, labels = build_code()
    out = bytearray([0xFF] * ROM_SIZE)
    for q, r in enumerate(roms):
        out[q * QUARTER:q * QUARTER + len(r)] = r
    out[HOOK:HOOK + len(boot)] = boot
    for at, data in title_patches(roms, labels, len(boot)):
        out[at:at + len(data)] = data
    out[0x102:0x104] = HOOK.to_bytes(2, 'little')       # entry: nop / jp HOOK
    out[MENU_BANK * BANK:MENU_BANK * BANK + len(menu)] = menu
    for i, img in enumerate(screens(roms, art)):
        blob = screen_bank(img)
        b = SPLASH_BANK + i
        out[b * BANK:b * BANK + len(blob)] = blob

    # Header: our title, 2 MiB MBC1 with 8 KiB of RAM and no battery (the menu
    # keeps the boot state there), and Capcom's licensee as in every original,
    # so a CGB picks the same DMG palette it gives them.
    out[0x134:0x144] = b'DISNEYAFTERNOON\x00'
    out[0x147] = 0x02
    out[0x148] = 0x06
    out[0x149] = 0x02
    out[0x14D] = header_checksum(out)
    out[0x14E:0x150] = global_checksum(out).to_bytes(2, 'big')

    # No Nintendo logo may sit at $40104: emulators take one there to mean an
    # MBC1M multicart, which banks differently.
    assert bytes(out[0x40104:0x40134]) != bytes(dt[0x104:0x134])
    return bytes(out)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    for g in GAMES:
        ap.add_argument(g['key'], help=f"{g['label']} (USA) ROM")
    ap.add_argument('bundle', help='bundleMain.mbundle from the PC Disney Afternoon Collection')
    ap.add_argument('-o', '--out', required=True)
    ap.add_argument('--screens', help='also write the five screens as PNGs into this folder')
    a = ap.parse_args()
    roms = [load_checked(getattr(a, g['key']), g['md5'], g['label'] + ' (USA)') for g in GAMES]
    load_checked(a.bundle, BUNDLE_MD5, 'bundleMain.mbundle')
    art = mbundle.read(a.bundle)
    rom = build(roms, art)
    open(a.out, 'wb').write(rom)
    if a.screens:
        os.makedirs(a.screens, exist_ok=True)
        for i, img in enumerate(screens(roms, art)):
            img.save(os.path.join(a.screens, f'screen{i}.png'))
    print(f'wrote {a.out} ({len(rom) // 1024} KiB), md5 {md5(rom)}')


if __name__ == '__main__':
    main()
