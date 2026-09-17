"""GT4 缺口识别图像管线。"""
import io
import numpy as np
from PIL import Image
from ..logger import dim


def decode_gray(png_bytes: bytes):
    img = Image.open(io.BytesIO(png_bytes)).convert("RGBA")
    arr = np.array(img).astype(np.float32)
    r, g, b, a = arr[..., 0], arr[..., 1], arr[..., 2], arr[..., 3]
    r = r * a / 255
    g = g * a / 255
    b = b * a / 255
    gray = (r * 299 + g * 587 + b * 114) / 1000
    return gray.astype(np.uint8)


def gaussian_blur(src: np.ndarray, sigma: float = 1.1) -> np.ndarray:
    k = np.array([np.exp(-(i - 2) ** 2 / (2 * sigma * sigma)) for i in range(5)])
    k /= k.sum()
    pad = np.pad(src.astype(np.float32), ((0, 0), (2, 2)), mode="edge")
    tmp = np.zeros_like(src, dtype=np.float32)
    for i, ki in enumerate(k):
        tmp += ki * pad[:, i:i + src.shape[1]]
    pad = np.pad(tmp, ((2, 2), (0, 0)), mode="edge")
    dst = np.zeros_like(src, dtype=np.float32)
    for i, ki in enumerate(k):
        dst += ki * pad[i:i + src.shape[0], :]
    return dst


def canny(src: np.ndarray, low: float, high: float) -> np.ndarray:
    h, w = src.shape
    padded = np.pad(src, 1, mode="edge")
    gx = (-padded[:-2, :-2] - 2 * padded[1:-1, :-2] - padded[2:, :-2]
          + padded[:-2, 2:] + 2 * padded[1:-1, 2:] + padded[2:, 2:])
    gy = (-padded[:-2, :-2] - 2 * padded[:-2, 1:-1] - padded[:-2, 2:]
          + padded[2:, :-2] + 2 * padded[2:, 1:-1] + padded[2:, 2:])
    mag = np.hypot(gx, gy)
    ang = np.arctan2(gy, gx)
    ang = np.where(ang < 0, ang + np.pi, ang)

    nms = np.zeros_like(mag)
    for y in range(1, h - 1):
        for x in range(1, w - 1):
            a = ang[y, x]
            if a < np.pi / 4:
                dx, dy = 1, 0
            elif a < np.pi / 2:
                dx, dy = 1, 1
            elif a < 3 * np.pi / 4:
                dx, dy = 0, 1
            else:
                dx, dy = -1, 1
            m = mag[y, x]
            m1 = mag[y + dy, x + dx]
            m2 = mag[y - dy, x - dx]
            if m >= m1 and m >= m2:
                nms[y, x] = m

    out = np.zeros((h, w), dtype=np.uint8)
    stack = []
    for y in range(h):
        for x in range(w):
            if nms[y, x] >= high:
                out[y, x] = 255
                stack.append((y, x))
    while stack:
        y, x = stack.pop()
        for dy in (-1, 0, 1):
            for dx in (-1, 0, 1):
                ny, nx = y + dy, x + dx
                if 0 <= ny < h and 0 <= nx < w:
                    if out[ny, nx] == 0 and nms[ny, nx] >= low:
                        out[ny, nx] = 255
                        stack.append((ny, nx))
    return out


def match_x(bg: np.ndarray, tpl: np.ndarray) -> int:
    bh, bw = bg.shape
    th, tw = tpl.shape
    if tw > bw or th > bh:
        return 0
    t = tpl.astype(np.float64) - tpl.mean()
    t_norm = np.sqrt((t * t).sum())
    if t_norm == 0:
        return 0

    best_x, best_score = 0, -1e18
    for oy in range(bh - th + 1):
        for ox in range(bw - tw + 1):
            win = bg[oy:oy + th, ox:ox + tw].astype(np.float64)
            wm = win - win.mean()
            num = (wm * t).sum()
            denom = np.sqrt((wm * wm).sum()) * t_norm
            score = num / denom if denom > 0 else 0
            if score > best_score:
                best_score, best_x = score, ox
    return best_x


def get_distance_original(bg_png: bytes, slice_png: bytes) -> int:
    bg_gray = decode_gray(bg_png)
    sl_gray = decode_gray(slice_png)
    bg_edges = canny(gaussian_blur(bg_gray), 100, 200)
    sl_edges = canny(gaussian_blur(sl_gray), 100, 200)
    if (sl_edges == 255).sum() < 10:
        raise ValueError("切片图无边缘特征")
    x = match_x(bg_edges, sl_edges)
    dim(f"缺口识别 x={x}")
    return x
