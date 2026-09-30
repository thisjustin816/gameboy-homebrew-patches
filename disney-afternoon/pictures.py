"""The splash and menu pictures, drawn in the Game Boy's four shades.

The logos come from the PC Disney Afternoon Collection. Scaling them down by
brightness alone loses thin outlines and merges colors of the same brightness,
so each logo is sorted into color families first and each family gets a shade.
Every target pixel then takes the family that covers most of it, except that a
thin outline wins as soon as it covers OUTLINE_SHARE, so it stays continuous.

The menu's frame and arrow are DuckTales' own, from its LAND SELECT screen.
"""
import hashlib, io, os, tempfile
from collections import Counter, deque
import numpy as np
from PIL import Image, ImageDraw, ImageEnhance

# Shades 0-3, lightest first, as the menu's BGP ($E4) shows them.
SHADES = [(255, 255, 255), (170, 170, 170), (85, 85, 85), (0, 0, 0)]

OUTLINE_SHARE = 0.25

# The collection logo, built from its layers in the PC files: the triangle with the Mickey
# shape from its own layer, then the letters of the finished logo.
SPLASH_SIZE = (144, 112)
SPLASH_TOP = 4               # the logo's top row on the splash
TRIANGLE_SHADE = 2           # dark gray triangle
MICKEY_SHADE = 1             # with a light gray Mickey on it
MICKEY_DARK = 75             # the Mickey is darker than the stripes around it, once they are blurred
FILL_SHARE = 0.45            # a letter's fill covers this much of a pixel to be drawn
TEXT_SHARE = 0.4             # the same for the small words, whose strokes are thinner
TEXT_SCALE = 1.25            # THE, AFTERNOON and COLLECTION are drawn this much bigger to stay readable
BANNER_SHADE = 1             # COLLECTION's banner: light gray, with a black edge

# The game logos
LOGO_SIZE = (160, 72)
WORDMARK_PART = 1200         # the wordmark's letters are separate parts smaller than this (pixels)
WORDMARK_WIDTH = 40          # every logo's "Disney's" is this wide
WORDMARK_SOURCE = 'ducktales'
# DuckTales' fill runs red, orange, yellow. These brightnesses map to dark gray,
# light gray and white; in between, an ordered dither mixes the two neighbours.
GRADIENT = [(80, 2.0), (140, 1.0), (215, 0.0)]
BAYER = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]]) / 16 + 1 / 32

# DuckTales' LAND SELECT screen: the frame's tiles and the arrow sprite.
FRAME_TOP = [0x01, 0x14, 0x14, 0x14, 0x02, 0x03, 0x14, 0x14, 0x02, 0x03, 0x14, 0x14, 0x02, 0x03,
             0x14, 0x14, 0x14, 0x13]
FRAME_BOTTOM = [0x06, 0x14, 0x10, 0x11, 0x14, 0x14, 0x10, 0x11, 0x14, 0x14, 0x10, 0x11, 0x14, 0x14,
                0x10, 0x11, 0x14, 0x07]
FRAME_SIDES = [(0x04, 0x05), (0x12, 0x15)]    # left and right edge tiles, alternating by row
FRAME_INSIDE = 0x6E
ARROW_TILE = 0x69
LAND_SELECT_MD5 = '0c03e6fe8498bc2db1cc315590e04abd'   # of the tiles, palettes and arrow captured

PROMPT_ROW = 15              # PRESS START on the splash
MENU_TOP, MENU_BOTTOM = 10, 17
LABEL_COL, ARROW_COL = 4, 3


def snap(x):
    return x - x % 8


# ---- DuckTales' frame ---------------------------------------------------------

