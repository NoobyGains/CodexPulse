"""Generate synthetic README artwork. Optional developer dependency: Pillow."""
from pathlib import Path
import sys

from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from codexpulse.render import THEMES

OUT = ROOT / "assets"
OUT.mkdir(exist_ok=True)
FONT_PATHS = ["C:/Windows/Fonts/consola.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSansMono.ttf", "/System/Library/Fonts/Menlo.ttc"]
FONT = next((p for p in FONT_PATHS if Path(p).exists()), None)

def font(size):
    return ImageFont.truetype(FONT, size) if FONT else ImageFont.load_default(size=size)

def surface(width, height):
    img = Image.new("RGB", (width, height), "#0c1017")
    draw = ImageDraw.Draw(img)
    draw.rounded_rectangle((1, 1, width-2, height-2), radius=18, outline="#283444", width=2)
    for x, color in zip((28, 49, 70), ("#ff8272", "#fbbf24", "#4ade80")):
        draw.ellipse((x, 21, x+10, 31), fill=color)
    return img, draw

def draw_widget(draw, x, y, label, pct, theme, size=190):
    tone = theme["low" if pct < 50 else "mid" if pct < 80 else "high"]
    draw.text((x, y), label, fill="#d8e2ee", font=font(19))
    draw.text((x+size-47, y), f"{pct}%", fill=tone, font=font(19))
    draw.rounded_rectangle((x, y+34, x+size, y+40), radius=3, fill="#263140")
    if pct:
        draw.rounded_rectangle((x, y+34, x+size*pct/100, y+40), radius=3, fill=tone)

def main():
    frames = []
    for pct in list(range(27, 98, 3)) + [96] * 8:
        img, draw = surface(1240, 255)
        draw.text((98, 14), "CodexPulse", fill="#d8e2ee", font=font(23))
        draw.text((28, 66), "Your Codex usage, at a glance.", fill="#f0f6fc", font=font(28))
        for i, (label, amount) in enumerate((("Session", pct), ("Weekly", 78), ("Model quota", 89), ("Context", 14))):
            draw_widget(draw, 30+i*300, 120, label, amount, THEMES["default"], 260)
        draw.text((30, 203), "ILLUSTRATIVE DATA  /  PULSE COMPANION  /  NATIVE CODEX FOOTER ALSO INCLUDED", fill="#94a3b8", font=font(16))
        frames.append(img)
    frames[0].save(OUT / "demo.gif", save_all=True, append_images=frames[1:], duration=160, loop=0, optimize=True)
    img, draw = surface(1240, 1040)
    draw.text((98, 13), "15 themes. One familiar pulse.", fill="#d8e2ee", font=font(24))
    for i, (name, theme) in enumerate(THEMES.items()):
        x, y = 28+(i%3)*407, 68+(i//3)*188
        draw.rounded_rectangle((x, y, x+370, y+166), radius=12, fill="#141b26", outline="#283444")
        draw.text((x+17, y+12), name, fill="#d8e2ee", font=font(22))
        for j, (pct, key) in enumerate(((27, "low"), (73, "mid"), (96, "high"))):
            yy = y+57+j*31
            draw.text((x+18, yy-5), f"{pct}%", fill=theme[key], font=font(18))
            draw.rounded_rectangle((x+75, yy, x+340, yy+7), radius=3, fill="#263140")
            draw.rounded_rectangle((x+75, yy, x+75+265*pct/100, yy+7), radius=3, fill=theme[key])
    img.save(OUT / "themes.png")

if __name__ == "__main__":
    main()
