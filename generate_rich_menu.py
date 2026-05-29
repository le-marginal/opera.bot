"""
Rich Menu — Opéra Taipei
Thème : Opéra Nocturne
"""
from PIL import Image, ImageDraw, ImageFont
import math

# ── Dimensions LINE standard ──────────────────────────────────────────────────
W, H = 2500, 1686
CELL_W = W // 3
CELL_H = H // 2

# ── Palette ───────────────────────────────────────────────────────────────────
NAVY       = "#0B1729"
GOLD       = "#E0C39E"
GOLD_DIM   = "#A8895E"
BURGUNDY   = "#6F213E"
TEAL       = "#0F5A52"
WHITE      = "#F5F0E8"

def hex2rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i+2], 16) for i in (0, 2, 4))

# ── Polices ───────────────────────────────────────────────────────────────────
FONTS = "/home/gaston/fonts/"
F_TITLE  = FONTS + "playfair/playfair-display-v40-latin-700.ttf"
F_SUB    = FONTS + "noto-serif-tc/noto-serif-tc-v36-chinese-traditional_latin-500.ttf"
F_SYMBOL = FONTS + "playfair/playfair-display-v40-latin-regular.ttf"

# ── Contenu des cellules ──────────────────────────────────────────────────────
CELLS = [
    {"symbol": "✦",  "en": "Reservations",   "zh": "訂位",     "accent": BURGUNDY},
    {"symbol": "◈",  "en": "Drinks Menu",    "zh": "飲品菜單",  "accent": TEAL},
    {"symbol": "✦",  "en": "Food Menu",      "zh": "餐點菜單",  "accent": BURGUNDY},
    {"symbol": "◈",  "en": "Instagram",      "zh": "官方 IG",   "accent": TEAL},
    {"symbol": "✦",  "en": "Contact Us",     "zh": "聯絡我們",  "accent": BURGUNDY},
    {"symbol": "◈",  "en": "Info & Hours",   "zh": "營業資訊",  "accent": TEAL},
]

# ── Canvas ────────────────────────────────────────────────────────────────────
img  = Image.new("RGB", (W, H), hex2rgb(NAVY))
draw = ImageDraw.Draw(img, "RGBA")

# ── Fond : vignette radiale (assombrir les coins) ─────────────────────────────
vignette = Image.new("RGBA", (W, H), (0, 0, 0, 0))
vd = ImageDraw.Draw(vignette)
cx, cy = W // 2, H // 2
max_r = math.hypot(cx, cy)
steps = 80
for s in range(steps, 0, -1):
    r = int(max_r * s / steps)
    alpha = int(120 * (1 - s / steps) ** 1.4)
    vd.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(0, 0, 0, alpha))
img = Image.alpha_composite(img.convert("RGBA"), vignette).convert("RGB")
draw = ImageDraw.Draw(img, "RGBA")

# ── Cellules : overlay accent très subtil ─────────────────────────────────────
for i, cell in enumerate(CELLS):
    col = i % 3
    row = i // 3
    x0, y0 = col * CELL_W, row * CELL_H
    x1, y1 = x0 + CELL_W, y0 + CELL_H
    r, g, b = hex2rgb(cell["accent"])
    draw.rectangle([x0, y0, x1, y1], fill=(r, g, b, 18))

# ── Grille principale (gold champagne) ────────────────────────────────────────
GRID_W = 3
gold_rgb = hex2rgb(GOLD)
draw.line([(CELL_W,   0), (CELL_W,   H)], fill=gold_rgb, width=GRID_W)
draw.line([(2*CELL_W, 0), (2*CELL_W, H)], fill=gold_rgb, width=GRID_W)
draw.line([(0, CELL_H),   (W, CELL_H)],   fill=gold_rgb, width=GRID_W)

# ── Ornements : losanges aux intersections ────────────────────────────────────
def diamond(draw, cx, cy, size, color):
    pts = [(cx, cy - size), (cx + size, cy), (cx, cy + size), (cx - size, cy)]
    draw.polygon(pts, fill=color)
    inner = size // 2
    pts2 = [(cx, cy - inner), (cx + inner, cy), (cx, cy + inner), (cx - inner, cy)]
    draw.polygon(pts2, fill=hex2rgb(NAVY))

for px, py in [(CELL_W, CELL_H), (2*CELL_W, CELL_H)]:
    diamond(draw, px, py, 22, gold_rgb)

# ── Ornements : petits tirets dorés aux bords de grille ──────────────────────
dash_len, gap = 18, 10
gold_dim = hex2rgb(GOLD_DIM)
for x in [CELL_W, 2*CELL_W]:
    y = 0
    while y < H:
        draw.line([(x, y), (x, min(y + dash_len, H))], fill=gold_dim, width=1)
        y += dash_len + gap

# ── Ligne de titre en haut : "OPÉRA TAIPEI" centré ───────────────────────────
try:
    f_brand = ImageFont.truetype(F_TITLE, 72)
    brand   = "OPÉRA  TAIPEI"
    bb      = draw.textbbox((0, 0), brand, font=f_brand)
    bw      = bb[2] - bb[0]
    draw.text(((W - bw) / 2, 28), brand, font=f_brand, fill=gold_rgb)
    # ligne fine sous le titre
    draw.line([(W//2 - 320, 118), (W//2 + 320, 118)], fill=gold_dim, width=1)
except Exception as e:
    print(f"[brand] {e}")

# ── Contenu des cellules ──────────────────────────────────────────────────────
try:
    f_en  = ImageFont.truetype(F_TITLE,  86)
    f_zh  = ImageFont.truetype(F_SUB,    52)
    f_sym = ImageFont.truetype(F_SYMBOL, 48)
except Exception as e:
    print(f"[font load] {e}")
    raise

for i, cell in enumerate(CELLS):
    col = i % 3
    row = i // 3
    cx  = col * CELL_W + CELL_W // 2
    cy  = row * CELL_H + CELL_H // 2 + 30   # +30 pour laisser place au titre en haut

    accent = hex2rgb(cell["accent"])

    # Symbole décoratif
    sym_bb = draw.textbbox((0, 0), cell["symbol"], font=f_sym)
    sw = sym_bb[2] - sym_bb[0]
    draw.text((cx - sw // 2, cy - 125), cell["symbol"], font=f_sym, fill=accent)

    # Texte anglais
    en_bb = draw.textbbox((0, 0), cell["en"], font=f_en)
    ew = en_bb[2] - en_bb[0]
    draw.text((cx - ew // 2, cy - 60), cell["en"], font=f_en, fill=hex2rgb(WHITE))

    # Ligne décorative sous le texte anglais
    draw.line([(cx - 80, cy + 48), (cx + 80, cy + 48)], fill=accent, width=2)

    # Texte chinois
    zh_bb = draw.textbbox((0, 0), cell["zh"], font=f_zh)
    zw = zh_bb[2] - zh_bb[0]
    draw.text((cx - zw // 2, cy + 62), cell["zh"], font=f_zh, fill=hex2rgb(GOLD_DIM))

# ── Bordure extérieure fine ───────────────────────────────────────────────────
draw.rectangle([0, 0, W - 1, H - 1], outline=gold_rgb, width=2)

# ── Sauvegarde ────────────────────────────────────────────────────────────────
out = "/home/gaston/htdocs/opera.bot/assets/opera_rich_menu.png"
img.save(out, "PNG")
print(f"✓ Image générée : {out}  ({W}x{H})")