def land_select(dt_rom):
    """Capture the LAND SELECT screen's frame tiles and arrow from DuckTales.

    A fixed cold boot with one START press, so it is the same every run; the md5
    check makes sure of it. Returns {'bg': {tile: 16 bytes}, 'bgp', 'arrow', 'obp0'}.
    """
    from pyboy import PyBoy
    with tempfile.TemporaryDirectory() as tmp:
        path = os.path.join(tmp, 'dt.gb')
        open(path, 'wb').write(dt_rom)
        pb = PyBoy(path, window='null', sound_emulated=False)
        for f in range(480):
            if f == 240:
                pb.button('start', 4)
            pb.tick(1, False)
        m = pb.memory
        vram = bytes(m[0x8000:0x9FFF]) + bytes([m[0x9FFF]])
        bgp, obp0 = m[0xFF47], m[0xFF48]
        pb.stop(save=False)
    def bg(i):                                  # LCDC bit 4 is clear: $8800 addressing
        a = 0x1000 + (i if i < 128 else i - 256) * 16
        return vram[a:a + 16]
    wanted = sorted(set(FRAME_TOP + FRAME_BOTTOM + [t for p in FRAME_SIDES for t in p] + [FRAME_INSIDE]))
    cap = dict(bg={t: bg(t) for t in wanted}, bgp=bgp,
               arrow=vram[ARROW_TILE * 16:ARROW_TILE * 16 + 16], obp0=obp0)
    digest = hashlib.md5(b''.join(cap['bg'][t] for t in wanted)
                         + bytes([bgp, obp0]) + cap['arrow']).hexdigest()
    if digest != LAND_SELECT_MD5:
        raise SystemExit(f'LAND SELECT capture md5 {digest} does not match {LAND_SELECT_MD5}')
    return cap


def tile_image(data, pal, transparent=False):
    """8x8 image of a 2bpp tile through a DMG palette; as a sprite, color 0 is clear."""
    im = Image.new('RGBA', (8, 8), (0, 0, 0, 0))
    for y in range(8):
        lo, hi = data[2 * y], data[2 * y + 1]
        for x in range(8):
            c = ((lo >> (7 - x)) & 1) | (((hi >> (7 - x)) & 1) << 1)
            if c or not transparent:
                im.putpixel((x, y), SHADES[(pal >> (2 * c)) & 3] + (255,))
    return im


def draw_frame(img, cap, top, bottom):
    def put(t, col, row):
        img.paste(tile_image(cap['bg'][t], cap['bgp']).convert('RGB'), (col * 8, row * 8))
    for c, t in enumerate(FRAME_TOP):
        put(t, 1 + c, top)
    for c, t in enumerate(FRAME_BOTTOM):
        put(t, 1 + c, bottom)
    for r in range(top + 1, bottom):
        left, right = FRAME_SIDES[(r - top) % 2]
        put(left, 1, r)
        put(right, 18, r)
        for c in range(2, 18):
            put(FRAME_INSIDE, c, r)


def draw_text(img, glyphs, col, row, text, invert=False):
    for j, ch in enumerate(text):
        g = glyphs[ch]
        for y in range(8):
            lo, hi = g[2 * y], g[2 * y + 1]
            for x in range(8):
                c = ((lo >> (7 - x)) & 1) | (((hi >> (7 - x)) & 1) << 1)
                img.putpixel(((col + j) * 8 + x, row * 8 + y), SHADES[3 - c if invert else c])


# ---- helpers ------------------------------------------------------------------

def despeckle(img):
    """Replace every pixel that matches none of its 8 neighbours with the most common neighbour."""
    out = img.copy()
    w, h = img.size
    px, po = img.load(), out.load()
    for y in range(h):
        for x in range(w):
            nb = [px[x + dx, y + dy] for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                  if (dx or dy) and 0 <= x + dx < w and 0 <= y + dy < h]
            if px[x, y] not in nb:
                po[x, y] = Counter(nb).most_common(1)[0][0]
    return out


def on_white(png):
    """A PNG cropped to its content, on white, as an int RGB array."""
    im = Image.open(io.BytesIO(png)).convert('RGBA')
    im = im.crop(im.getbbox())
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    return np.asarray(bg.convert('RGB')).astype(int)


def blocks(shape, size):
    """Scale factor and target size to fit shape (h, w) into size, and each target
    pixel's source block as (y0, y1, x0, x1)."""
    h0, w0 = shape
    scale = min(size[0] / w0, size[1] / h0)
    w, h = int(w0 * scale), int(h0 * scale)
    def span(t):
        return int(t / scale), max(int((t + 1) / scale), int(t / scale) + 1)
    return scale, w, h, [[span(ty) + span(tx) for tx in range(w)] for ty in range(h)]


