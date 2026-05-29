"""
Sync menu Opéra Taipei — Google Sheets → LINE Flex Message cache
Thème : Opéra Nocturne
"""
import gspread
import json
from collections import defaultdict
import traceback
import sys

# ── Config ────────────────────────────────────────────────────────────────────
CREDS_FILE  = '/home/gaston/htdocs/lucien.bot/gaston-key.json'
SHEET_ID    = '19RYYbV-1LazPjTHb1DZtygBB4bSIKsNBY_DxhLW4ISw'
CACHE_FILE  = '/home/gaston/htdocs/opera.bot/menu_cache.json'

# ── Palette Opéra Nocturne ────────────────────────────────────────────────────
NAVY     = "#0B1729"
NAVY_2   = "#111F35"
GOLD     = "#E0C39E"
GOLD_DIM = "#A8895E"
BURGUNDY = "#6F213E"
TEAL     = "#0F5A52"
WHITE    = "#F5F0E8"
GRAY     = "#8899AA"

# ── Composants Flex ──────────────────────────────────────────────────────────

def build_header(title_en, title_zh, accent=GOLD):
    return {
        "type": "box",
        "layout": "vertical",
        "backgroundColor": NAVY,
        "paddingTop": "lg",
        "paddingBottom": "sm",
        "paddingStart": "md",
        "paddingEnd": "md",
        "contents": [
            {
                "type": "text",
                "text": title_en.upper(),
                "color": accent,
                "size": "sm",
                "weight": "bold",
                "align": "center"
            },
            {
                "type": "text",
                "text": title_zh,
                "color": GRAY,
                "size": "xxs",
                "align": "center",
                "margin": "xs"
            },
            {
                "type": "separator",
                "color": GOLD_DIM,
                "margin": "sm"
            }
        ]
    }

def build_item(item):
    name_en = str(item.get('Nom', '')).strip()
    name_zh = str(item.get('Nom (Chinois)', '')).strip()
    price   = str(item.get('Prix (NT$)', '')).strip()
    desc    = str(item.get('Description / Options', '')).strip()

    name_line = name_en
    if name_zh:
        name_line = f"{name_en}  {name_zh}"

    contents = [
        {
            "type": "box",
            "layout": "horizontal",
            "contents": [
                {
                    "type": "text",
                    "text": name_line,
                    "color": WHITE,
                    "size": "xxs",
                    "flex": 5,
                    "wrap": True,
                    "weight": "bold"
                },
                {
                    "type": "text",
                    "text": f"NT${price}" if price else "",
                    "color": GOLD,
                    "size": "xxs",
                    "align": "end",
                    "flex": 2,
                    "gravity": "center"
                }
            ]
        }
    ]

    if desc:
        contents.append({
            "type": "text",
            "text": desc,
            "color": GRAY,
            "size": "xxs",
            "wrap": True,
            "margin": "xs"
        })

    return {
        "type": "box",
        "layout": "vertical",
        "spacing": "xs",
        "paddingStart": "sm",
        "paddingEnd": "sm",
        "paddingTop": "sm",
        "contents": contents
    }

def build_separator():
    return {"type": "separator", "color": BURGUNDY, "margin": "sm"}

def build_bubble(title_en, title_zh, items, accent=GOLD):
    body_contents = []
    for i, item in enumerate(items):
        body_contents.append(build_item(item))
        if i < len(items) - 1:
            body_contents.append(build_separator())

    return {
        "type": "bubble",
        "size": "kilo",
        "styles": {
            "header": {"backgroundColor": NAVY},
            "body":   {"backgroundColor": NAVY}
        },
        "header": build_header(title_en, title_zh, accent),
        "body": {
            "type": "box",
            "layout": "vertical",
            "backgroundColor": NAVY,
            "paddingAll": "sm",
            "spacing": "none",
            "contents": body_contents
        }
    }

# ── Carousels ─────────────────────────────────────────────────────────────────

DRINKS_MAP = [
    ("House Signatures",   "招牌特調",    GOLD),
    ("Classic Cocktails",  "經典雞尾酒",  GOLD),
    ("Wine Cocktails",     "葡萄酒特調",  TEAL),
    ("Wine By The Glass",  "單杯葡萄酒",  TEAL),
    ("Beers",              "啤酒",       GRAY),
    ("Homemade Sodas",     "自製氣泡飲",  TEAL),
]

FOOD_MAP = [
    ("Appetizers & Tasty Bites", "餐點", GOLD),
]

def create_drinks_carousel(by_cat):
    bubbles = []
    for cat_en, cat_zh, accent in DRINKS_MAP:
        items = by_cat.get(cat_en, [])
        if not items:
            continue
        # Couper en deux si > 10 items
        if len(items) > 10:
            bubbles.append(build_bubble(cat_en, cat_zh, items[:10], accent))
            bubbles.append(build_bubble(cat_en + " (suite)", cat_zh, items[10:], accent))
        else:
            bubbles.append(build_bubble(cat_en, cat_zh, items, accent))

    carousel = {
        "altText": "Drinks Menu 🎭",
        "contents": {"type": "carousel", "contents": bubbles}
    }
    kb = len(json.dumps(carousel, ensure_ascii=False).encode()) / 1024
    print(f"  drinks_menu_1: {kb:.1f} KB ({len(bubbles)} bulles)")
    return carousel

def create_food_carousel(by_cat):
    bubbles = []
    for cat_en, cat_zh, accent in FOOD_MAP:
        items = by_cat.get(cat_en, [])
        if items:
            bubbles.append(build_bubble(cat_en, cat_zh, items, accent))

    carousel = {
        "altText": "Food Menu 🍽️",
        "contents": {"type": "carousel", "contents": bubbles}
    }
    kb = len(json.dumps(carousel, ensure_ascii=False).encode()) / 1024
    print(f"  food_carousel: {kb:.1f} KB ({len(bubbles)} bulles)")
    return carousel

# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    try:
        client = gspread.service_account(filename=CREDS_FILE)
        sh     = client.open_by_key(SHEET_ID)
        ws     = sh.get_worksheet(0)
        rows   = ws.get_all_records()

        available = [r for r in rows if str(r.get('Disponible', '')).upper() == 'TRUE']
        print(f"{len(available)} items disponibles sur {len(rows)}")

        food_cats  = {"Appetizers & Tasty Bites"}
        by_cat     = defaultdict(list)

        for item in available:
            cat = item.get('Catégorie', '')
            by_cat[cat].append(item)

        food_by_cat  = {k: v for k, v in by_cat.items() if k in food_cats}
        drinks_by_cat = {k: v for k, v in by_cat.items() if k not in food_cats}

        cache = {
            "drinks_menu_1": create_drinks_carousel(drinks_by_cat),
            "food_carousel":  create_food_carousel(food_by_cat),
        }

        with open(CACHE_FILE, 'w', encoding='utf-8') as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)

        print("✅ Cache menu Opéra reconstruit.")

    except Exception:
        print("Erreur :")
        traceback.print_exc(file=sys.stdout)

if __name__ == "__main__":
    main()
