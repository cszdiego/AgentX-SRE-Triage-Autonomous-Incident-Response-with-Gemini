"""
Generates evidence/error_screenshot.png — a realistic Redis error terminal screenshot.
Run ONCE before the demo:  python scripts/generate_screenshot.py
Requires: Pillow (already in backend/requirements.txt)
"""
from PIL import Image, ImageDraw, ImageFont
import os, sys

OUT_PATH = os.path.join(os.path.dirname(__file__), "..", "evidence", "error_screenshot.png")

W, H = 900, 560
BG      = (18, 18, 18)       # near-black terminal
RED     = (255, 85, 85)
YELLOW  = (255, 215, 0)
GREEN   = (80, 200, 120)
CYAN    = (80, 200, 220)
WHITE   = (220, 220, 220)
GRAY    = (120, 120, 120)
ORANGE  = (255, 165, 0)

img  = Image.new("RGB", (W, H), BG)
draw = ImageDraw.Draw(img)

# ── Terminal title bar ───────────────────────────────────────────────────────
draw.rectangle([0, 0, W, 30], fill=(40, 40, 40))
for x, col in [(14, (255,95,87)), (34, (255,189,46)), (54, (39,201,63))]:
    draw.ellipse([x-6, 9, x+6, 21], fill=col)
draw.text((W//2 - 80, 8), "sre_backend — basket-api logs", fill=GRAY)

# ── Header bar ──────────────────────────────────────────────────────────────
draw.rectangle([0, 30, W, 60], fill=(28, 28, 28))
draw.text((10, 38), "AgentX SRE-Triage — Live Error Capture", fill=CYAN)
draw.text((W - 230, 38), "2026-04-09 13:58:01 UTC", fill=GRAY)

# ── Log lines ────────────────────────────────────────────────────────────────
lines = [
    (GRAY,   "2026-04-09 13:58:01.234"),
    (RED,    " [CRIT] "),
    (WHITE,  "Basket.API — RedisConnectionException"),
    None,
    (GRAY,   "2026-04-09 13:58:01.234"),
    (RED,    " [ERROR] "),
    (ORANGE, "StackExchange.Redis.ConnectionMultiplexer"),
    None,
    (WHITE,  "  Message  : No connection available to service this operation: HGET basket_user_8821"),
    (WHITE,  "  Stack    : RedisBasketRepository.GetBasketAsync(String customerId)"),
    (WHITE,  "             BasketService.GetBasket(GetBasketRequest, ServerCallContext)"),
    None,
    (GRAY,   "2026-04-09 13:58:02.891"),
    (YELLOW, " [WARN]  "),
    (WHITE,  "Basket.API — Redis reconnect attempt 1/5 failed. Waiting 5000ms..."),
    None,
    (GRAY,   "2026-04-09 13:58:08.334"),
    (RED,    " [CRIT]  "),
    (WHITE,  "Basket.API — All Redis reconnect attempts exhausted. Service DEGRADED."),
    None,
    (GRAY,   "2026-04-09 13:58:09.001"),
    (RED,    " [ERROR] "),
    (WHITE,  "WebApp — Checkout button disabled. Basket unavailable for ALL users."),
]

y = 75
try:
    mono = ImageFont.truetype("consola.ttf", 14)
except:
    try:
        mono = ImageFont.truetype("DejaVuSansMono.ttf", 14)
    except:
        mono = ImageFont.load_default()

for item in lines:
    if item is None:
        y += 6
        continue
    if isinstance(item, tuple) and len(item) == 2:
        color, text = item
        draw.text((10, y), text, fill=color, font=mono)
        y += 20
    else:
        # multi-segment line — already handled above
        y += 20

# ── Impact box ───────────────────────────────────────────────────────────────
draw.rectangle([10, H - 145, W - 10, H - 10], fill=(30, 15, 15), outline=RED, width=2)
draw.text((20, H - 135), "── IMPACT METRICS ──────────────────────────────────────────────", fill=RED, font=mono)
draw.text((20, H - 112), "  Affected sessions  : ~3,200 active users", fill=WHITE, font=mono)
draw.text((20, H - 90),  "  Failed checkouts   : 487 in last 10 minutes", fill=WHITE, font=mono)
draw.text((20, H - 68),  "  Revenue at risk    : $24,350  (avg $50/order × 487)", fill=YELLOW, font=mono)
draw.text((20, H - 46),  "  Redis last restart : 2026-04-09 13:45:00 UTC (maintenance)", fill=ORANGE, font=mono)
draw.text((20, H - 24),  "  Root service       : Basket.API → RedisBasketRepository.cs", fill=GREEN, font=mono)

# ── Save ─────────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(OUT_PATH), exist_ok=True)
img.save(OUT_PATH, "PNG")
print(f"[OK] Screenshot saved -> {os.path.abspath(OUT_PATH)}")
print("  Attach this file when submitting the checkout failure incident.")