def shrink(codes, size, decide):
    """Reduce a per-pixel code map to fit size; decide(counts) picks each pixel's shade."""
    _, w, h, blk = blocks(codes.shape, size)
    n = codes.max() + 1
    out = Image.new('RGB', (w, h))
    for ty in range(h):
        for tx in range(w):
            y0, y1, x0, x1 = blk[ty][tx]
            out.putpixel((tx, ty), SHADES[decide(np.bincount(codes[y0:y1, x0:x1].ravel(), minlength=n))])
    return despeckle(out)


def to_shades(png, size, contrast):
    """Scale an image into size and map it to four shades by brightness; transparency is white."""
    im = Image.open(io.BytesIO(png)).convert('RGBA')
    im = im.crop(im.getbbox())
    im.thumbnail(size, Image.LANCZOS)
    bg = Image.new('RGBA', im.size, (255, 255, 255, 255))
    bg.alpha_composite(im)
    grey = ImageEnhance.Contrast(bg.convert('L')).enhance(contrast)
    pal = Image.new('P', (1, 1))
    pal.putpalette(sum([list(s) for s in SHADES[::-1]], []) + [0] * 756)
    return grey.convert('RGB').quantize(palette=pal, dither=Image.Dither.NONE).convert('RGB')


def png_bytes(img):
    b = io.BytesIO()
    img.save(b, 'PNG')
    return b.getvalue()


# ---- the collection logo --------------------------------------------------------

def splash_layers(A):
    """Per source pixel: the triangle mask, its lime edge, and the letters' code.
    Codes: 0 white fill, 1 yellow text, 2 purple shadow, 3 banner, 4 pink outline, -1 not letters."""
    r, g, b, a = A[..., 0], A[..., 1], A[..., 2], A[..., 3]
    lime = (abs(r - 154) < 40) & (abs(g - 233) < 30) & (b < 110)
    # everything clearly greener than red is the triangle: cyan and teal stripes, the Mickey
    # shape, the lime edge and its dark green shade; the banner's blue border is much bluer
    triangle = (g > r + 30) & ~(b > g + 80) & (a > 40)
    code = np.full(r.shape, -1)
    solid = (a > 200) & ~triangle
    white = solid & (r > 225) & (g > 225) & (b > 225)
    yellow = solid & (r > 200) & (g > 200) & (b < 120)
    pink = solid & (r > 200) & (g < 130) & (b < 170) & (b > 90)
    banner = solid & (r > 180) & (g < 110) & (b >= 170)
    shadow = solid & ~white & ~yellow & ~pink & ~banner
    for c, m in ((0, white), (1, yellow), (2, shadow), (3, banner), (4, pink)):
        code[m] = c
    # the magenta banner and its blue border; the letters' shadows hold specks of the same
    # magenta, so keep only the biggest part
    lab, ps = parts(banner | (solid & (r < 100) & (b > 180)))
    banner_quad = lab == max(ps, key=lambda p: p[2])[0]
    return triangle, lime, code, banner_quad


def corners(mask):
    """The extreme points of a mask: top left, top right, bottom right, bottom left."""
    ys, xs = np.nonzero(mask)
    return [(xs[i], ys[i]) for i in (np.argmin(xs + ys), np.argmax(xs - ys),
                                     np.argmax(xs + ys), np.argmin(xs - ys))]


def triangle_corners(lime):
    """The triangle's top left, top right and bottom corners, from its lime edge."""
    ys, xs = np.nonzero(lime)
    return [(xs[i], ys[i]) for i in (np.argmin(xs + ys), np.argmax(xs - ys), np.argmax(ys))]


def erode(mask):
    """Shrink a mask by one pixel in all eight directions."""
    m = np.pad(mask, 1)
    out = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out &= m[1 + dy:1 + dy + mask.shape[0], 1 + dx:1 + dx + mask.shape[1]]
    return out


