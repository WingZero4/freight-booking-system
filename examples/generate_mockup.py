"""Generate a design mockup PNG showing the Apex-inspired color scheme."""
from PIL import Image, ImageDraw, ImageFont
import os

W, H = 1200, 2400
NAVY_DARK = (30, 42, 74)
NAVY_MID = (42, 55, 90)
NAVY_LIGHT = (55, 68, 108)
CRIMSON = (139, 26, 43)
CRIMSON_HOVER = (160, 25, 45)
BODY_BG = (240, 242, 245)
CARD_BG = (255, 255, 255)
TEXT_DARK = (26, 26, 46)
TEXT_MUTED = (108, 117, 125)
BORDER = (224, 227, 232)
WHITE = (255, 255, 255)
GREEN = (25, 135, 84)
AMBER = (230, 168, 23)
BLUE = (13, 110, 253)
CYAN = (13, 202, 240)
GRAY = (108, 117, 125)
TABLE_STRIPE = (248, 249, 250)

# Try to find a good font
def get_font(size, bold=False):
    candidates = [
        "C:/Windows/Fonts/segoeui.ttf",
        "C:/Windows/Fonts/segoeuib.ttf",
        "C:/Windows/Fonts/arial.ttf",
        "C:/Windows/Fonts/arialbd.ttf",
    ]
    if bold:
        bold_candidates = [
            "C:/Windows/Fonts/segoeuib.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
        for f in bold_candidates:
            if os.path.exists(f):
                return ImageFont.truetype(f, size)
    for f in candidates:
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

img = Image.new('RGB', (W, H), BODY_BG)
draw = ImageDraw.Draw(img)

y = 0

# ─── Helper functions ───────────────────────────────────────────────
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
    for i, (col, w) in enumerate(zip(cols, widths)):
        draw.text((cx + 8, y + 8), str(col), fill=fg, font=font_r)
        # Vertical line
        draw.line([(cx, y), (cx, y + row_h)], fill=BORDER, width=1)
        cx += w
    draw.line([(cx, y), (cx, y + row_h)], fill=BORDER, width=1)
    draw.line([(x, y + row_h), (x + sum(widths), y + row_h)], fill=BORDER, width=1)
    return y + row_h

# ─── SECTION LABEL ──────────────────────────────────────────────────
def section_label(y, text):
    draw.text((30, y), text, fill=CRIMSON, font=font_title)
    draw.line([(30, y + 22), (W - 30, y + 22)], fill=CRIMSON, width=2)
    return y + 35

# ═══════════════════════════════════════════════════════════════════
# NAVBAR
# ═══════════════════════════════════════════════════════════════════
draw.rectangle([0, y, W, y + 56], fill=NAVY_DARK)
draw.text((30, y + 16), "\u2693  Freight Booking", fill=WHITE, font=font_xl)
nav_items = ["Dashboard", "Bookings", "New Booking", "Address Book"]
nx = 350
for item in nav_items:
    tw = draw.textlength(item, font=font_md)
    if item == "Bookings":
        rounded_rect(nx - 6, y + 12, nx + tw + 6, y + 44, fill=(255, 255, 255, 30))
        draw.text((nx, y + 18), item, fill=WHITE, font=font_md_b)
    else:
        draw.text((nx, y + 18), item, fill=(200, 200, 220), font=font_md)
    nx += tw + 30

# User info
draw.text((W - 280, y + 18), "acme_user (ACME)", fill=(180, 180, 200), font=font_sm)
rounded_rect(W - 120, y + 14, W - 30, y + 40, fill=NAVY_LIGHT, radius=4)
draw.text((W - 110, y + 18), "Logout", fill=(200, 200, 220), font=font_sm)

y += 56

# ═══════════════════════════════════════════════════════════════════
# TITLE
# ═══════════════════════════════════════════════════════════════════
y += 20
draw.text((30, y), "DESIGN MOCKUP \u2014 Apex-Inspired Color Scheme", fill=NAVY_DARK, font=font_xxl)
y += 45

# ═══════════════════════════════════════════════════════════════════
# BOOKING DETAIL HEADER
# ═══════════════════════════════════════════════════════════════════
y = section_label(y, "BOOKING DETAIL HEADER")

# Navy gradient header
header_h = 100
for i in range(header_h):
    r = int(NAVY_DARK[0] + (NAVY_MID[0] - NAVY_DARK[0]) * i / header_h)
    g = int(NAVY_DARK[1] + (NAVY_MID[1] - NAVY_DARK[1]) * i / header_h)
    b = int(NAVY_DARK[2] + (NAVY_MID[2] - NAVY_DARK[2]) * i / header_h)
    draw.line([(30, y + i), (W - 30, y + i)], fill=(r, g, b))

draw.text((50, y + 16), "BK-202602-0001", fill=WHITE, font=font_xxl)
draw.text((50, y + 50), "Sea FCL  \u00b7  USNYC \u2192 CNSHA  \u00b7  1x 20GP  \u00b7  FOB", fill=(180, 185, 210), font=font_md)
# Status badge
badge(W - 160, y + 22, "Confirmed", GREEN)

# Action buttons row
btn_y = y + header_h - 2
draw.rectangle([30, btn_y, W - 30, btn_y + 40], fill=NAVY_MID)
draw.line([(30, btn_y), (W - 30, btn_y)], fill=(60, 65, 90), width=1)
bx = 50
for label, bg in [("Carrier Details", CRIMSON), ("In Transit", BLUE), ("Cancel", NAVY_LIGHT), ("Back to List", NAVY_LIGHT)]:
    tw = draw.textlength(label, font=font_sm)
    if label == "Back to List":
        bx = W - 160
    rounded_rect(bx, btn_y + 8, bx + tw + 20, btn_y + 32, bg, radius=4)
    draw.text((bx + 10, btn_y + 12), label, fill=WHITE, font=font_sm)
    bx += tw + 30

y = btn_y + 44

# Tabs
tab_y = y + 5
tabs = ["Overview", "Cargo (3)", "Parties (2)", "Documents (4)", "Activity"]
tx = 30
for tab in tabs:
    tw = draw.textlength(tab, font=font_md)
    if tab == "Overview":
        draw.text((tx + 10, tab_y + 8), tab, fill=CRIMSON, font=font_md_b)
        draw.line([(tx + 5, tab_y + 30), (tx + tw + 15, tab_y + 30)], fill=CRIMSON, width=3)
    else:
        draw.text((tx + 10, tab_y + 8), tab, fill=TEXT_MUTED, font=font_md)
    tx += tw + 35

y = tab_y + 38

# ═══════════════════════════════════════════════════════════════════
# OVERVIEW CARD with Route + Cargo Table
# ═══════════════════════════════════════════════════════════════════
card_top = y
rounded_rect(30, y, W - 30, y + 420, CARD_BG, radius=8)
y += 20

# Route section header
draw.text((50, y), "Route & Mode", fill=CRIMSON, font=font_lg)
draw.line([(50, y + 24), (400, y + 24)], fill=CRIMSON, width=2)
y += 40

# Origin -> Destination
draw.text((50, y), "Origin", fill=TEXT_MUTED, font=font_sm)
draw.text((50, y + 18), "USNYC - New York", fill=NAVY_DARK, font=font_lg)

draw.text((480, y + 10), "\u2192", fill=CRIMSON, font=font_xxl)

draw.text((600, y), "Destination", fill=TEXT_MUTED, font=font_sm)
draw.text((600, y + 18), "CNSHA - Shanghai", fill=NAVY_DARK, font=font_lg)
y += 55

# Cargo section header
draw.text((50, y), "Cargo Summary", fill=CRIMSON, font=font_lg)
draw.line([(50, y + 24), (400, y + 24)], fill=CRIMSON, width=2)
y += 35

# Cargo table
cols_header = ["#", "Description", "Qty", "Package", "Weight", "L", "W", "H", "Vol CBM", "HS Code", "Origin", "Hazmat"]
col_w = [35, 175, 50, 80, 75, 55, 55, 55, 75, 80, 60, 100]
table_x = 50

# Header
y = draw_table_row(table_x, y, cols_header, col_w, font_r=font_sm, bg=NAVY_DARK, fg=WHITE, row_h=30)

# Data rows
rows = [
    ["1", "LCD Monitors 27\"", "50", "Carton", "500.00", "60", "40", "35", "4.200", "852872", "CN", "-"],
    ["2", "Keyboard Assy", "200", "Carton", "300.00", "-", "-", "-", "2.800", "847330", "CN", "-"],
    ["3", "Li Battery Packs", "25", "Crate", "150.00", "45", "30", "20", "0.675", "850760", "CN", "UN3481"],
]
for i, row in enumerate(rows):
    bg_r = TABLE_STRIPE if i % 2 == 0 else CARD_BG
    y = draw_table_row(table_x, y, row, col_w, bg=bg_r, row_h=30)

# Footer
y = draw_table_row(table_x, y, ["", "", "", "Totals", "950.00", "", "", "", "7.675", "", "", ""], col_w, bg=NAVY_DARK, fg=WHITE, row_h=30)

y += 15

# ═══════════════════════════════════════════════════════════════════
# DASHBOARD STATS
# ═══════════════════════════════════════════════════════════════════
y += 25
y = section_label(y, "DASHBOARD STATS")

stats = [
    ("4", "Draft", GRAY),
    ("7", "Submitted", AMBER),
    ("12", "Confirmed", GREEN),
    ("2", "Cancelled", CRIMSON),
]
sx = 30
card_w = (W - 60 - 45) // 4
for num, label, color in stats:
    rounded_rect(sx, y, sx + card_w, y + 90, CARD_BG, radius=8)
    # Left accent bar
    draw.rectangle([sx, y + 10, sx + 4, y + 80], fill=color)
    draw.text((sx + 20, y + 15), num, fill=NAVY_DARK, font=font_stat)
    draw.text((sx + 20, y + 58), label, fill=TEXT_MUTED, font=font_md)
    sx += card_w + 15

y += 110

# ═══════════════════════════════════════════════════════════════════
# BUTTONS & BADGES
# ═══════════════════════════════════════════════════════════════════
y = section_label(y, "BUTTONS & BADGES")

# Buttons row
buttons = [
    ("New Booking", CRIMSON, WHITE),
    ("Confirm", NAVY_DARK, WHITE),
    ("Cancel", CARD_BG, CRIMSON),
    ("Edit", CARD_BG, NAVY_DARK),
    ("Submit", CRIMSON, WHITE),
    ("Export CSV", NAVY_DARK, WHITE),
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

# Badges row
badges_data = [
    ("Draft", GRAY),
    ("Submitted", AMBER),
    ("Confirmed", GREEN),
    ("In Transit", BLUE),
    ("Completed", CYAN),
    ("Rejected", NAVY_MID),
    ("Cancelled", CRIMSON),
]
bx = 30
for label, bg in badges_data:
    fg = WHITE if bg not in [AMBER, CYAN] else TEXT_DARK
    bw = badge(bx, y, label, bg, fg)
    bx += bw + 10

y += 45

# ═══════════════════════════════════════════════════════════════════
# BOOKING LIST TABLE
# ═══════════════════════════════════════════════════════════════════
y = section_label(y, "BOOKING LIST")

# Card header
rounded_rect(30, y, W - 30, y + 38, NAVY_DARK, radius=8)
# Flatten bottom corners of header
draw.rectangle([30, y + 20, W - 30, y + 38], fill=NAVY_DARK)
draw.text((50, y + 10), "Recent Bookings", fill=WHITE, font=font_md_b)
y += 38

# Table
list_cols = ["Booking #", "Customer", "Route", "Mode", "Ready Date", "Status", "Action"]
list_w = [150, 185, 165, 100, 130, 130, 90]
y = draw_table_row(30, y, list_cols, list_w, bg=NAVY_DARK, fg=WHITE, row_h=32)

list_rows = [
    ["BK-202602-0001", "Acme Corp", "USNYC \u2192 CNSHA", "Sea FCL", "Feb 21, 2026", "Confirmed", "View"],
    ["BK-202602-0002", "Globex Inc", "CNSHA \u2192 USLAX", "Sea FCL", "Feb 28, 2026", "Submitted", "View"],
    ["BK-202602-0003", "Acme Corp", "HKHKG \u2192 USNYC", "Air", "Mar 05, 2026", "Draft", "View"],
]
status_colors = {"Confirmed": GREEN, "Submitted": AMBER, "Draft": GRAY}
for i, row in enumerate(list_rows):
    bg_r = TABLE_STRIPE if i % 2 == 0 else CARD_BG
    y = draw_table_row(30, y, row, list_w, bg=bg_r, row_h=32)

y += 15

# ═══════════════════════════════════════════════════════════════════
# LOGIN PAGE
# ═══════════════════════════════════════════════════════════════════
y = section_label(y, "LOGIN PAGE")

login_x = W // 2 - 200
login_w = 400

# Card with navy header
rounded_rect(login_x, y, login_x + login_w, y + 340, CARD_BG, radius=12)

# Navy header area
for i in range(120):
    r = int(NAVY_DARK[0] + (NAVY_MID[0] - NAVY_DARK[0]) * i / 120)
    g = int(NAVY_DARK[1] + (NAVY_MID[1] - NAVY_DARK[1]) * i / 120)
    b = int(NAVY_DARK[2] + (NAVY_MID[2] - NAVY_DARK[2]) * i / 120)
    if i < 12:
        draw.line([(login_x + 12 - i, y + i), (login_x + login_w - 12 + i, y + i)], fill=(r, g, b))
    else:
        draw.line([(login_x, y + i), (login_x + login_w, y + i)], fill=(r, g, b))

draw.text((login_x + 110, y + 30), "Freight Booking", fill=WHITE, font=font_xxl)
draw.text((login_x + 135, y + 68), "Customer Portal", fill=(180, 185, 210), font=font_md)

# Form fields
fy = y + 135
draw.text((login_x + 30, fy), "Username", fill=TEXT_DARK, font=font_md_b)
fy += 22
draw.rounded_rectangle([login_x + 30, fy, login_x + login_w - 30, fy + 36], radius=6, outline=BORDER, width=2, fill=WHITE)
fy += 50

draw.text((login_x + 30, fy), "Password", fill=TEXT_DARK, font=font_md_b)
fy += 22
draw.rounded_rectangle([login_x + 30, fy, login_x + login_w - 30, fy + 36], radius=6, outline=BORDER, width=2, fill=WHITE)
fy += 50

# Login button
rounded_rect(login_x + 30, fy, login_x + login_w - 30, fy + 40, CRIMSON, radius=6)
tw = draw.textlength("Login", font=font_lg)
draw.text((login_x + login_w // 2 - tw // 2, fy + 10), "Login", fill=WHITE, font=font_lg)
fy += 52
tw2 = draw.textlength("Forgot Password?", font=font_sm)
draw.text((login_x + login_w // 2 - tw2 // 2, fy), "Forgot Password?", fill=CRIMSON, font=font_sm)

y += 360

# ═══════════════════════════════════════════════════════════════════
# COLOR PALETTE
# ═══════════════════════════════════════════════════════════════════
y = section_label(y, "COLOR PALETTE")

palette = [
    ("#0f1535", "Navy Dark", NAVY_DARK),
    ("#1a1f3d", "Navy Mid", NAVY_MID),
    ("#252b4a", "Navy Light", NAVY_LIGHT),
    ("#8b1a2b", "Crimson", CRIMSON),
    ("#a0192d", "Crimson Hover", CRIMSON_HOVER),
    ("#f0f2f5", "Body BG", BODY_BG),
    ("#ffffff", "Card White", CARD_BG),
]
px = 30
swatch_w = (W - 60 - 6 * 12) // 7
for hex_c, name, rgb in palette:
    rounded_rect(px, y, px + swatch_w, y + 55, rgb, radius=8)
    if rgb in [BODY_BG, CARD_BG]:
        draw.rounded_rectangle([px, y, px + swatch_w, y + 55], radius=8, outline=BORDER, width=1)
    draw.text((px + 5, y + 62), name, fill=TEXT_DARK, font=font_sm)
    draw.text((px + 5, y + 78), hex_c, fill=TEXT_MUTED, font=font_sm)
    px += swatch_w + 12

y += 105

# Font info
draw.text((30, y), "Font: Inter (Google Fonts) \u2014 clean, modern sans-serif", fill=TEXT_DARK, font=font_md_b)
y += 22
draw.text((30, y), "Inspired by Apex Globe portal: dark navy headers/nav, crimson red accents, white cards", fill=TEXT_MUTED, font=font_sm)
y += 30

# ═══════════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════════
draw.rectangle([0, y, W, y + 45], fill=NAVY_DARK)
tw = draw.textlength("Freight Booking Portal \u00a9 2026", font=font_sm)
draw.text((W // 2 - tw // 2, y + 14), "Freight Booking Portal \u00a9 2026", fill=(120, 125, 150), font=font_sm)
y += 45

# Crop to actual content height
img = img.crop((0, 0, W, y + 10))

output_path = os.path.join(os.path.dirname(__file__), "design-mockup.png")
img.save(output_path, "PNG", quality=95)
print(f"Mockup saved to: {output_path}")
print(f"Image size: {img.size[0]}x{img.size[1]}")
