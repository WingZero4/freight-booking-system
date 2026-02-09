"""Generate 3 additional design mockup PNGs — Options C, D, E."""
from PIL import Image, ImageDraw, ImageFont
import os

W = 1200

def get_font(size, bold=False):
    if bold:
        for f in ["C:/Windows/Fonts/segoeuib.ttf", "C:/Windows/Fonts/arialbd.ttf"]:
            if os.path.exists(f):
                return ImageFont.truetype(f, size)
    for f in ["C:/Windows/Fonts/segoeui.ttf", "C:/Windows/Fonts/arial.ttf"]:
        if os.path.exists(f):
            return ImageFont.truetype(f, size)
    return ImageFont.load_default()

font_sm = get_font(13)
font_md = get_font(15)
font_md_b = get_font(15, bold=True)
font_lg = get_font(18, bold=True)
font_xl = get_font(22, bold=True)
font_xxl = get_font(28, bold=True)
font_stat = get_font(36, bold=True)
font_title = get_font(16, bold=True)
WHITE = (255, 255, 255)


def generate_mockup(colors, output_name):
    """Generate a full mockup PNG with the given color scheme."""
    H = 2400
    img = Image.new('RGB', (W, H), colors['body_bg'])
    draw = ImageDraw.Draw(img)

    PRIMARY = colors['primary']
    PRIMARY_MID = colors['primary_mid']
    PRIMARY_LIGHT = colors['primary_light']
    ACCENT = colors['accent']
    ACCENT_HOVER = colors.get('accent_hover', ACCENT)
    BODY_BG = colors['body_bg']
    CARD_BG = colors['card_bg']
    TEXT_DARK = colors['text_dark']
    TEXT_MUTED = colors['text_muted']
    BORDER = colors['border']
    GREEN = colors['green']
    ORANGE_C = colors['orange']
    BLUE_C = colors['blue']
    GRAY_C = colors['gray']
    RED_C = colors['red']
    TABLE_STRIPE = colors['table_stripe']
    TITLE = colors['title']
    SUBTITLE = colors['subtitle']
    PALETTE = colors['palette']
    ACCENT_LINE = colors.get('accent_line', None)
    DESCRIPTION = colors['description']

    y = 0

    def rounded_rect(x1, y1, x2, y2, fill, radius=8):
        draw.rounded_rectangle([x1, y1, x2, y2], radius=radius, fill=fill)

    def badge(x, y, text, bg, fg=WHITE):
        tw = draw.textlength(text, font=font_sm)
        rounded_rect(x, y, x + tw + 16, y + 22, bg, radius=4)
        draw.text((x + 8, y + 4), text, fill=fg, font=font_sm)
        return tw + 20

    def draw_table_row(x, y, cols, widths, font_r=font_sm, bg=None, fg=TEXT_DARK, row_h=32):
        if bg:
            draw.rectangle([x, y, x + sum(widths), y + row_h], fill=bg)
        cx = x
        for col, w in zip(cols, widths):
            draw.text((cx + 8, y + 8), str(col), fill=fg, font=font_r)
            draw.line([(cx, y), (cx, y + row_h)], fill=BORDER, width=1)
            cx += w
        draw.line([(cx, y), (cx, y + row_h)], fill=BORDER, width=1)
        draw.line([(x, y + row_h), (x + sum(widths), y + row_h)], fill=BORDER, width=1)
        return y + row_h

    def section_label(y, text):
        draw.text((30, y), text, fill=ACCENT, font=font_title)
        draw.line([(30, y + 22), (W - 30, y + 22)], fill=ACCENT, width=2)
        return y + 35

    # ─── NAVBAR ───────────────────────────────────────────────
    draw.rectangle([0, y, W, y + 56], fill=PRIMARY)
    if ACCENT_LINE:
        draw.rectangle([0, y + 56, W, y + 59], fill=ACCENT_LINE)
    draw.text((30, y + 16), "\u2693  Freight Booking", fill=WHITE, font=font_xl)
    nav_items = ["Dashboard", "Bookings", "New Booking", "Address Book"]
    nx = 350
    for item in nav_items:
        tw = draw.textlength(item, font=font_md)
        if item == "Bookings":
            rounded_rect(nx - 6, y + 12, nx + tw + 6, y + 44, fill=PRIMARY_MID, radius=4)
            draw.text((nx, y + 18), item, fill=WHITE, font=font_md_b)
        else:
            draw.text((nx, y + 18), item, fill=(195, 200, 215), font=font_md)
        nx += tw + 30
    draw.text((W - 280, y + 18), "acme_user (ACME)", fill=(175, 185, 200), font=font_sm)
    rounded_rect(W - 120, y + 14, W - 30, y + 40, fill=PRIMARY_LIGHT, radius=4)
    draw.text((W - 110, y + 18), "Logout", fill=(210, 215, 225), font=font_sm)
    y += 59 if ACCENT_LINE else 56

    # ─── TITLE ────────────────────────────────────────────────
    y += 20
    draw.text((30, y), TITLE, fill=PRIMARY, font=font_xxl)
    draw.text((30, y + 36), SUBTITLE, fill=ACCENT, font=font_lg)
    y += 70

    # ─── BOOKING DETAIL HEADER ────────────────────────────────
    y = section_label(y, "BOOKING DETAIL HEADER")
    header_h = 100
    for i in range(header_h):
        r = int(PRIMARY[0] + (PRIMARY_MID[0] - PRIMARY[0]) * i / header_h)
        g = int(PRIMARY[1] + (PRIMARY_MID[1] - PRIMARY[1]) * i / header_h)
        b = int(PRIMARY[2] + (PRIMARY_MID[2] - PRIMARY[2]) * i / header_h)
        draw.line([(30, y + i), (W - 30, y + i)], fill=(r, g, b))
    draw.text((50, y + 16), "BK-202602-0001", fill=WHITE, font=font_xxl)
    draw.text((50, y + 50), "Sea FCL  \u00b7  USNYC \u2192 CNSHA  \u00b7  1x 20GP  \u00b7  FOB", fill=(180, 190, 210), font=font_md)
    badge(W - 160, y + 22, "Confirmed", GREEN)

    btn_y = y + header_h - 2
    draw.rectangle([30, btn_y, W - 30, btn_y + 40], fill=PRIMARY_MID)
    bx = 50
    for label, bg in [("Carrier Details", ACCENT), ("In Transit", BLUE_C), ("Cancel", PRIMARY_LIGHT), ("Back to List", PRIMARY_LIGHT)]:
        tw = draw.textlength(label, font=font_sm)
        if label == "Back to List":
            bx = W - 160
        rounded_rect(bx, btn_y + 8, bx + tw + 20, btn_y + 32, bg, radius=4)
        draw.text((bx + 10, btn_y + 12), label, fill=WHITE, font=font_sm)
        bx += tw + 30
    y = btn_y + 44

    # ─── TABS ─────────────────────────────────────────────────
    tab_y = y + 5
    tabs = ["Overview", "Cargo (3)", "Parties (2)", "Documents (4)", "Activity"]
    tx = 30
    for tab in tabs:
        tw = draw.textlength(tab, font=font_md)
        if tab == "Overview":
            draw.text((tx + 10, tab_y + 8), tab, fill=ACCENT, font=font_md_b)
            draw.line([(tx + 5, tab_y + 30), (tx + tw + 15, tab_y + 30)], fill=ACCENT, width=3)
        else:
            draw.text((tx + 10, tab_y + 8), tab, fill=TEXT_MUTED, font=font_md)
        tx += tw + 35
    y = tab_y + 38

    # ─── OVERVIEW CARD ────────────────────────────────────────
    rounded_rect(30, y, W - 30, y + 420, CARD_BG, radius=8)
    y += 20

    draw.text((50, y), "Route & Mode", fill=ACCENT, font=font_lg)
    draw.line([(50, y + 24), (400, y + 24)], fill=ACCENT, width=2)
    y += 40
    draw.text((50, y), "Origin", fill=TEXT_MUTED, font=font_sm)
    draw.text((50, y + 18), "USNYC - New York", fill=PRIMARY, font=font_lg)
    draw.text((480, y + 10), "\u2192", fill=ACCENT, font=font_xxl)
    draw.text((600, y), "Destination", fill=TEXT_MUTED, font=font_sm)
    draw.text((600, y + 18), "CNSHA - Shanghai", fill=PRIMARY, font=font_lg)
    y += 55

    draw.text((50, y), "Cargo Summary", fill=ACCENT, font=font_lg)
    draw.line([(50, y + 24), (400, y + 24)], fill=ACCENT, width=2)
    y += 35

    cols_h = ["#", "Description", "Qty", "Package", "Weight", "L", "W", "H", "Vol CBM", "HS Code", "Origin", "Hazmat"]
    col_w = [35, 175, 50, 80, 75, 55, 55, 55, 75, 80, 60, 100]
    y = draw_table_row(50, y, cols_h, col_w, bg=PRIMARY, fg=WHITE, row_h=30)
    rows = [
        ["1", "LCD Monitors 27\"", "50", "Carton", "500.00", "60", "40", "35", "4.200", "852872", "CN", "-"],
        ["2", "Keyboard Assy", "200", "Carton", "300.00", "-", "-", "-", "2.800", "847330", "CN", "-"],
        ["3", "Li Battery Packs", "25", "Crate", "150.00", "45", "30", "20", "0.675", "850760", "CN", "UN3481"],
    ]
    for i, row in enumerate(rows):
        y = draw_table_row(50, y, row, col_w, bg=TABLE_STRIPE if i % 2 == 0 else CARD_BG, row_h=30)
    y = draw_table_row(50, y, ["", "", "", "Totals", "950.00", "", "", "", "7.675", "", "", ""], col_w, bg=PRIMARY, fg=WHITE, row_h=30)
    y += 40

    # ─── DASHBOARD STATS ──────────────────────────────────────
    y = section_label(y, "DASHBOARD STATS")
    stats = [("4", "Draft", GRAY_C), ("7", "Submitted", ORANGE_C), ("12", "Confirmed", GREEN), ("2", "Cancelled", RED_C)]
    sx = 30
    card_w = (W - 60 - 45) // 4
    for num, label, color in stats:
        rounded_rect(sx, y, sx + card_w, y + 90, CARD_BG, radius=8)
        draw.rectangle([sx, y + 10, sx + 4, y + 80], fill=color)
        draw.text((sx + 20, y + 15), num, fill=PRIMARY, font=font_stat)
        draw.text((sx + 20, y + 58), label, fill=TEXT_MUTED, font=font_md)
        sx += card_w + 15
    y += 110

    # ─── BUTTONS & BADGES ─────────────────────────────────────
    y = section_label(y, "BUTTONS & BADGES")
    buttons = [
        ("New Booking", ACCENT, WHITE),
        ("Confirm", GREEN, WHITE),
        ("Cancel", CARD_BG, RED_C),
        ("Edit", CARD_BG, PRIMARY),
        ("Submit", ACCENT, WHITE),
        ("Export CSV", PRIMARY, WHITE),
    ]
    bx = 30
    for label, bg, fg in buttons:
        tw = draw.textlength(label, font=font_md)
        rounded_rect(bx, y, bx + tw + 28, y + 36, bg, radius=6)
        if bg == CARD_BG:
            draw.rounded_rectangle([bx, y, bx + tw + 28, y + 36], radius=6, outline=fg, width=2)
        draw.text((bx + 14, y + 9), label, fill=fg, font=font_md)
        bx += tw + 40
    y += 50

    badges_data = [
        ("Draft", GRAY_C), ("Submitted", ORANGE_C), ("Confirmed", GREEN),
        ("In Transit", BLUE_C), ("Completed", ACCENT), ("Rejected", PRIMARY_MID), ("Cancelled", RED_C),
    ]
    bx = 30
    for label, bg in badges_data:
        fg = WHITE if bg != ORANGE_C else TEXT_DARK
        bw = badge(bx, y, label, bg, fg)
        bx += bw + 10
    y += 45

    # ─── BOOKING LIST TABLE ───────────────────────────────────
    y = section_label(y, "BOOKING LIST")
    rounded_rect(30, y, W - 30, y + 38, PRIMARY, radius=8)
    draw.rectangle([30, y + 20, W - 30, y + 38], fill=PRIMARY)
    draw.text((50, y + 10), "Recent Bookings", fill=WHITE, font=font_md_b)
    y += 38
    list_cols = ["Booking #", "Customer", "Route", "Mode", "Ready Date", "Status", "Action"]
    list_w = [150, 185, 165, 100, 130, 130, 90]
    y = draw_table_row(30, y, list_cols, list_w, bg=PRIMARY, fg=WHITE, row_h=32)
    list_rows = [
        ["BK-202602-0001", "Acme Corp", "USNYC \u2192 CNSHA", "Sea FCL", "Feb 21, 2026", "Confirmed", "View"],
        ["BK-202602-0002", "Globex Inc", "CNSHA \u2192 USLAX", "Sea FCL", "Feb 28, 2026", "Submitted", "View"],
        ["BK-202602-0003", "Acme Corp", "HKHKG \u2192 USNYC", "Air", "Mar 05, 2026", "Draft", "View"],
    ]
    for i, row in enumerate(list_rows):
        y = draw_table_row(30, y, row, list_w, bg=TABLE_STRIPE if i % 2 == 0 else CARD_BG, row_h=32)
    y += 15

    # ─── LOGIN PAGE ───────────────────────────────────────────
    y = section_label(y, "LOGIN PAGE")
    lx, lw = W // 2 - 200, 400
    rounded_rect(lx, y, lx + lw, y + 340, CARD_BG, radius=12)
    for i in range(120):
        r = int(PRIMARY[0] + (PRIMARY_MID[0] - PRIMARY[0]) * i / 120)
        g = int(PRIMARY[1] + (PRIMARY_MID[1] - PRIMARY[1]) * i / 120)
        b = int(PRIMARY[2] + (PRIMARY_MID[2] - PRIMARY[2]) * i / 120)
        if i < 12:
            draw.line([(lx + 12 - i, y + i), (lx + lw - 12 + i, y + i)], fill=(r, g, b))
        else:
            draw.line([(lx, y + i), (lx + lw, y + i)], fill=(r, g, b))
    if ACCENT_LINE:
        draw.rectangle([lx, y + 117, lx + lw, y + 120], fill=ACCENT_LINE)
    draw.text((lx + 110, y + 30), "Freight Booking", fill=WHITE, font=font_xxl)
    draw.text((lx + 135, y + 68), "Customer Portal", fill=(180, 190, 215), font=font_md)
    fy = y + 135
    draw.text((lx + 30, fy), "Username", fill=TEXT_DARK, font=font_md_b)
    fy += 22
    draw.rounded_rectangle([lx + 30, fy, lx + lw - 30, fy + 36], radius=6, outline=BORDER, width=2, fill=WHITE)
    fy += 50
    draw.text((lx + 30, fy), "Password", fill=TEXT_DARK, font=font_md_b)
    fy += 22
    draw.rounded_rectangle([lx + 30, fy, lx + lw - 30, fy + 36], radius=6, outline=BORDER, width=2, fill=WHITE)
    fy += 50
    rounded_rect(lx + 30, fy, lx + lw - 30, fy + 40, ACCENT, radius=6)
    tw = draw.textlength("Login", font=font_lg)
    draw.text((lx + lw // 2 - tw // 2, fy + 10), "Login", fill=WHITE, font=font_lg)
    fy += 52
    tw2 = draw.textlength("Forgot Password?", font=font_sm)
    draw.text((lx + lw // 2 - tw2 // 2, fy), "Forgot Password?", fill=ACCENT, font=font_sm)
    y += 360

    # ─── COLOR PALETTE ────────────────────────────────────────
    y = section_label(y, "COLOR PALETTE")
    px = 30
    sw = (W - 60 - 6 * 12) // 7
    for hex_c, name, rgb in PALETTE:
        rounded_rect(px, y, px + sw, y + 55, rgb, radius=8)
        if rgb in [BODY_BG, CARD_BG]:
            draw.rounded_rectangle([px, y, px + sw, y + 55], radius=8, outline=BORDER, width=1)
        draw.text((px + 5, y + 62), name, fill=TEXT_DARK, font=font_sm)
        draw.text((px + 5, y + 78), hex_c, fill=TEXT_MUTED, font=font_sm)
        px += sw + 12
    y += 105

    draw.text((30, y), "Font: Inter (Google Fonts) \u2014 clean, modern sans-serif", fill=TEXT_DARK, font=font_md_b)
    y += 22
    draw.text((30, y), DESCRIPTION, fill=TEXT_MUTED, font=font_sm)
    y += 30

    # ─── FOOTER ───────────────────────────────────────────────
    draw.rectangle([0, y, W, y + 45], fill=PRIMARY)
    if ACCENT_LINE:
        draw.rectangle([0, y, W, y + 3], fill=ACCENT_LINE)
    tw = draw.textlength("Freight Booking Portal \u00a9 2026", font=font_sm)
    draw.text((W // 2 - tw // 2, y + 16), "Freight Booking Portal \u00a9 2026", fill=(165, 175, 190), font=font_sm)
    y += 45

    img_cropped = img.crop((0, 0, W, y + 10))
    out = os.path.join(os.path.dirname(__file__), output_name)
    img_cropped.save(out, "PNG", quality=95)
    print(f"Saved: {out} ({img_cropped.size[0]}x{img_cropped.size[1]})")


# ═══════════════════════════════════════════════════════════════════════
# OPTION C: Premium & Sophisticated
# Deep charcoal + champagne gold — "White-glove service"
# ═══════════════════════════════════════════════════════════════════════
CHARCOAL = (45, 45, 55)
CHARCOAL_MID = (58, 58, 68)
CHARCOAL_LIGHT = (78, 78, 90)
GOLD = (184, 152, 76)
GOLD_HOVER = (200, 168, 88)

generate_mockup({
    'primary': CHARCOAL,
    'primary_mid': CHARCOAL_MID,
    'primary_light': CHARCOAL_LIGHT,
    'accent': GOLD,
    'accent_hover': GOLD_HOVER,
    'body_bg': (245, 244, 242),       # warm off-white
    'card_bg': (255, 255, 255),
    'text_dark': (38, 38, 48),
    'text_muted': (120, 118, 115),
    'border': (228, 225, 220),
    'green': (46, 139, 87),            # seagreen — more refined
    'orange': (200, 155, 50),          # muted gold-orange
    'blue': (70, 130, 180),            # steelblue
    'gray': (128, 128, 128),
    'red': (178, 60, 50),              # muted red
    'table_stripe': (250, 249, 247),
    'accent_line': GOLD,
    'title': "OPTION C \u2014 Premium & Sophisticated",
    'subtitle': "FOR COMPARISON",
    'description': "Charcoal + champagne gold: exclusive, high-end feel \u2014 \"white-glove logistics service\"",
    'palette': [
        ("#2d2d37", "Charcoal", CHARCOAL),
        ("#3a3a44", "Char Mid", CHARCOAL_MID),
        ("#4e4e5a", "Char Light", CHARCOAL_LIGHT),
        ("#b8984c", "Gold", GOLD),
        ("#c8a858", "Gold Hover", GOLD_HOVER),
        ("#f5f4f2", "Body BG", (245, 244, 242)),
        ("#ffffff", "Card White", (255, 255, 255)),
    ],
}, "design-mockup-c.png")


# ═══════════════════════════════════════════════════════════════════════
# OPTION D: Clean & Efficient
# Crisp white + indigo/violet — "Modern SaaS tech feel"
# ═══════════════════════════════════════════════════════════════════════
INDIGO = (67, 56, 202)
INDIGO_MID = (79, 70, 215)
INDIGO_LIGHT = (99, 90, 225)
VIOLET_ACCENT = (124, 58, 237)

generate_mockup({
    'primary': INDIGO,
    'primary_mid': INDIGO_MID,
    'primary_light': INDIGO_LIGHT,
    'accent': VIOLET_ACCENT,
    'accent_hover': (109, 40, 217),
    'body_bg': (248, 248, 255),        # ghostwhite — very clean
    'card_bg': (255, 255, 255),
    'text_dark': (30, 30, 60),
    'text_muted': (107, 114, 128),
    'border': (229, 231, 235),
    'green': (16, 185, 129),           # emerald — modern
    'orange': (245, 158, 11),          # amber
    'blue': (59, 130, 246),            # modern blue
    'gray': (107, 114, 128),
    'red': (239, 68, 68),              # bright red
    'table_stripe': (249, 250, 251),
    'accent_line': VIOLET_ACCENT,
    'title': "OPTION D \u2014 Clean & Efficient",
    'subtitle': "FOR COMPARISON",
    'description': "Indigo + violet: modern SaaS tech feel \u2014 \"cutting-edge, fast, no-nonsense\"",
    'palette': [
        ("#4338ca", "Indigo", INDIGO),
        ("#4f46d7", "Indigo Mid", INDIGO_MID),
        ("#635ae1", "Indigo Light", INDIGO_LIGHT),
        ("#7c3aed", "Violet", VIOLET_ACCENT),
        ("#f59e0b", "Amber", (245, 158, 11)),
        ("#f8f8ff", "Body BG", (248, 248, 255)),
        ("#ffffff", "Card White", (255, 255, 255)),
    ],
}, "design-mockup-d.png")


# ═══════════════════════════════════════════════════════════════════════
# OPTION E: Calm & Reassuring
# Soft blue + sage green — "Relax, we've got this handled"
# ═══════════════════════════════════════════════════════════════════════
SLATE_BLUE = (55, 80, 108)
SLATE_BLUE_MID = (68, 95, 125)
SLATE_BLUE_LIGHT = (85, 112, 142)
SAGE = (104, 157, 113)
SAGE_HOVER = (90, 143, 99)

generate_mockup({
    'primary': SLATE_BLUE,
    'primary_mid': SLATE_BLUE_MID,
    'primary_light': SLATE_BLUE_LIGHT,
    'accent': SAGE,
    'accent_hover': SAGE_HOVER,
    'body_bg': (245, 248, 246),        # hint of green warmth
    'card_bg': (255, 255, 255),
    'text_dark': (42, 52, 62),
    'text_muted': (110, 125, 138),
    'border': (220, 228, 225),
    'green': (72, 160, 100),           # natural green
    'orange': (220, 160, 50),          # warm amber
    'blue': (70, 140, 200),            # calm blue
    'gray': (120, 132, 140),
    'red': (190, 70, 60),              # subdued red
    'table_stripe': (248, 251, 249),
    'accent_line': SAGE,
    'title': "OPTION E \u2014 Calm & Reassuring",
    'subtitle': "FOR COMPARISON",
    'description': "Slate blue + sage green: serene confidence \u2014 \"relax, your shipment is in good hands\"",
    'palette': [
        ("#37506c", "Slate Blue", SLATE_BLUE),
        ("#445f7d", "Slate Mid", SLATE_BLUE_MID),
        ("#55708e", "Slate Light", SLATE_BLUE_LIGHT),
        ("#689d71", "Sage", SAGE),
        ("#5a8f63", "Sage Hover", SAGE_HOVER),
        ("#f5f8f6", "Body BG", (245, 248, 246)),
        ("#ffffff", "Card White", (255, 255, 255)),
    ],
}, "design-mockup-e.png")