def dilate(mask):
    """Grow a mask by one pixel in all eight directions."""
    m = np.pad(mask, 1)
    out = mask.copy()
    for dy in (-1, 0, 1):
        for dx in (-1, 0, 1):
            out |= m[1 + dy:1 + dy + mask.shape[0], 1 + dx:1 + dx + mask.shape[1]]
    return out


def shift(mask, dx, dy):
    """A mask moved right by dx and down by dy."""
    out = np.zeros_like(mask)
    h, w = mask.shape
    out[dy:, dx:] = mask[:h - dy, :w - dx]
    return out


def box_blur(x, r):
    k = 2 * r + 1
    c = np.pad(np.pad(x, r, mode='edge').cumsum(0).cumsum(1), ((1, 0), (1, 0)))
    return (c[k:, k:] - c[:-k, k:] - c[k:, :-k] + c[:-k, :-k]) / (k * k)


def cover(mask, scale, w, h):
    """How much of each target pixel a full-size mask covers, 0 to 1."""
    im = Image.fromarray((np.clip(mask.astype(float), 0, 1) * 255).astype('uint8'))
    a = np.asarray(im.resize((round(mask.shape[1] * scale), round(mask.shape[0] * scale)), Image.BOX)) / 255
    out = np.zeros((h, w))
    out[:min(h, a.shape[0]), :min(w, a.shape[1])] = a[:h, :w]
    return out


def scale_about(mask, k, c):
    """A full-size mask scaled by k about the point c, as coverage 0 to 1."""
    coeffs = (1 / k, 0, c[0] - c[0] / k, 0, 1 / k, c[1] - c[1] / k)
    im = Image.fromarray(mask.astype('uint8') * 255)
    return np.asarray(im.transform(im.size, Image.AFFINE, coeffs, Image.BILINEAR)) / 255


def mickey_mask(bg_png, shape, triangle):
    """The Mickey shape from the triangle layer, moved onto the finished logo, whose triangle
    corners are triangle. The layer draws it as darker stripes: blurred, it stands out."""
    B = np.asarray(Image.open(io.BytesIO(bg_png)).convert('RGBA')).astype(float)
    lum = 0.299 * B[..., 0] + 0.587 * B[..., 1] + 0.114 * B[..., 2]
    alpha = B[..., 3] / 255
    blurred = box_blur(lum * alpha, 8) / np.maximum(box_blur(alpha, 8), 1e-3)
    r, g, b = B[..., 0], B[..., 1], B[..., 2]
    lime = (abs(r - 154) < 40) & (abs(g - 233) < 30) & (b < 110)
    inside = (alpha > 0.9) & ~lime & (box_blur(lime.astype(float), 12) == 0)
    lab, ps = parts((blurred < MICKEY_DARK) & inside)
    mask = lab == max(ps, key=lambda p: p[2])[0]
    # the layer is placed differently from the finished logo: map one triangle onto the other
    src = np.array(triangle_corners(lime), float)
    M = np.linalg.solve(np.c_[np.array(triangle, float), np.ones(3)], src)
    im = Image.fromarray(mask.astype('uint8') * 255).transform(
        (shape[1], shape[0]), Image.AFFINE, (M[0, 0], M[1, 0], M[2, 0], M[0, 1], M[1, 1], M[2, 1]), Image.BILINEAR)
    return np.asarray(im) / 255


