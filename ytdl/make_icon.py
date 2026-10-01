#!/usr/bin/env python3
"""アプリのアイコンを標準ライブラリだけで描く。

赤い角丸の四角に、白い「下向き矢印＋受け皿」のダウンロード記号。

    python3 make_icon.py icon.png              # 1024×1024 の PNG（Mac 用。make_app.sh が .icns にする）
    python3 make_icon.py windows/icon.ico      # 16〜256 px を詰めた Windows 用アイコン
"""

from __future__ import annotations

import math
import struct
import sys
import zlib

SIZE = 1024  # 図形の座標はこの大きさを基準に書いてある
ICO_SIZES = (16, 24, 32, 48, 64, 256)
TOP = (255, 92, 78)  # 上端の色
BOTTOM = (212, 32, 26)  # 下端の色
STROKE = 38  # 線の太さの半分


def rounded_rect_sdf(x: float, y: float, cx: float, cy: float, half: float, r: float) -> float:
    qx = abs(x - cx) - half + r
    qy = abs(y - cy) - half + r
    outside = math.hypot(max(qx, 0.0), max(qy, 0.0))
    return outside + min(max(qx, qy), 0.0) - r


def segment_sdf(x: float, y: float, ax: float, ay: float, bx: float, by: float, w: float) -> float:
    px, py = x - ax, y - ay
    dx, dy = bx - ax, by - ay
    t = max(0.0, min(1.0, (px * dx + py * dy) / (dx * dx + dy * dy)))
    return math.hypot(px - dx * t, py - dy * t) - w


# 矢印の軸・矢じり・受け皿（線分の集まり）
GLYPH = [
    (512, 270, 512, 610),
    (512, 630, 360, 478),
    (512, 630, 664, 478),
    (300, 742, 724, 742),
    (300, 742, 300, 690),
    (724, 742, 724, 690),
]


def coverage(d: float) -> float:
    return max(0.0, min(1.0, 0.5 - d))


def render(size: int = SIZE) -> bytes:
    """size×size の PNG を返す。小さいサイズも 1024 基準の図形を縮めて描くので輪郭がにじまない。"""
    scale = size / SIZE
    rows = []
    for y in range(size):
        t = y / max(size - 1, 1)
        bg = [TOP[i] + (BOTTOM[i] - TOP[i]) * t for i in range(3)]
        row = bytearray(b"\x00")  # PNG の行フィルタ: なし
        for x in range(size):
            px, py = (x + 0.5) / scale, (y + 0.5) / scale
            a = coverage(rounded_rect_sdf(px, py, 512, 512, 412, 185) * scale)
            if a <= 0:
                row += b"\x00\x00\x00\x00"
                continue
            g = 0.0
            if 200 < py < 820 and 220 < px < 804:  # 記号のある範囲だけ計算して速くする
                g = coverage(min(segment_sdf(px, py, *s, STROKE) for s in GLYPH) * scale)
            r, gr, b = (c + (255 - c) * g for c in bg)
            row += bytes((round(r), round(gr), round(b), round(a * 255)))
        rows.append(bytes(row))
    raw = b"".join(rows)

    def chunk(tag: bytes, data: bytes) -> bytes:
        return struct.pack(">I", len(data)) + tag + data + struct.pack(">I", zlib.crc32(tag + data))

    ihdr = struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0)
    return b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b"")


def render_ico() -> bytes:
    """PNG を詰めた .ico（Windows Vista 以降が読める形式）を返す。"""
    images = [render(s) for s in ICO_SIZES]
    header = struct.pack("<HHH", 0, 1, len(images))
    offset = len(header) + 16 * len(images)
    entries, data = b"", b""
    for s, png in zip(ICO_SIZES, images):
        dim = 0 if s >= 256 else s  # 256 は 0 と書く決まり
        entries += struct.pack("<BBBBHHII", dim, dim, 0, 0, 1, 32, len(png), offset + len(data))
        data += png
    return header + entries + data


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "icon.png"
    with open(out, "wb") as f:
        f.write(render_ico() if out.lower().endswith(".ico") else render())
