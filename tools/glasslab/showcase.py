"""showcase render (pure, no browser): one centred glass window on a crisp wallpaper, like a real desktop shot.

The page comes as the usual black/white capture pair → exact premultiplied colour + alpha (metrics.alpha_map). Behind
the window the wallpaper is compositor-blurred (Hyprland-ish: gaussian + vibrancy, a touch darker); around it the
wallpaper stays crisp, darkened only by the window's soft shadow. Rounded AA corners, hairline light border, no chrome
(Zen web-app windows have no toolbar)."""
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

from .metrics import alpha_map

SIZE = (2560, 1600)                 # 16:10 gallery canvas
CSS_W = 1440                        # shot viewport width (css px): radius/border are specified at this scale
RADIUS = 14                         # css px
BORDER = (255, 255, 255, 0.12)      # hairline inner stroke
SHADOWS = [                          # (dy, sigma, opacity) as share of canvas height/width: ambient + contact
    (0.018, 0.022, 0.50),
    (0.003, 0.004, 0.22),
]


def f32(img):
    return np.asarray(img.convert("RGB"), dtype=np.float32)


def u8(a):
    return Image.fromarray(np.clip(np.rint(a), 0, 255).astype("uint8"))


def cover(img, size):
    """scale to cover size, centre crop"""
    W, H = size
    s = max(W / img.width, H / img.height)
    w, h = max(W, round(img.width * s)), max(H, round(img.height * s))
    x, y = (w - W) // 2, (h - H) // 2
    return img.convert("RGB").resize((w, h), Image.LANCZOS).crop((x, y, x + W, y + H))


def blurred(wall, sigma=28, vibrancy=0.17, brightness=0.94):
    """compositor blur behind the window: gaussian (σ at 2560 wide, scaled) + Hyprland-style vibrancy, slightly dimmer"""
    a = f32(wall.filter(ImageFilter.GaussianBlur(sigma * wall.width / 2560)))
    grey = a.mean(axis=2, keepdims=True)
    return u8((grey + (a - grey) * (1 + vibrancy)) * brightness)


def window_rect(size, cap, share=0.6, max_h=0.8):
    """centred window [x, y, w, h]: share of canvas width, capture aspect, never taller than max_h of the canvas"""
    W, H = size
    w = round(W * share)
    h = round(w * cap[1] / cap[0])
    if h > max_h * H:
        h = round(max_h * H)
        w = round(h * cap[0] / cap[1])
    return (W - w) // 2, (H - h) // 2, w, h


def radius_px(w):
    return max(2, round(RADIUS * w / CSS_W))


def rounded_mask(w, h, r, inset=0, ss=4):
    """anti-aliased rounded-rect coverage [0, 1] (supersampled), optionally inset by `inset` px"""
    m = Image.new("L", (w * ss, h * ss), 0)
    i = inset * ss
    ImageDraw.Draw(m).rounded_rectangle((i, i, w * ss - 1 - i, h * ss - 1 - i), radius=max(0, r - inset) * ss, fill=255)
    return np.asarray(m.resize((w, h), Image.BOX), dtype=np.float32) / 255


def page(black, white, size):
    """resized page → (premultiplied colour, alpha)"""
    b, w = black.convert("RGB").resize(size, Image.LANCZOS), white.convert("RGB").resize(size, Image.LANCZOS)
    a = alpha_map(b, w)[..., None]
    return np.minimum(f32(b), 255 * a), a


def shadow(size, rect, r):
    """canvas multiplier [0, 1]: soft drop shadow of the window (ambient + contact)"""
    W, H = size
    x, y, w, h = rect
    k = np.ones((H, W), np.float32)
    for dy, sigma, op in SHADOWS:
        m = Image.new("L", size, 0)
        oy = round(dy * H)
        ImageDraw.Draw(m).rounded_rectangle((x, y + oy, x + w - 1, y + h - 1 + oy), radius=r, fill=255)
        s = np.asarray(m.filter(ImageFilter.GaussianBlur(sigma * W)), dtype=np.float32) / 255
        k *= 1 - op * s
    return k[..., None]


def render(black, white, wallpaper, *, size=SIZE, width_share=0.6, max_h=0.8):
    """black/white capture + wallpaper → finished showcase image"""
    wall = cover(wallpaper, size)
    x, y, w, h = rect = window_rect(size, black.size, width_share, max_h)
    r = radius_px(w)
    colour, alpha = page(black, white, (w, h))
    behind = f32(blurred(wall))[y:y + h, x:x + w]
    win = colour + (1 - alpha) * behind
    t = max(1, round(w / CSS_W))
    ring = (rounded_mask(w, h, r) - rounded_mask(w, h, r, inset=t))[..., None] * BORDER[3]
    win = win * (1 - ring) + np.array(BORDER[:3], np.float32) * ring
    out = f32(wall) * shadow(size, rect, r)
    m = rounded_mask(w, h, r)[..., None]
    out[y:y + h, x:x + w] = out[y:y + h, x:x + w] * (1 - m) + win * m
    return u8(out)


def save(img, stem, web_w=1280):
    """→ <stem>.jpg (full, q90) + <stem>.webp (web_w wide)"""
    stem = Path(stem)
    stem.parent.mkdir(parents=True, exist_ok=True)
    jpg, webp = Path(f"{stem}.jpg"), Path(f"{stem}.webp")
    img.save(jpg, quality=90, subsampling=0)
    img.resize((web_w, round(img.height * web_w / img.width)), Image.LANCZOS).save(webp, quality=88, method=6)
    return [jpg, webp]