def split_letters(mask):
    """A word's letters, one mask each. Letters that touch in the art (a serif, two O's) are
    cut apart at their thinnest column."""
    lab, ps = parts(mask)
    ps = [(n, b) for n, b, s in ps if s > 150]
    typical = sorted(b[2] - b[0] for n, b in ps)[len(ps) // 2]
    out = []
    def cut(m, b):
        if b[2] - b[0] <= 1.6 * typical:
            out.append(m)
            return
        cols = m[:, b[0]:b[2] + 1].sum(0)
        lo, hi = int(len(cols) * 0.3), int(len(cols) * 0.7)
        x = b[0] + lo + int(np.argmin(cols[lo:hi]))
        for part in (m & (np.arange(m.shape[1]) < x), m & (np.arange(m.shape[1]) >= x)):
            ys, xs = np.nonzero(part)
            cut(part, (xs.min(), ys.min(), xs.max(), ys.max()))
    for n, b in ps:
        cut(lab == n, b)
    return sorted(out, key=lambda m: np.nonzero(m)[1].min())


def separated(covers, share):
    """The letters' fills together, with at least a pixel between neighbours for the outline."""
    total = np.zeros(covers[0].shape, bool)
    for c in covers:
        total |= (c >= share) & ~dilate(total)
    return total


def splash_logo(png, bg_png):
    """The collection logo: the triangle with its edge and the Mickey shape, then each word as
    white fills from the art with a black outline and drop shadow drawn at the target size."""
    A = np.asarray(Image.open(io.BytesIO(png)).convert('RGBA')).astype(int)
    ys, xs = np.nonzero(A[..., 3] > 40)
    A = A[ys.min():ys.max() + 1, xs.min():xs.max() + 1]
    h0, w0 = A.shape[:2]
    scale = min(SPLASH_SIZE[0] / w0, SPLASH_SIZE[1] / h0)
    w, h = int(w0 * scale), int(h0 * scale)
    _, lime, code, banner = splash_layers(A)
    triangle = triangle_corners(lime)
    base = Image.new('L', (w, h), 0)
    ImageDraw.Draw(base).polygon([(x * scale, y * scale) for x, y in triangle], fill=1)
    tri = np.asarray(base) == 1
    mickey = cover(mickey_mask(bg_png, A.shape, triangle), scale, w, h) >= 0.5
    shade = np.where(tri, np.where(mickey, MICKEY_SHADE, TRIANGLE_SHADE), 0)
    # the lime edge, as a black line with a white band inside it
    inner = erode(tri)
    band = erode(erode(inner))
    shade[tri & ~inner] = 3
    shade[inner & ~band] = 0

    def lettering(fill):
        edge = dilate(fill)
        shade[edge | shift(edge, 1, 1)] = 3
        shade[fill] = 0

    q = Image.new('L', (w0, h0), 0)
    ImageDraw.Draw(q).polygon([(int(x), int(y)) for x, y in corners(banner)], fill=1)
    in_banner = np.asarray(q) == 1
    lettering(cover((code == 0) & ~in_banner, scale, w, h) >= FILL_SHARE)
    lab, ps = parts(code == 1)
    for top in (True, False):                    # THE, then AFTERNOON
        word = np.isin(lab, [n for n, b, s in ps if s > 150 and (b[3] < h0 / 3) == top])
        ys, xs = np.nonzero(word)
        c = ((xs.min() + xs.max()) / 2, (ys.min() + ys.max()) / 2)
        lettering(separated([cover(scale_about(l, TEXT_SCALE, c), scale, w, h)
                             for l in split_letters(word)], TEXT_SHARE))
    # the banner grows leftward from its right end, so it stays on the canvas
    ys, xs = np.nonzero(in_banner)
    c = (xs.max(), (ys.min() + ys.max()) / 2)
    ban = cover(scale_about(in_banner, TEXT_SCALE, c), scale, w, h) >= 0.5
    shade[dilate(ban)] = 3
    shade[ban] = BANNER_SHADE
    lettering(separated([cover(scale_about(l, TEXT_SCALE, c), scale, w, h)
                         for l in split_letters((code == 0) & in_banner)], TEXT_SHARE))
    out = Image.new('RGB', (w, h))
    out.putdata([SHADES[v] for v in shade.ravel()])
    return out


# ---- the game logos ---------------------------------------------------------------

def dithered_logo(png, size):
    """DuckTales' logos: the red-to-yellow fill as an ordered dither across three shades."""
    rgb = on_white(png)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    # codes: 0 white, 1 fill, 2 red rim, 3 dark, 4 dark outline (kept continuous)
    codes = np.where(lum > 170, 0, np.where(lum > 85, 2, 3))
    codes = np.where((r > 150) & (b < 120), 1, codes)
    codes = np.where(lum < 70, 4, codes)
    codes = np.where(lum > 235, 0, codes)
    _, w, h, blk = blocks(codes.shape, size)
    FILL = (1, 2, 3)                           # a marker color for fill pixels, dithered below
    img = Image.new('RGB', (w, h))
    fill_lum = np.zeros((h, w))
    for ty in range(h):
        for tx in range(w):
            y0, y1, x0, x1 = blk[ty][tx]
            part = codes[y0:y1, x0:x1]
            c = np.bincount(part.ravel(), minlength=5)
            if c[4] >= OUTLINE_SHARE * c.sum():
                img.putpixel((tx, ty), SHADES[3])
                continue
            k = int(c[:4].argmax())
            img.putpixel((tx, ty), [SHADES[0], FILL, SHADES[2], SHADES[3]][k])
            if k == 1:
                fill_lum[ty, tx] = lum[y0:y1, x0:x1][part == 1].mean()
    # clean speckles on the shapes first, so the dither pattern survives
    img = despeckle(img)
    out = img.copy()
    for y in range(h):
        for x in range(w):
            if img.getpixel((x, y)) == FILL:
                v = np.interp(fill_lum[y, x], [p for p, _ in GRADIENT], [s for _, s in GRADIENT])
                lo = int(np.floor(v))
                out.putpixel((x, y), SHADES[min(lo + (v - lo > BAYER[y % 4, x % 4]), 3)])
    return out


def family_logo(png, size):
    """TaleSpin's logo, by color family: warm fill in two steps, red rim, dark outline."""
    rgb = on_white(png)
    r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
    lum = 0.299 * r + 0.587 * g + 0.114 * b
    warm = (r > 150) & (g >= 60) & (b < 120)
    codes = np.where(lum > 170, 1, np.where(lum > 85, 2, 3))
    codes = np.where(warm, np.where(lum > 185, 0, 1), codes)
    codes = np.where((r > 150) & (g < 60) & (b < 120), 2, codes)
    codes = np.where(lum < 70, 4, codes)
    codes = np.where(lum > 235, 5, codes)
    def decide(c):
        if c[4] >= OUTLINE_SHARE * c.sum():
            return 3
        c = c.copy()
        c[0] += c[5]
        return int(c[:4].argmax())
    return shrink(codes, size, decide)


def title_logo(key, png, size):
    if key in ('ducktales', 'ducktales2'):
        return dithered_logo(png, size)
    if key == 'darkwing':                      # its colors are dark on light: brightness works
        return despeckle(to_shades(png, size, 1.3))
    return family_logo(png, size)


def parts(mask):
    """The 4-connected parts of a mask: (labels, [(label, bbox, size)])."""
    h, w = mask.shape
    lab = np.zeros((h, w), np.int32)
    out, n = [], 0
    for y in range(h):
        for x in range(w):
            if mask[y, x] and not lab[y, x]:
                n += 1
                lab[y, x] = n
                q = deque([(y, x)])
                x0 = x1 = x
                y0 = y1 = y
                size = 0
                while q:
                    cy, cx = q.popleft()
                    size += 1
                    x0, x1, y0, y1 = min(x0, cx), max(x1, cx), min(y0, cy), max(y1, cy)
                    for ny, nx in ((cy + 1, cx), (cy - 1, cx), (cy, cx + 1), (cy, cx - 1)):
                        if 0 <= ny < h and 0 <= nx < w and mask[ny, nx] and not lab[ny, nx]:
                            lab[ny, nx] = n
                            q.append((ny, nx))
                out.append((n, (x0, y0, x1, y1), size))
    return lab, out


def split_wordmark(png):
    """Return (title RGBA without "Disney's", the wordmark RGBA, its bbox), in the logo's crop."""
    im = Image.open(io.BytesIO(png)).convert('RGBA')
    im = im.crop(im.getbbox())
    a = np.asarray(im)
    lab, ps = parts(a[..., 3] > 40)
    big = [n for n, b, s in ps if s >= WORDMARK_PART]
    title_top = min(b[1] for n, b, s in ps if s >= WORDMARK_PART)
    small = [(n, b) for n, b, s in ps if s < WORDMARK_PART]
    word = [n for n, b in small if b[3] < title_top + a.shape[0] // 4]
    # a long y tail reaches further down: take any small part that starts within the
    # wordmark's rows and sits within its width
    wx0 = min(b[0] for n, b in small if n in word)
    wx1 = max(b[2] for n, b in small if n in word)
    wy1 = max(b[3] for n, b in small if n in word)
    word += [n for n, b in small if n not in word and b[1] <= wy1 and wx0 <= b[0] and b[2] <= wx1]
    # keep the soft edge around the letters with them: grow the mask by 2 pixels
    grown = np.isin(lab, word)
    for _ in range(2):
        g = grown.copy()
        g[1:] |= grown[:-1]
        g[:-1] |= grown[1:]
        g[:, 1:] |= grown[:, :-1]
        g[:, :-1] |= grown[:, 1:]
        grown = g & (a[..., 3] > 0) & ~np.isin(lab, big)
    title = a.copy()
    title[grown, 3] = 0
    wm = np.zeros_like(a)
    wm[grown] = a[grown]
    ys, xs = np.nonzero(grown)
    return Image.fromarray(title), Image.fromarray(wm), (xs.min(), ys.min(), xs.max() + 1, ys.max() + 1)


def master_wordmark(art, games):
    """One black "Disney's", WORDMARK_WIDTH wide, used on every logo so they all match."""
    g = next(g for g in games if g['key'] == WORDMARK_SOURCE)
    _, wm, box = split_wordmark(art[g['art']])
    wm = wm.crop(box)
    w, h = WORDMARK_WIDTH, max(1, round(wm.height * WORDMARK_WIDTH / wm.width))
    cover = np.asarray(wm.resize((w, h), Image.BOX))[..., 3] / 255
    out = Image.new('RGBA', (w, h), (0, 0, 0, 0))
    for y in range(h):
        for x in range(w):
            if cover[y, x] >= 0.4:
                out.putpixel((x, y), SHADES[3] + (255,))
    return out


def game_logo(art, games, g):
    """A game's logo: its title converted at the whole logo's scale, and the shared wordmark
    where its own "Disney's" was."""
    full = Image.open(io.BytesIO(art[g['art']])).convert('RGBA')
    full = full.crop(full.getbbox())
    title, _, box = split_wordmark(art[g['art']])
    scale = min(LOGO_SIZE[0] / full.width, LOGO_SIZE[1] / full.height)
    dims = (round(full.width * scale), round(full.height * scale))
    canvas = Image.new('RGB', dims, SHADES[0])
    # the title alone is smaller than the whole logo when the wordmark stuck out; keep it
    # at the whole logo's scale and place
    tb = title.getbbox()
    size = (round((tb[2] - tb[0]) * scale), round((tb[3] - tb[1]) * scale))
    canvas.paste(title_logo(g['key'], png_bytes(title), size), (round(tb[0] * scale), round(tb[1] * scale)))
    wm = master_wordmark(art, games)
    cx, cy = (box[0] + box[2]) / 2 * scale, (box[1] + box[3]) / 2 * scale
    x = min(max(0, round(cx - wm.width / 2)), canvas.width - wm.width)
    y = max(0, round(cy - wm.height / 2))
    canvas.paste(wm, (x, y), wm)
    return canvas


# ---- screens ------------------------------------------------------------------------

def splash_screen(png, bg_png, glyphs):
    img = Image.new('RGB', (160, 144), SHADES[0])
    logo = splash_logo(png, bg_png)
    img.paste(logo, (snap((160 - logo.width) // 2), SPLASH_TOP))
    draw_text(img, glyphs, 4, PROMPT_ROW, 'PRESS START')
    return img


def menu_screen(logo, glyphs, cap, games, sel):
    img = Image.new('RGB', (160, 144), SHADES[0])
    img.paste(logo, (snap((160 - logo.width) // 2), 4 + (72 - logo.height) // 2))
    draw_frame(img, cap, MENU_TOP, MENU_BOTTOM)
    for i, g in enumerate(games):
        draw_text(img, glyphs, LABEL_COL, MENU_TOP + 2 + i, g['label'], invert=True)
    arrow = tile_image(cap['arrow'], cap['obp0'], transparent=True)
    img.paste(arrow, (ARROW_COL * 8, (MENU_TOP + 2 + sel) * 8), arrow)
    return img
