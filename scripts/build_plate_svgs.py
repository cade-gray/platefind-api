#!/usr/bin/env python3
"""Draw every US plate design as a self-contained SVG.

Source of truth for the `plates.svg_code` column. Run it and commit what it
writes:

    python3 scripts/build_plate_svgs.py

Outputs
  plate-svgs/<slug>.svg          one file per plate, for eyeballing and editing
  migrations/002_plate_svgs.sql  UPDATE statements keyed on `state`
  plate-svgs/preview.html        all 51 on one page

Every SVG is a 300x150 (2:1, the real 12x6 in plate ratio) viewBox with no
external references, so it can be inlined anywhere. Gradient and clip ids are
prefixed with the state slug because a board renders all 51 into one document
and duplicate ids would cross-wire the fills.
"""

import html
import math
import os
import re

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
SVG_DIR = os.path.join(ROOT, "plate-svgs")
SQL_PATH = os.path.join(ROOT, "migrations", "002_plate_svgs.sql")

W, H = 300, 150
SANS = "'Helvetica Neue',Helvetica,Arial,sans-serif"
CONDENSED = "'Helvetica Neue',Arial,sans-serif"
SERIF = "Georgia,'Times New Roman',serif"

# ---------------------------------------------------------------- primitives

def esc(text):
    return html.escape(str(text), quote=True)


def text(x, y, body, size, fill, weight="700", ls=0, family=SANS,
         anchor="middle", style=None, opacity=None, extra=""):
    bits = [
        f'x="{x}"', f'y="{y}"', f'font-family="{family}"',
        f'font-size="{size}"', f'font-weight="{weight}"',
        f'fill="{fill}"', f'text-anchor="{anchor}"',
    ]
    if ls:
        bits.append(f'letter-spacing="{ls}"')
    if style:
        bits.append(f'font-style="{style}"')
    if opacity is not None:
        bits.append(f'opacity="{opacity}"')
    if extra:
        bits.append(extra)
    return f'<text {" ".join(bits)}>{esc(body)}</text>'


def star(cx, cy, r, fill, rot=-90, inner=0.42, opacity=None):
    pts = []
    for i in range(10):
        ang = math.radians(rot + i * 36)
        rr = r if i % 2 == 0 else r * inner
        pts.append(f"{cx + rr * math.cos(ang):.1f},{cy + rr * math.sin(ang):.1f}")
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return f'<polygon points="{" ".join(pts)}" fill="{fill}"{op}/>'


def fir(cx, base, h, w, fill, opacity=None):
    """A conifer: three stacked skirts over a trunk."""
    op = f' opacity="{opacity}"' if opacity is not None else ""
    trunk = f'<rect x="{cx - w * 0.07:.1f}" y="{base - h * 0.16:.1f}" width="{w * 0.14:.1f}" height="{h * 0.18:.1f}" fill="{fill}"/>'
    skirts = []
    for i, (top, bot, spread) in enumerate(
        ((0.00, 0.44, 0.58), (0.26, 0.70, 0.80), (0.50, 0.86, 1.0))
    ):
        ty = base - h * (1 - top)
        by = base - h * (1 - bot)
        hw = w * spread / 2
        skirts.append(
            f'<polygon points="{cx:.1f},{ty:.1f} {cx + hw:.1f},{by:.1f} {cx - hw:.1f},{by:.1f}"/>'
        )
    return f'<g fill="{fill}"{op}>{trunk}{"".join(skirts)}</g>'


def ridge(points, fill, opacity=None):
    """A closed mountain silhouette; points are (x, y) peaks, floored at H."""
    op = f' opacity="{opacity}"' if opacity is not None else ""
    body = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
    return f'<polygon points="{body}" fill="{fill}"{op}/>'


def zia(cx, cy, r, fill, arm=None, opacity=None):
    """Zia sun: a ring with four groups of four rays."""
    arm = arm or r * 1.15
    op = f' opacity="{opacity}"' if opacity is not None else ""
    t = r * 0.30
    gap = r * 0.62
    rays = []
    for a in (0, 90, 180, 270):
        for i, ln in enumerate((0.62, 1.0, 1.0, 0.62)):
            off = (i - 1.5) * gap
            rays.append(
                f'<rect x="{r * 1.25:.1f}" y="{off - t / 2:.1f}" width="{arm * ln:.1f}" '
                f'height="{t:.1f}" transform="rotate({a})"/>'
            )
    return (
        f'<g transform="translate({cx},{cy})" fill="{fill}"{op}>'
        f'<circle r="{r:.1f}" fill="none" stroke="{fill}" stroke-width="{r * 0.42:.1f}"/>'
        f'{"".join(rays)}</g>'
    )


def waves(y, fill, opacity=None, rows=3, span=(6, 294), amp=5, step=26):
    op = f' opacity="{opacity}"' if opacity is not None else ""
    out = []
    x0, x1 = span
    for r in range(rows):
        yy = y + r * (amp * 1.6)
        d = [f"M{x0} {yy:.1f}"]
        x = x0
        up = True
        while x < x1:
            d.append(f"q{step / 2:.1f} {-amp if up else amp} {step} 0")
            x += step
            up = not up
        out.append(f'<path d="{" ".join(d)}" fill="none" stroke="{fill}" stroke-width="3.4" stroke-linecap="round"/>')
    return f"<g{op}>{''.join(out)}</g>"


def linear(gid, stops, x1="0", y1="0", x2="0", y2="1"):
    body = "".join(
        f'<stop offset="{o}" stop-color="{c}"{f" stop-opacity=\"{a}\"" if a is not None else ""}/>'
        for o, c, a in stops
    )
    return f'<linearGradient id="{gid}" x1="{x1}" y1="{y1}" x2="{x2}" y2="{y2}">{body}</linearGradient>'


# ------------------------------------------------------------------ assembly

def build(spec):
    slug = spec["slug"]
    defs = spec.get("defs", "")
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {W} {H}" width="100%" '
        f'height="100%" preserveAspectRatio="xMidYMid meet" role="img" '
        f'aria-label="{esc(spec["state"])} license plate: {esc(spec["design"])}">'
    ]
    clip = f'<clipPath id="{slug}-clip"><rect width="{W}" height="{H}" rx="15"/></clipPath>'
    parts.append(f"<defs>{clip}{defs}</defs>")
    parts.append(f'<rect width="{W}" height="{H}" rx="15" fill="{spec["face"]}"/>')
    art = spec.get("art", "")
    if art:
        # scenery runs to the edges; the clip keeps it inside the rounded corners
        parts.append(f'<g clip-path="url(#{slug}-clip)">{art}</g>')

    name_y = spec.get("name_y", 27)
    if spec.get("name"):
        parts.append(text(
            spec.get("name_x", 150), name_y, spec["name"],
            spec.get("name_size", 20), spec["name_fill"],
            weight=spec.get("name_weight", "700"),
            ls=spec.get("name_ls", 2.2),
            family=spec.get("name_family", SANS),
            style=spec.get("name_style"),
        ))

    serial = spec.get("serial")
    if serial:
        parts.append(text(
            spec.get("serial_x", 150), spec.get("serial_y", 102), serial,
            spec.get("serial_size", 46), spec["serial_fill"],
            weight="700", ls=spec.get("serial_ls", 3),
            family=CONDENSED,
        ))
    for extra in spec.get("serial_extra", []):
        parts.append(extra)

    if spec.get("slogan"):
        parts.append(text(
            spec.get("slogan_x", 150), spec.get("slogan_y", 138), spec["slogan"],
            spec.get("slogan_size", 13), spec["slogan_fill"],
            weight=spec.get("slogan_weight", "700"),
            ls=spec.get("slogan_ls", 0.8),
            family=spec.get("slogan_family", SANS),
            style=spec.get("slogan_style"),
        ))

    parts.append(spec.get("over", ""))
    rim = spec.get("rim", "rgba(0,0,0,.30)")
    parts.append(
        f'<rect x="4.5" y="4.5" width="291" height="141" rx="11" fill="none" '
        f'stroke="{rim}" stroke-width="2" opacity="{spec.get("rim_opacity", ".45")}"/>'
    )
    parts.append(
        f'<rect x=".9" y=".9" width="298.2" height="148.2" rx="14.2" fill="none" '
        f'stroke="rgba(0,0,0,.32)" stroke-width="1.8"/>'
    )
    parts.append("</svg>")
    svg = "".join(parts)
    # ids are namespaced at author time; assert it so a copy-paste slip is loud
    for found in re.findall(r'id="([^"]+)"', svg):
        assert found.startswith(slug + "-"), f"{slug}: un-namespaced id {found!r}"
    return svg


# ------------------------------------------------------------------- motifs
# Each motif is authored in a local box and placed with translate/scale, so the
# same drawing can sit small in a corner or large behind the serial.

def g(x, y, s, fill, body, opacity=None):
    op = f' opacity="{opacity}"' if opacity is not None else ""
    return f'<g transform="translate({x},{y}) scale({s})" fill="{fill}"{op}>{body}</g>'


def saguaro(x, y, s, fill, opacity=None):
    body = (
        '<rect x="20" y="8" width="16" height="82" rx="8"/>'
        '<path d="M20 40 h-8 a7 7 0 0 0-7 7 v14 a7 7 0 0 0 7 7 h1 v-13 a2 2 0 0 1 2-2 h5z"/>'
        '<path d="M36 30 h7 a7 7 0 0 1 7 7 v22 a7 7 0 0 1-7 7 h-1 v-21 a2 2 0 0 0-2-2 h-4z"/>'
    )
    return g(x, y, s, fill, body, opacity)


def wheat(x, y, s, fill, opacity=None):
    grains = []
    for i in range(7):
        yy = 6 + i * 9
        grains.append(f'<ellipse cx="14" cy="{yy + 4}" rx="8" ry="5.5" transform="rotate(-32 14 {yy + 4})"/>')
        grains.append(f'<ellipse cx="36" cy="{yy + 4}" rx="8" ry="5.5" transform="rotate(32 36 {yy + 4})"/>')
    body = '<rect x="22" y="30" width="6" height="70" rx="3"/>' + "".join(grains)
    return g(x, y, s, fill, body, opacity)


def horse(x, y, s, fill, opacity=None, rear=False):
    """Stylised horse in a 100-wide box: galloping, or bucking (Steamboat)."""
    if not rear:
        body = (
            '<ellipse cx="44" cy="46" rx="29" ry="16"/>'
            '<path d="M60 38 L78 14 L90 10 L96 20 L78 30 L70 42 L62 52 Z"/>'
            '<path d="M86 8 L100 12 L97 24 L82 21 Z"/>'
            '<path d="M18 32 C6 24 0 28 0 38 C8 36 14 38 20 46 Z"/>'
            '<path d="M22 56 L12 78 L4 92 L20 94 L30 78 L38 60 Z"/>'
            '<path d="M40 58 L38 80 L34 94 L50 95 L54 80 L56 58 Z"/>'
            '<path d="M54 54 L62 72 L70 86 L82 80 L72 66 L68 50 Z"/>'
            '<path d="M62 48 L78 62 L88 72 L98 64 L84 54 L74 42 Z"/>'
        )
    else:
        body = (
            '<ellipse cx="54" cy="44" rx="29" ry="16" transform="rotate(-30 54 44)"/>'
            '<path d="M38 32 L16 58 L6 50 L30 24 Z"/>'
            '<path d="M16 58 L2 70 L0 58 L10 46 Z"/>'
            '<path d="M30 24 L27 12 L37 20 Z"/>'
            '<path d="M30 56 L16 72 L26 80 L40 66 Z"/>'
            '<path d="M44 62 L34 82 L46 88 L54 68 Z"/>'
            '<path d="M72 32 L92 20 L99 30 L78 44 Z"/>'
            '<path d="M76 46 L96 42 L99 54 L80 58 Z"/>'
            '<path d="M80 28 C92 16 100 14 100 4 C93 12 85 17 76 21 Z"/>'
        )
    return g(x, y, s, fill, body, opacity)


def bird(x, y, s, fill, opacity=None, tail="short"):
    """Perched songbird. `tail="fork"` gives the scissor-tailed flycatcher."""
    tails = {
        "short": '<path d="M34 56 L6 76 L12 82 L38 64 Z"/>',
        "fork": ('<path d="M34 54 L2 92 L10 96 L38 62 Z"/>'
                 '<path d="M36 60 L18 104 L28 106 L42 68 Z"/>'),
    }
    body = (
        '<ellipse cx="54" cy="44" rx="23" ry="15" transform="rotate(-26 54 44)"/>'
        '<circle cx="76" cy="22" r="12"/>'
        '<path d="M86 17 L104 22 L86 28 Z"/>'
        '<circle cx="80" cy="19" r="2.2" fill="#ffffff" fill-opacity=".55"/>'
        '<path d="M46 34 C58 30 70 38 72 52 C60 60 46 54 42 43 Z" fill-opacity=".55"/>'
        '<rect x="54" y="56" width="4" height="16" rx="2"/>'
        '<rect x="64" y="54" width="4" height="18" rx="2"/>'
        + tails[tail]
    )
    return g(x, y, s, fill, body, opacity)


def pelican(x, y, s, fill, opacity=None):
    """Brown pelican: the long hooked bill and throat pouch carry the read."""
    body = (
        '<path d="M10 64 C10 48 26 38 46 40 C60 42 68 50 70 60 C72 74 60 86 42 86 '
        'C24 86 10 78 10 64 Z"/>'
        '<path d="M56 48 C52 32 58 14 72 12 C84 10 92 18 92 28 L84 30 C84 22 80 18 75 21 '
        'C67 26 64 38 66 50 Z"/>'
        '<path d="M90 22 L100 27 L74 74 L64 68 Z"/>'
        '<path d="M74 74 L64 68 C60 76 66 84 74 82 Z"/>'
        '<path d="M84 32 C92 44 90 60 78 70 C76 56 78 42 82 34 Z" fill-opacity=".45"/>'
        '<circle cx="80" cy="24" r="2.6" fill="#ffffff" fill-opacity=".6"/>'
        '<path d="M18 52 C30 46 48 52 54 66 C40 78 22 70 14 58 Z" fill-opacity=".5"/>'
        '<rect x="34" y="82" width="5" height="14" rx="2"/>'
        '<rect x="50" y="82" width="5" height="14" rx="2"/>'
        '<path d="M26 96 h20 l-2 5 h-20 Z"/><path d="M42 96 h20 l-2 5 h-20 Z"/>'
    )
    return g(x, y, s, fill, body, opacity)


def guitar(x, y, s, fill, opacity=None):
    """Two bouts and a waist — the outline that actually reads as a guitar."""
    body = (
        '<circle cx="40" cy="74" r="25"/>'
        '<circle cx="40" cy="42" r="18"/>'
        '<path d="M23 40 h34 v36 h-34 Z"/>'
        '<rect x="36" y="4" width="9" height="34" rx="2" transform="rotate(24 40 22)"/>'
        '<rect x="46" y="-4" width="15" height="13" rx="3" transform="rotate(24 53 2)"/>'
    )
    detail = (
        '<circle cx="40" cy="56" r="8" fill="#ffffff" fill-opacity=".8"/>'
        '<rect x="34" y="76" width="12" height="4" rx="2" fill="#ffffff" fill-opacity=".55"/>'
    )
    return g(x, y, s, fill, body + detail, opacity)


def lighthouse(x, y, s, fill, opacity=None):
    body = (
        '<path d="M34 26 h20 l8 56 h-36 Z"/>'
        '<rect x="30" y="16" width="28" height="10" rx="3"/>'
        '<rect x="36" y="4" width="16" height="12" rx="3"/>'
        '<path d="M18 82 h52 l6 14 h-64 Z"/>'
        '<rect x="34" y="40" width="20" height="7" fill="#ffffff" fill-opacity=".55"/>'
        '<rect x="31" y="58" width="26" height="7" fill="#ffffff" fill-opacity=".55"/>'
    )
    return g(x, y, s, fill, body, opacity)


def suspension_bridge(x, y, s, fill, opacity=None):
    cables = "".join(
        f'<rect x="{18 + i * 8}" y="{58 - (26 - abs(50 - (18 + i * 8)) * 0.52):.1f}" width="2.4" '
        f'height="{(26 - abs(50 - (18 + i * 8)) * 0.52):.1f}" />'
        for i in range(1, 9)
    )
    body = (
        '<rect x="0" y="58" width="100" height="7"/>'
        '<rect x="16" y="14" width="6" height="51"/><rect x="78" y="14" width="6" height="51"/>'
        '<path d="M19 18 C40 46 60 46 81 18 L81 26 C60 52 40 52 19 26 Z"/>'
        '<path d="M0 30 C8 24 14 20 19 18 L19 26 C13 29 7 33 0 38 Z"/>'
        '<path d="M100 30 C92 24 86 20 81 18 L81 26 C87 29 93 33 100 38 Z"/>'
        + cables
    )
    return g(x, y, s, fill, body, opacity)


def arch_bridge(x, y, s, fill, opacity=None):
    """New River Gorge: a single steel arch under a straight deck."""
    posts = "".join(
        f'<rect x="{10 + i * 11.5}" y="22" width="3.4" '
        f'height="{max(4, 46 - abs(50 - (11.7 + i * 11.5)) * 0.86):.1f}"/>'
        for i in range(8)
    )
    body = (
        '<rect x="0" y="16" width="100" height="6"/>'
        '<path d="M2 74 C20 16 80 16 98 74 L88 74 C72 30 28 30 12 74 Z"/>'
        '<rect x="0" y="66" width="14" height="12"/><rect x="86" y="66" width="14" height="12"/>'
        + posts
    )
    return g(x, y, s, fill, body, opacity)


def barn(x, y, s, fill, opacity=None):
    body = (
        '<path d="M8 48 L36 24 L64 48 L64 96 L8 96 Z"/>'
        '<path d="M0 50 L36 20 L72 50 L64 58 L36 34 L8 58 Z"/>'
        '<rect x="76" y="30" width="22" height="66" rx="4"/>'
        '<path d="M74 30 q13 -16 26 0 Z"/>'
        '<rect x="26" y="64" width="20" height="32" fill="#ffffff" fill-opacity=".5"/>'
        '<path d="M26 64 L46 96 M46 64 L26 96" stroke="#ffffff" stroke-opacity=".5" '
        'stroke-width="3" fill="none"/>'
    )
    return g(x, y, s, fill, body, opacity)


def delicate_arch(x, y, s, fill, opacity=None):
    body = (
        '<path d="M10 96 C10 60 20 20 44 12 C68 4 84 30 86 60 C87 78 86 90 86 96 '
        'L70 96 C70 70 70 46 60 34 C50 22 38 34 34 56 C31 74 31 88 31 96 Z"/>'
    )
    return g(x, y, s, fill, body, opacity)


def rushmore(x, y, s, fill, opacity=None):
    """Four presidents in profile, carved into the granite face."""
    heads = []
    for hx, hy, sc in ((6, 30, 1.0), (30, 24, 1.08), (54, 32, 0.96), (76, 26, 1.02)):
        heads.append(
            f'<g transform="translate({hx},{hy}) scale({sc})">'
            # forehead, nose, lips, chin, then back of the skull
            '<path d="M20 0 C10 0 3 9 3 20 L0 25 L5 28 L3 34 L8 36 L7 43 '
            'C13 48 22 47 25 41 C28 31 28 10 20 0 Z"/>'
            '</g>'
        )
    rock = ('<path d="M0 100 L2 56 L16 38 L34 46 L52 32 L72 44 L90 36 L100 60 L100 100 Z" '
            'fill-opacity=".45"/>')
    talus = ('<path d="M0 100 L10 82 L28 90 L48 80 L70 92 L90 82 L100 98 L100 100 Z" '
             'fill-opacity=".75"/>')
    return g(x, y, s, fill, rock + "".join(heads) + talus, opacity)


def butte(x, y, s, fill, opacity=None):
    body = (
        '<path d="M4 100 L14 46 L26 40 L48 44 L58 100 Z"/>'
        '<path d="M52 100 L62 62 L74 56 L90 60 L98 100 Z"/>'
    )
    return g(x, y, s, fill, body, opacity)


def chimney_rock(x, y, s, fill, opacity=None):
    """Chimney Rock: a spire on a broad conical base."""
    body = (
        '<path d="M2 100 L26 58 L40 50 L60 50 L74 58 L98 100 Z" fill-opacity=".8"/>'
        '<path d="M36 54 L46 6 L54 6 L64 54 Z"/>'
        '<path d="M46 6 L50 0 L54 6 Z"/>'
    )
    return g(x, y, s, fill, body, opacity)


def biplane(x, y, s, fill, opacity=None):
    """Wright Flyer in side view: fuselage, stacked wings, propeller."""
    body = (
        '<path d="M8 44 L20 36 L64 34 L84 40 L94 46 L84 52 L64 56 L20 54 Z"/>'
        '<path d="M10 44 L2 20 L13 20 L24 40 Z"/>'
        '<rect x="16" y="24" width="62" height="6" rx="3"/>'
        '<rect x="16" y="60" width="62" height="6" rx="3"/>'
        '<rect x="30" y="27" width="4.5" height="36"/><rect x="62" y="27" width="4.5" height="36"/>'
        '<rect x="90" y="28" width="5" height="36" rx="2.5"/>'
    )
    return g(x, y, s, fill, body, opacity)


def torch(x, y, s, fill, opacity=None):
    rays = "".join(
        f'<rect x="47" y="-6" width="6" height="20" rx="3" transform="rotate({a} 50 40)"/>'
        for a in (-70, -50, -30, -10, 10, 30, 50, 70)
    )
    body = (
        '<path d="M50 8 C58 20 62 26 62 34 C62 44 56 50 50 50 C44 50 38 44 38 34 C38 26 42 20 50 8 Z"/>'
        '<rect x="45" y="50" width="10" height="40" rx="3"/>'
        '<rect x="36" y="48" width="28" height="7" rx="3"/>'
        '<rect x="32" y="88" width="36" height="8" rx="4"/>'
        + rays
    )
    return g(x, y, s, fill, body, opacity)


def palmetto(x, y, s, fill, opacity=None):
    """Palmetto: fronds arc out from the crown and droop, as on the state flag."""
    frond = ('<path d="M50 30 Q78 18 97 40 Q88 34 78 34 Q64 34 52 38 Z" '
             'transform="rotate({a} 50 30)"/>')
    right = "".join(frond.format(a=a) for a in (-58, -30, -4, 22, 48))
    left = f'<g transform="translate(100,0) scale(-1,1)">{right}</g>'
    crown = '<circle cx="50" cy="31" r="6"/>'
    trunk = ('<path d="M45 33 C43 56 42 78 40 99 L57 99 C56 76 55 55 55 33 Z"/>'
             '<path d="M44 52 h12 M43 66 h13 M42 80 h14" stroke="#ffffff" '
             'stroke-opacity=".35" stroke-width="2" fill="none"/>')
    return g(x, y, s, fill, trunk + right + left + crown, opacity)


def anchor(x, y, s, fill, opacity=None):
    body = (
        '<circle cx="50" cy="14" r="10" fill="none" stroke-width="7" stroke="currentColor"/>'
        '<rect x="46" y="20" width="8" height="62" rx="3"/>'
        '<rect x="26" y="32" width="48" height="8" rx="4"/>'
        '<path d="M12 58 C12 84 30 96 50 96 C70 96 88 84 88 58 L78 58 C78 78 66 86 50 86 '
        'C34 86 22 78 22 58 Z"/>'
    )
    return g(x, y, s, fill, body.replace("currentColor", fill), opacity)


def dome(x, y, s, fill, opacity=None):
    cols = "".join(f'<rect x="{26 + i * 10}" y="52" width="5" height="26"/>' for i in range(5))
    body = (
        '<rect x="14" y="78" width="72" height="22"/>'
        '<rect x="20" y="70" width="60" height="9"/>'
        '<path d="M22 52 C22 26 78 26 78 52 Z"/>'
        '<rect x="44" y="12" width="12" height="16" rx="3"/>'
        '<rect x="47" y="0" width="6" height="14"/>'
        + cols
    )
    return g(x, y, s, fill, body, opacity)


def lincoln(x, y, s, fill, opacity=None):
    """Lincoln in profile — the stovepipe hat and beard do the identifying."""
    body = (
        '<path d="M33 2 h36 l3 32 h-42 Z"/>'
        '<rect x="17" y="33" width="66" height="8" rx="3"/>'
        '<path d="M40 41 C33 42 30 50 31 59 C32 67 35 72 39 76 L37 86 L70 90 L66 74 '
        'C71 68 73 58 71 50 C69 43 62 41 56 41 Z"/>'
        '<path d="M70 52 L80 60 L69 66 Z"/>'
        '<path d="M38 70 C46 84 66 88 73 78 C75 70 71 64 69 62 C68 73 55 79 40 68 Z"/>'
        '<path d="M36 84 L30 96 L14 100 L86 100 L78 92 L68 86 Z"/>'
    )
    return g(x, y, s, fill, body, opacity)


def orange_fruit(cx, cy, r, peel="#f0891f", leaf="#3d8a45"):
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{peel}"/>'
        f'<circle cx="{cx - r * 0.3:.1f}" cy="{cy - r * 0.3:.1f}" r="{r * 0.42:.1f}" fill="#ffffff" fill-opacity=".22"/>'
        f'<path d="M{cx} {cy - r} q {r * 0.9:.1f} {-r * 0.75:.1f} {r * 1.15:.1f} {-r * 0.05:.1f} '
        f'q {-r * 0.85:.1f} {r * 0.5:.1f} {-r * 1.15:.1f} {r * 0.05:.1f} Z" fill="{leaf}"/>'
    )


def peach(cx, cy, r, skin="#f2a15c", blush="#e3663f", leaf="#3d8a45"):
    return (
        f'<circle cx="{cx}" cy="{cy}" r="{r}" fill="{skin}"/>'
        f'<path d="M{cx} {cy - r} a {r} {r} 0 0 0 0 {r * 2}" fill="{blush}" fill-opacity=".5"/>'
        f'<path d="M{cx} {cy - r * 0.98:.1f} v{r * 1.9:.1f}" stroke="{blush}" stroke-width="{r * 0.16:.1f}" fill="none"/>'
        f'<path d="M{cx} {cy - r} q {r * 0.9:.1f} {-r * 0.7:.1f} {r * 1.1:.1f} {0} '
        f'q {-r * 0.8:.1f} {r * 0.45:.1f} {-r * 1.1:.1f} {0} Z" fill="{leaf}"/>'
    )


def md_flag_band(h=22):
    """Maryland's quartered flag, run as a repeating band across the top."""
    cells = []
    for i in range(4):
        x = i * 75
        if i % 2 == 0:  # Calvert: gold and black bendy
            for j in range(10):
                x0 = x - 14 + j * 9.4
                fill = "#f0c33c" if j % 2 == 0 else "#141414"
                cells.append(
                    f'<polygon points="{x0:.1f},0 {x0 + 9.4:.1f},0 {x0 - 4.6:.1f},{h} {x0 - 14:.1f},{h}" fill="{fill}"/>'
                )
        else:  # Crossland: red and white cross
            cells.append(f'<rect x="{x}" y="0" width="75" height="{h}" fill="#c8102e"/>')
            cells.append(f'<rect x="{x}" y="{h * 0.38:.1f}" width="75" height="{h * 0.24:.1f}" fill="#ffffff"/>')
            for j in range(4):
                cells.append(f'<rect x="{x + 6 + j * 19}" y="0" width="{h * 0.24:.1f}" height="{h}" fill="#ffffff"/>')
    return f'<g clip-path="none">{"".join(cells)}</g>'


SPECS = []

SPECS.append(dict(
    slug="alabama", state="Alabama", design="Standard White Plate",
    defs=linear("alabama-face", [("0", "#ffffff", None), ("1", "#c8dcef", None)]),
    face="url(#alabama-face)",
    art='<rect y="117" width="300" height="5" fill="#17427a" opacity=".12"/>',
    name="ALABAMA", name_fill="#17427a", name_size=21, name_ls=3.4,
    serial="1AB2C34", serial_fill="#15305c",
    slogan="Sweet Home Alabama", slogan_fill="#15305c", slogan_size=15,
    slogan_family=SERIF, slogan_style="italic", rim="#17427a",
))

SPECS.append(dict(
    slug="alaska", state="Alaska", design="The Last Frontier",
    face="#e8b53a",
    art=(
        ridge([(0, 150), (0, 110), (40, 70), (68, 92), (110, 54), (150, 96),
               (196, 62), (240, 100), (272, 84), (300, 108), (300, 150)], "#ffffff", ".34")
        + ridge([(0, 150), (0, 126), (56, 100), (104, 120), (150, 104), (200, 124),
                 (252, 106), (300, 126), (300, 150)], "#14356b", ".13")
    ),
    name="ALASKA", name_fill="#14356b", name_size=22, name_ls=4,
    serial="AAA 123", serial_fill="#14356b",
    slogan="The Last Frontier", slogan_fill="#14356b", slogan_size=13, rim="#14356b",
))

SPECS.append(dict(
    slug="arizona", state="Arizona", design="Desert Sunset Plate",
    defs=linear("arizona-sun", [("0", "#f7b93c", None), ("0.55", "#e2603c", None), ("1", "#8e3060", None)]),
    face="#fbfaf6",
    art=(
        '<rect y="92" width="300" height="58" fill="url(#arizona-sun)"/>'
        + ridge([(0, 150), (0, 104), (40, 90), (80, 103), (120, 87), (170, 104),
                 (220, 89), (262, 102), (300, 91), (300, 150)], "#3a1330", ".45")
        + saguaro(12, 70, 0.62, "#2a0f24", ".92")
        + saguaro(248, 76, 0.54, "#2a0f24", ".92")
    ),
    name="ARIZONA", name_fill="#8a2432", name_size=22, name_ls=3, name_y=30,
    serial="ABC1234", serial_fill="#1b3a6b", serial_size=40, serial_y=76,
    slogan="Grand Canyon State", slogan_fill="#ffffff", slogan_size=12, slogan_y=136,
    rim="#8a2432",
))

SPECS.append(dict(
    slug="arkansas", state="Arkansas", design="Diamond State Plate",
    defs=linear("arkansas-face", [("0", "#ffffff", None), ("1", "#edf3e9", None)]),
    face="url(#arkansas-face)",
    art=(
        '<g opacity=".3"><polygon points="150,42 190,74 150,126 110,74" fill="#2f6b3f"/></g>'
        '<g opacity=".45" fill="none" stroke="#ffffff" stroke-width="2.2">'
        '<path d="M110 74 h80"/><path d="M128 58 L136 74 L128 92"/><path d="M172 58 L164 74 L172 92"/>'
        '<path d="M136 74 L150 126 L164 74"/></g>'
    ),
    name="ARKANSAS", name_fill="#2f6b3f", name_size=21, name_ls=3,
    serial="123 ABC", serial_fill="#1f3a2a",
    slogan="The Natural State", slogan_fill="#2f6b3f", slogan_size=13, rim="#2f6b3f",
))

SPECS.append(dict(
    slug="california", state="California", design="White Standard",
    defs=linear("california-face", [("0", "#ffffff", None), ("1", "#eef1f6", None)]),
    face="url(#california-face)",
    name="California", name_fill="#d0342c", name_size=27, name_ls=0, name_y=33,
    name_family=SERIF, name_style="italic",
    serial="7ABC123", serial_fill="#123c8c", serial_size=48, serial_y=106,
    slogan="dmv.ca.gov", slogan_fill="#5c6472", slogan_size=9, slogan_ls=1.8, slogan_y=136,
    rim="#123c8c",
))

SPECS.append(dict(
    slug="colorado", state="Colorado", design="Green Mountains",
    defs=linear("colorado-face", [("0", "#ffffff", None), ("1", "#e6efe3", None)]),
    face="url(#colorado-face)",
    art=(
        ridge([(0, 150), (0, 130), (34, 106), (60, 120), (96, 92), (134, 118), (168, 98),
               (206, 122), (240, 104), (272, 124), (300, 110), (300, 150)], "#2f7a4a", ".22")
        + '<polyline points="0,130 34,106 60,120 96,92 134,118 168,98 206,122 240,104 272,124 300,110" '
          'fill="none" stroke="#2f7a4a" stroke-width="2.4" opacity=".4"/>'
    ),
    name="COLORADO", name_fill="#1e5c34", name_size=22, name_ls=3.4,
    serial="ABC-D12", serial_fill="#1e5c34", rim="#1e5c34",
))

SPECS.append(dict(
    slug="connecticut", state="Connecticut", design="Constitution State",
    defs=linear("connecticut-face", [("0", "#b9d5ee", None), ("0.58", "#ffffff", None), ("1", "#ffffff", None)]),
    face="url(#connecticut-face)",
    name="CONNECTICUT", name_fill="#123a6b", name_size=18, name_ls=2,
    serial="AB 12345", serial_fill="#123a6b", serial_size=44,
    slogan="Constitution State", slogan_fill="#123a6b", slogan_size=12, rim="#123a6b",
))

SPECS.append(dict(
    slug="delaware", state="Delaware", design="Gold Standard",
    face="#0f1c33",
    name="DELAWARE", name_fill="#e8c25a", name_size=17, name_ls=5,
    serial="123456", serial_fill="#f2d477", serial_size=50, serial_ls=5,
    slogan="THE FIRST STATE", slogan_fill="#e8c25a", slogan_size=11, slogan_ls=2.6,
    rim="#e8c25a", rim_opacity=".5",
))

SPECS.append(dict(
    slug="district-of-columbia", state="District of Columbia",
    design="Taxation Without Representation",
    defs=linear("district-of-columbia-face", [("0", "#ffffff", None), ("1", "#eff3f8", None)]),
    face="url(#district-of-columbia-face)",
    art="".join(star(cx, 45, 6.2, "#b3282d") for cx in (130, 150, 170)),
    name="WASHINGTON, D.C.", name_fill="#b3282d", name_size=15, name_ls=1.6, name_y=26,
    serial="AB 1234", serial_fill="#17325e", serial_size=44, serial_y=110,
    slogan="TAXATION WITHOUT REPRESENTATION", slogan_fill="#b3282d",
    slogan_size=9, slogan_ls=0.6, slogan_y=139, rim="#17325e",
))

SPECS.append(dict(
    slug="florida", state="Florida", design="Sunshine State",
    defs=linear("florida-face", [("0", "#ffffff", None), ("1", "#f3f7f1", None)]),
    face="url(#florida-face)",
    art=orange_fruit(150, 88, 15),
    name="FLORIDA", name_fill="#1f6b3a", name_size=22, name_ls=3.4, name_y=30,
    serial=None,
    serial_extra=[
        text(80, 104, "ABC", 40, "#123c6b", family=CONDENSED, ls=2),
        text(222, 104, "D12", 40, "#123c6b", family=CONDENSED, ls=2),
    ],
    slogan="Sunshine State", slogan_fill="#1f6b3a", slogan_size=12, rim="#1f6b3a",
))

SPECS.append(dict(
    slug="georgia", state="Georgia", design="Peach State",
    defs=linear("georgia-face", [("0", "#ffffff", None), ("1", "#f6f0e8", None)]),
    face="url(#georgia-face)",
    art=peach(150, 86, 16),
    name="Georgia", name_fill="#17427a", name_size=22, name_ls=1.4, name_y=30,
    serial=None,
    serial_extra=[
        text(76, 104, "ABC", 37, "#17427a", family=CONDENSED, ls=2),
        text(224, 104, "1234", 37, "#17427a", family=CONDENSED, ls=2),
    ],
    slogan="Peach State", slogan_fill="#17427a", slogan_size=12, rim="#17427a",
))

SPECS.append(dict(
    slug="hawaii", state="Hawaii", design="Rainbow Plate",
    defs=linear("hawaii-face", [("0", "#ffffff", None), ("1", "#edf4fa", None)]),
    face="url(#hawaii-face)",
    art='<g opacity=".55">' + "".join(
        f'<path d="M2 150 A 152 {112 - i * 6} 0 0 1 298 150" fill="none" stroke="{c}" stroke-width="6.4"/>'
        for i, c in enumerate(("#e4443a", "#ef8b2c", "#f2c93f", "#3f9b52", "#2f6fb5", "#6b4a9e"))
    ) + "</g>",
    name="HAWAII", name_fill="#17427a", name_size=22, name_ls=4.4,
    serial="ABC 123", serial_fill="#17427a", serial_size=38, serial_y=115,
    slogan="Aloha State", slogan_fill="#17427a", slogan_size=12, slogan_y=141, rim="#17427a",
))

SPECS.append(dict(
    slug="idaho", state="Idaho", design="Scenic Idaho",
    defs=linear("idaho-sky", [("0", "#b3d8f2", None), ("1", "#e9f4fb", None)]),
    face="url(#idaho-sky)",
    art=(
        ridge([(0, 150), (0, 110), (40, 82), (74, 104), (112, 74), (150, 102), (190, 72),
               (232, 100), (268, 80), (300, 104), (300, 150)], "#8ea8bf", ".8")
        + '<g fill="#ffffff" opacity=".9"><polygon points="112,74 123,84 117,85 112,81 107,85 101,84"/>'
          '<polygon points="190,72 201,82 195,83 190,79 185,83 179,82"/>'
          '<polygon points="40,82 50,92 45,93 40,89 35,93 30,92"/></g>'
        + ridge([(0, 150), (0, 128), (50, 116), (110, 130), (170, 114), (230, 128),
                 (300, 112), (300, 150)], "#3f6f45", ".95")
        + fir(268, 128, 28, 19, "#28502e") + fir(290, 130, 22, 15, "#28502e")
    ),
    name="Idaho", name_fill="#b8352c", name_size=23, name_ls=1.6, name_y=29,
    serial="1A 12345", serial_fill="#14355e", serial_size=42, serial_y=100,
    slogan="Scenic Idaho", slogan_fill="#ffffff", slogan_size=13, slogan_y=140, rim="#14355e",
))

SPECS.append(dict(
    slug="illinois", state="Illinois", design="Land of Lincoln",
    defs=linear("illinois-face", [("0", "#ffffff", None), ("1", "#e4edf7", None)]),
    face="url(#illinois-face)",
    art=lincoln(10, 40, 0.72, "#17427a", ".18") + dome(222, 44, 0.7, "#17427a", ".18"),
    name="Illinois", name_fill="#17427a", name_size=22, name_ls=1.6,
    serial="AB 12345", serial_fill="#17427a", serial_size=44,
    slogan="Land of Lincoln", slogan_fill="#17427a", slogan_size=12, rim="#17427a",
))

SPECS.append(dict(
    slug="indiana", state="Indiana", design="In God We Trust",
    defs=linear("indiana-face", [("0", "#ffffff", None), ("1", "#d9e7f6", None)]),
    face="url(#indiana-face)",
    art=torch(114, 26, 0.74, "#17427a", ".15"),
    name="INDIANA", name_fill="#17427a", name_size=21, name_ls=3.4,
    serial="123ABC", serial_fill="#17427a",
    slogan="In God We Trust", slogan_fill="#17427a", slogan_size=12, rim="#17427a",
))

SPECS.append(dict(
    slug="iowa", state="Iowa", design="Farm Heritage",
    defs=linear("iowa-face", [("0", "#ffffff", None), ("1", "#e8f1fa", None)]),
    face="url(#iowa-face)",
    art=(
        ridge([(0, 150), (0, 120), (60, 110), (130, 122), (200, 108), (260, 118),
               (300, 110), (300, 150)], "#3f6f45", ".9")
        + barn(16, 68, 0.56, "#1e3a1c", ".95")
        + fir(228, 122, 26, 18, "#22421f", ".9") + fir(250, 124, 20, 14, "#22421f", ".9")
        + '<g stroke="#ffffff" stroke-width="1.6" opacity=".28" fill="none">'
          '<path d="M0 132 h300"/><path d="M0 140 h300"/></g>'
    ),
    name="IOWA", name_fill="#17427a", name_size=22, name_ls=4,
    serial="ABC 123", serial_fill="#17427a", serial_size=44, serial_y=96, rim="#17427a",
))

SPECS.append(dict(
    slug="kansas", state="Kansas", design="Ad Astra",
    defs=linear("kansas-face", [("0", "#ffffff", None), ("1", "#f7f2e2", None)]),
    face="url(#kansas-face)",
    art=(wheat(6, 30, 0.66, "#c99a2e", ".45")
         + '<g transform="translate(300,0) scale(-1,1)">'
         + wheat(6, 30, 0.66, "#c99a2e", ".45") + "</g>"),
    name="KANSAS", name_fill="#17427a", name_size=22, name_ls=3.4,
    serial="123 ABC", serial_fill="#17427a",
    slogan="Ad Astra Per Aspera", slogan_fill="#17427a", slogan_size=11, rim="#17427a",
))

SPECS.append(dict(
    slug="kentucky", state="Kentucky", design="Unbridled Spirit",
    defs=linear("kentucky-face", [("0", "#ffffff", None), ("1", "#e5eef8", None)]),
    face="url(#kentucky-face)",
    art=horse(88, 40, 1.16, "#17427a", ".15"),
    name="Kentucky", name_fill="#17427a", name_size=22, name_ls=1.6,
    serial="ABC 123", serial_fill="#17427a",
    slogan="Unbridled Spirit", slogan_fill="#17427a", slogan_size=14,
    slogan_family=SERIF, slogan_style="italic", rim="#17427a",
))

SPECS.append(dict(
    slug="louisiana", state="Louisiana", design="Sportsman's Paradise",
    defs=linear("louisiana-face", [("0", "#ffffff", None), ("1", "#ecf4f0", None)]),
    face="url(#louisiana-face)",
    art=pelican(104, 36, 0.86, "#4a3a24", ".2"),
    name="Louisiana", name_fill="#17427a", name_size=22, name_ls=1.6,
    serial="123 ABC", serial_fill="#17427a",
    slogan="Sportsman's Paradise", slogan_fill="#17427a", slogan_size=12, rim="#17427a",
))

SPECS.append(dict(
    slug="maine", state="Maine", design="Pine Tree Plate",
    defs=linear("maine-face", [("0", "#ffffff", None), ("1", "#eaf2ea", None)]),
    face="url(#maine-face)",
    art=(fir(150, 120, 70, 50, "#2f6b3f", ".2")
         + fir(58, 122, 44, 30, "#2f6b3f", ".16")
         + fir(242, 122, 44, 30, "#2f6b3f", ".16")),
    name="MAINE", name_fill="#17427a", name_size=22, name_ls=4.4,
    serial="1234 AB", serial_fill="#17427a",
    slogan="Vacationland", slogan_fill="#2f6b3f", slogan_size=13, rim="#2f6b3f",
))

SPECS.append(dict(
    slug="maryland", state="Maryland", design="War of 1812",
    face="#ffffff",
    art=md_flag_band(22) + '<rect y="22" width="300" height="2" fill="#17427a" opacity=".3"/>',
    name="Maryland", name_fill="#17427a", name_size=21, name_ls=1.6, name_y=48,
    serial="1AB2345", serial_fill="#17427a", serial_size=44, serial_y=110,
    slogan="War of 1812", slogan_fill="#17427a", slogan_size=12, slogan_y=140, rim="#17427a",
))

SPECS.append(dict(
    slug="massachusetts", state="Massachusetts", design="Spirit of America",
    defs=linear("massachusetts-face", [("0", "#ffffff", None), ("1", "#f0f4fa", None)]),
    face="url(#massachusetts-face)",
    name="Massachusetts", name_fill="#c0272d", name_size=23, name_ls=0, name_y=32,
    name_family=SERIF, name_style="italic",
    serial="1ABC23", serial_fill="#17427a", serial_size=46, serial_y=106,
    slogan="The Spirit of America", slogan_fill="#17427a", slogan_size=12, rim="#c0272d",
))

SPECS.append(dict(
    slug="michigan", state="Michigan", design="Pure Michigan",
    defs=linear("michigan-face", [("0", "#ffffff", None), ("1", "#c9def1", None)]),
    face="url(#michigan-face)",
    art=suspension_bridge(12, 46, "2.7,0.78", "#17427a", ".18"),
    name="Michigan", name_fill="#17427a", name_size=22, name_ls=1.6,
    serial="ABC 1234", serial_fill="#17427a", serial_size=42,
    slogan="Pure Michigan", slogan_fill="#17427a", slogan_size=14,
    slogan_family=SERIF, slogan_style="italic", rim="#17427a",
))

SPECS.append(dict(
    slug="minnesota", state="Minnesota", design="10000 Lakes",
    defs=linear("minnesota-face", [("0", "#ffffff", None), ("1", "#e7f0fa", None)]),
    face="url(#minnesota-face)",
    art=waves(114, "#2f6fb5", ".3", rows=3),
    name="Minnesota", name_fill="#17427a", name_size=22, name_ls=1.6,
    serial="ABC 123", serial_fill="#17427a", serial_size=44, serial_y=96,
    slogan="10,000 Lakes", slogan_fill="#17427a", slogan_size=12, slogan_y=143, rim="#17427a",
))

SPECS.append(dict(
    slug="mississippi", state="Mississippi", design="Guitar Plate",
    defs=linear("mississippi-face", [("0", "#ffffff", None), ("1", "#f3f1eb", None)]),
    face="url(#mississippi-face)",
    art=guitar(106, 32, 0.9, "#17427a", ".15") + lighthouse(12, 40, 0.66, "#17427a", ".2"),
    name="Mississippi", name_fill="#17427a", name_size=20, name_ls=1.4,
    serial="ABC 123", serial_fill="#17427a",
    slogan="Birthplace of America's Music", slogan_fill="#17427a", slogan_size=10, rim="#17427a",
))

SPECS.append(dict(
    slug="missouri", state="Missouri", design="Bluebird Plate",
    defs=linear("missouri-face", [("0", "#ffffff", None), ("1", "#ebf2fa", None)]),
    face="url(#missouri-face)",
    art=bird(96, 32, 0.92, "#2f6fb5", ".22"),
    name="MISSOURI", name_fill="#17427a", name_size=22, name_ls=3.4,
    serial="AB1 C2D", serial_fill="#17427a",
    slogan="Show-Me State", slogan_fill="#17427a", slogan_size=12, rim="#17427a",
))


def liberty(x, y, s, fill, opacity=None):
    spikes = "".join(
        f'<polygon points="50,44 {50 + 13 * math.cos(math.radians(a)):.1f},'
        f'{44 + 13 * math.sin(math.radians(a)):.1f} '
        f'{50 + 5 * math.cos(math.radians(a + 16)):.1f},{44 + 5 * math.sin(math.radians(a + 16)):.1f}"/>'
        for a in range(-160, 1, 20)
    )
    body = (
        '<path d="M38 96 h26 l5 8 h-36 Z"/>'
        '<path d="M42 52 h14 l7 44 h-28 Z"/>'
        '<circle cx="50" cy="44" r="8"/>'
        '<rect x="62" y="22" width="6" height="32" transform="rotate(16 65 38)"/>'
        '<polygon points="72,10 78,24 64,24"/>'
        '<rect x="26" y="58" width="16" height="6" transform="rotate(-20 34 61)"/>'
        + spikes
    )
    return g(x, y, s, fill, body, opacity)


def skyline(x, y, s, fill, opacity=None):
    towers = ((0, 46), (12, 30), (24, 56), (34, 22), (46, 40), (58, 12), (70, 44), (82, 34))
    body = "".join(
        f'<rect x="{bx}" y="{100 - bh}" width="10" height="{bh}"/>' for bx, bh in towers
    ) + '<polygon points="58,12 63,0 68,12"/>'
    return g(x, y, s, fill, body, opacity)


SPECS.append(dict(
    slug="montana", state="Montana", design="Treasure State",
    defs=linear("montana-sky", [("0", "#2b6ba8", None), ("0.46", "#a9cee8", None), ("1", "#f2f8fc", None)]),
    face="url(#montana-sky)",
    art=(
        ridge([(0, 150), (0, 88), (38, 54), (72, 82), (114, 46), (156, 80), (200, 48),
               (244, 80), (276, 58), (300, 84), (300, 150)], "#2f5568", ".7")
        + '<g fill="#ffffff" opacity=".8"><polygon points="114,46 127,58 120,60 114,55 108,60 101,58"/>'
          '<polygon points="200,48 213,60 206,62 200,57 194,62 187,60"/></g>'
        + ridge([(0, 150), (0, 116), (70, 104), (150, 118), (230, 102), (300, 114), (300, 150)],
                "#3f6f45", ".85")
    ),
    name="MONTANA", name_fill="#ffffff", name_size=22, name_ls=3.4,
    serial="4-12345", serial_fill="#14355e", serial_size=42, serial_y=100,
    slogan="Treasure State", slogan_fill="#ffffff", slogan_size=13, slogan_y=140, rim="#14355e",
))

SPECS.append(dict(
    slug="nebraska", state="Nebraska", design="Scenic Heritage",
    defs=linear("nebraska-face", [("0", "#eaf3fb", None), ("1", "#ffffff", None)]),
    face="url(#nebraska-face)",
    art=(
        chimney_rock(104, 26, 0.96, "#9a7a52", ".3")
        + ridge([(0, 150), (0, 116), (80, 110), (170, 118), (250, 108), (300, 116), (300, 150)],
                "#8a9a5e", ".3")
    ),
    name="NEBRASKA", name_fill="#17427a", name_size=21, name_ls=3.4,
    serial="1-A2345", serial_fill="#17427a", serial_size=40,
    slogan="Nebraska.gov", slogan_fill="#17427a", slogan_size=11, rim="#17427a",
))

SPECS.append(dict(
    slug="nevada", state="Nevada", design="Silver State",
    defs=linear("nevada-face", [("0", "#b9bec6", None), ("1", "#edeff2", None)]),
    face="url(#nevada-face)",
    art=ridge([(0, 58), (0, 42), (36, 18), (70, 42), (110, 20), (150, 44), (196, 16),
               (240, 44), (276, 24), (300, 42), (300, 58)], "#5f6b78", ".38"),
    name="NEVADA", name_fill="#14355e", name_size=22, name_ls=3.4, name_y=32,
    serial="123 ABC", serial_fill="#14355e",
    slogan="The Silver State", slogan_fill="#14355e", slogan_size=12, rim="#14355e",
))

SPECS.append(dict(
    slug="new-hampshire", state="New Hampshire", design="Live Free or Die",
    defs=linear("new-hampshire-face", [("0", "#ffffff", None), ("1", "#e7efe6", None)]),
    face="url(#new-hampshire-face)",
    art=ridge([(0, 150), (0, 112), (54, 84), (100, 108), (150, 80), (208, 106),
               (256, 86), (300, 110), (300, 150)], "#2f6b3f", ".16"),
    name="NEW HAMPSHIRE", name_fill="#2f6b3f", name_size=17, name_ls=2.4,
    serial="123 4567", serial_fill="#2f6b3f", serial_size=44,
    slogan="Live Free or Die", slogan_fill="#2f6b3f", slogan_size=13, rim="#2f6b3f",
))

SPECS.append(dict(
    slug="new-jersey", state="New Jersey", design="Garden State",
    defs=linear("new-jersey-face", [("0", "#f4e4ac", None), ("1", "#e6d18c", None)]),
    face="url(#new-jersey-face)",
    name="New Jersey", name_fill="#1f2328", name_size=21, name_ls=1.6,
    serial="A12-BCD", serial_fill="#1f2328", serial_size=44,
    slogan="Garden State", slogan_fill="#1f2328", slogan_size=13, rim="#7a6428",
))

SPECS.append(dict(
    slug="new-mexico", state="New Mexico", design="Chile Plate",
    defs=linear("new-mexico-face", [("0", "#3aacb0", None), ("1", "#1d8a92", None)]),
    face="url(#new-mexico-face)",
    art=zia(150, 50, 9, "#f2d477", arm=11),
    name="NEW MEXICO USA", name_fill="#f7e9a8", name_size=15, name_ls=2, name_y=26,
    serial="123-ABC", serial_fill="#fbf3cf", serial_size=42, serial_y=114,
    slogan="Land of Enchantment", slogan_fill="#f7e9a8", slogan_size=11, slogan_y=140,
    rim="#f2d477", rim_opacity=".45",
))

SPECS.append(dict(
    slug="new-york", state="New York", design="Excelsior",
    face="#ffffff",
    art=(
        '<rect width="300" height="32" fill="#17427a"/>'
        '<rect y="110" width="300" height="40" fill="#d7e6f4"/>'
        + liberty(12, 78, 0.42, "#17427a", ".62")
        + skyline(96, 82, 0.4, "#17427a", ".5")
        + waves(126, "#2f6fb5", ".45", rows=2, span=(214, 296), amp=4, step=20)
        + '<rect y="110" width="300" height="2" fill="#c9a227"/>'
    ),
    name="NEW YORK", name_fill="#ffffff", name_size=19, name_ls=3, name_y=23,
    serial="ABC-1234", serial_fill="#17427a", serial_size=42, serial_y=93,
    slogan="EXCELSIOR", slogan_fill="#8a6d1f", slogan_size=11, slogan_ls=2.4, slogan_y=141,
    rim="#17427a",
))

SPECS.append(dict(
    slug="north-carolina", state="North Carolina", design="First in Flight",
    defs=linear("north-carolina-face", [("0", "#ffffff", None), ("1", "#eaf1f9", None)]),
    face="url(#north-carolina-face)",
    art=(biplane(198, -4, 0.92, "#17427a", ".3")
         + '<rect y="120" width="300" height="3" fill="#c8102e" opacity=".65"/>'),
    name="First in Flight", name_fill="#c8102e", name_size=17, name_ls=1.2, name_y=26,
    serial="ABC-1234", serial_fill="#17427a", serial_size=42, serial_y=104,
    slogan="North Carolina", slogan_fill="#17427a", slogan_size=14, slogan_y=140, rim="#17427a",
))

SPECS.append(dict(
    slug="north-dakota", state="North Dakota", design="Legendary",
    defs=linear("north-dakota-sky", [("0", "#2c5f9e", None), ("0.44", "#cfe0ef", None), ("1", "#e8b95a", None)]),
    face="url(#north-dakota-sky)",
    art=(
        butte(4, 74, "1.1,0.72", "#7a5a3c", ".55")
        + butte(196, 76, "1.05,0.68", "#7a5a3c", ".45")
        + ridge([(0, 150), (0, 126), (70, 118), (150, 128), (230, 116), (300, 126), (300, 150)],
                "#6b4a2e", ".55")
    ),
    name="NORTH DAKOTA", name_fill="#ffffff", name_size=18, name_ls=2.6,
    serial="123 ABC", serial_fill="#14355e", serial_size=42, serial_y=100,
    slogan="Legendary", slogan_fill="#ffffff", slogan_size=15, slogan_y=140,
    slogan_family=SERIF, slogan_style="italic", rim="#14355e",
))

SPECS.append(dict(
    slug="ohio", state="Ohio", design="Birthplace of Aviation",
    defs=linear("ohio-face", [("0", "#ffffff", None), ("1", "#f2f5f9", None)]),
    face="url(#ohio-face)",
    art=(
        '<rect x="4" y="4" width="292" height="142" rx="12" fill="none" stroke="#c8102e" stroke-width="7"/>'
        + '<circle cx="58" cy="60" r="19" fill="#f2c33c" opacity=".45"/>'
        + biplane(186, 8, 0.92, "#17427a", ".28")
    ),
    name="Ohio", name_fill="#17427a", name_size=22, name_ls=1.6, name_y=30,
    serial="ABC 1234", serial_fill="#17427a", serial_size=40, serial_y=104,
    slogan="Birthplace of Aviation", slogan_fill="#c8102e", slogan_size=11, slogan_y=136,
    rim="#c8102e", rim_opacity="0",
))

SPECS.append(dict(
    slug="oklahoma", state="Oklahoma", design="Native America",
    defs=linear("oklahoma-face", [("0", "#ffffff", None), ("1", "#f1efe8", None)]),
    face="url(#oklahoma-face)",
    art=bird(94, 22, 0.9, "#8a6a45", ".26", tail="fork"),
    name="Oklahoma", name_fill="#17427a", name_size=22, name_ls=1.6,
    serial="ABC 123", serial_fill="#17427a",
    slogan="Native America", slogan_fill="#17427a", slogan_size=12, rim="#17427a",
))

SPECS.append(dict(
    slug="oregon", state="Oregon", design="Pacific Wonderland",
    defs=linear("oregon-sky", [("0", "#d5e8f4", None), ("1", "#ffffff", None)]),
    face="url(#oregon-sky)",
    art=(
        ridge([(0, 150), (0, 96), (48, 62), (92, 90), (150, 54), (208, 90), (256, 64),
               (300, 94), (300, 150)], "#8fa6b8", ".55")
        + ridge([(0, 150), (0, 120), (70, 112), (150, 122), (230, 110), (300, 120), (300, 150)],
                "#3f6f45", ".55")
        + fir(150, 124, 66, 46, "#2f6b3f", ".7")
        + fir(52, 126, 40, 28, "#2f6b3f", ".55") + fir(250, 126, 40, 28, "#2f6b3f", ".55")
    ),
    name="Oregon", name_fill="#17427a", name_size=22, name_ls=1.6,
    serial="123 ABC", serial_fill="#14355e", serial_size=42, serial_y=100,
    slogan="Pacific Wonderland", slogan_fill="#1e5c34", slogan_size=12, slogan_y=141, rim="#1e5c34",
))

SPECS.append(dict(
    slug="pennsylvania", state="Pennsylvania", design="Keystone State",
    face="#ffffff",
    art=(
        '<rect width="300" height="27" fill="#17427a"/>'
        '<rect y="123" width="300" height="27" fill="#f2c33c"/>'
        '<path d="M126 46 h48 l16 56 h-80 Z" fill="#17427a" opacity=".11"/>'
    ),
    name="Pennsylvania", name_fill="#ffffff", name_size=17, name_ls=1.6, name_y=20,
    serial="ABC-1234", serial_fill="#17427a", serial_size=44, serial_y=100,
    slogan="visitPA.com", slogan_fill="#1f2328", slogan_size=12, slogan_y=142, rim="#17427a",
))

SPECS.append(dict(
    slug="rhode-island", state="Rhode Island", design="Ocean State",
    defs=linear("rhode-island-face", [("0", "#ffffff", None), ("1", "#e7f0f9", None)]),
    face="url(#rhode-island-face)",
    art=waves(112, "#2f6fb5", ".32", rows=3) + anchor(16, 48, 0.46, "#17427a", ".2"),
    name="Rhode Island", name_fill="#17427a", name_size=21, name_ls=1.4,
    serial="AB-123", serial_fill="#17427a", serial_size=44, serial_y=96,
    slogan="Ocean State", slogan_fill="#17427a", slogan_size=12, slogan_y=143, rim="#17427a",
))

SPECS.append(dict(
    slug="south-carolina", state="South Carolina", design="Palmetto State",
    defs=linear("south-carolina-face", [("0", "#ffffff", None), ("1", "#e4ecf7", None)]),
    face="url(#south-carolina-face)",
    art=(palmetto(108, 26, 0.94, "#17427a", ".17")
         + '<path fill-rule="evenodd" fill="#17427a" opacity=".3" '
           'd="M38 49 m-17 0 a17 17 0 1 0 34 0 a17 17 0 1 0-34 0 '
           'M48 49 m-15 0 a15 15 0 1 0 30 0 a15 15 0 1 0-30 0 Z"/>'),
    name="South Carolina", name_fill="#17427a", name_size=20, name_ls=1.4,
    serial="ABC 123", serial_fill="#17427a",
    slogan="Smiling Faces. Beautiful Places.", slogan_fill="#17427a", slogan_size=10, rim="#17427a",
))

SPECS.append(dict(
    slug="south-dakota", state="South Dakota", design="Great Faces Great Places",
    defs=linear("south-dakota-sky", [("0", "#cfe4f4", None), ("1", "#ffffff", None)]),
    face="url(#south-dakota-sky)",
    art=rushmore(84, 32, "1.32,1.1", "#6f6659", ".42"),
    name="South Dakota", name_fill="#17427a", name_size=21, name_ls=1.4,
    serial="1AB 234", serial_fill="#17427a",
    slogan="Great Faces. Great Places.", slogan_fill="#17427a", slogan_size=11, rim="#17427a",
))

SPECS.append(dict(
    slug="tennessee", state="Tennessee", design="Blue Tennessee",
    face="#1d4e8f",
    art=(
        '<circle cx="42" cy="46" r="17" fill="none" stroke="#ffffff" stroke-width="3" opacity=".3"/>'
        + star(42, 38, 7, "#ffffff", opacity=".3")
        + star(34, 52, 7, "#ffffff", opacity=".3")
        + star(50, 52, 7, "#ffffff", opacity=".3")
    ),
    name="Tennessee", name_fill="#ffffff", name_size=22, name_ls=1.6,
    serial="A12-34B", serial_fill="#ffffff", serial_size=46,
    slogan="In God We Trust", slogan_fill="#cfe0f2", slogan_size=12,
    rim="#ffffff", rim_opacity=".45",
))

SPECS.append(dict(
    slug="texas", state="Texas", design="Classic Texas",
    defs=linear("texas-face", [("0", "#ffffff", None), ("1", "#f0f2f5", None)]),
    face="url(#texas-face)",
    art=(
        star(150, 84, 36, "#1f2328", opacity=".08")
        + star(74, 22, 9, "#17427a", opacity=".85")
        + '<rect y="120" width="300" height="3" fill="#c8102e" opacity=".75"/>'
        '<rect y="123" width="300" height="3" fill="#17427a" opacity=".75"/>'
    ),
    name="TEXAS", name_fill="#1f2328", name_size=22, name_ls=4.4,
    serial="ABC-1234", serial_fill="#1f2328", serial_size=42,
    slogan="The Lone Star State", slogan_fill="#1f2328", slogan_size=12, slogan_y=141,
    rim="#1f2328",
))

SPECS.append(dict(
    slug="utah", state="Utah", design="Life Elevated",
    defs=linear("utah-sky", [("0", "#f7e4cb", None), ("1", "#ffffff", None)]),
    face="url(#utah-sky)",
    art=(delicate_arch(16, 30, 0.94, "#b5562c", ".3")
         + '<rect y="118" width="300" height="4" fill="#b5562c" opacity=".22"/>'),
    name="Utah", name_fill="#14355e", name_size=22, name_ls=2,
    serial="A12 3BC", serial_fill="#14355e",
    slogan="Life Elevated", slogan_fill="#b5562c", slogan_size=13, rim="#b5562c",
))

SPECS.append(dict(
    slug="vermont", state="Vermont", design="Green Mountain State",
    defs=linear("vermont-face", [("0", "#ffffff", None), ("1", "#e3ede1", None)]),
    face="url(#vermont-face)",
    art=(ridge([(0, 150), (0, 106), (52, 74), (104, 102), (150, 68), (200, 100),
                (252, 78), (300, 104), (300, 150)], "#2f6b3f", ".18")
         + fir(40, 128, 34, 24, "#2f6b3f", ".28") + fir(262, 128, 34, 24, "#2f6b3f", ".28")),
    name="Vermont", name_fill="#1e5c34", name_size=22, name_ls=1.6,
    serial="ABC 123", serial_fill="#1e5c34",
    slogan="Green Mountain State", slogan_fill="#1e5c34", slogan_size=12, rim="#1e5c34",
))

SPECS.append(dict(
    slug="virginia", state="Virginia", design="Virginia is for Lovers",
    defs=linear("virginia-face", [("0", "#ffffff", None), ("1", "#e8eef8", None)]),
    face="url(#virginia-face)",
    art='<path d="M150 110 C118 84 120 60 137 56 C145 54 150 60 150 65 C150 60 155 54 163 56 '
        'C180 60 182 84 150 110 Z" fill="#c8102e" opacity=".13"/>',
    name="Virginia", name_fill="#17427a", name_size=22, name_ls=1.6,
    serial="ABC-1234", serial_fill="#17427a", serial_size=42,
    slogan="Virginia is for Lovers", slogan_fill="#17427a", slogan_size=12, rim="#17427a",
))

SPECS.append(dict(
    slug="washington", state="Washington", design="Mount Rainier",
    defs=linear("washington-sky", [("0", "#d5e8f4", None), ("1", "#ffffff", None)]),
    face="url(#washington-sky)",
    art=(
        ridge([(0, 150), (0, 104), (56, 80), (104, 96), (150, 42), (200, 94), (250, 78),
               (300, 102), (300, 150)], "#93aec4", ".7")
        + '<polygon points="150,42 172,64 162,66 150,58 138,66 128,64" fill="#ffffff" opacity=".95"/>'
        + ridge([(0, 150), (0, 122), (70, 114), (150, 124), (230, 112), (300, 122), (300, 150)],
                "#2f6b3f", ".5")
        + fir(34, 128, 42, 28, "#28502e", ".8") + fir(264, 128, 42, 28, "#28502e", ".8")
        + fir(60, 130, 30, 20, "#28502e", ".7") + fir(240, 130, 30, 20, "#28502e", ".7")
    ),
    name="Washington", name_fill="#1e5c34", name_size=22, name_ls=1.6,
    serial="ABC1234", serial_fill="#14355e", serial_size=42, serial_y=104, rim="#1e5c34",
))

SPECS.append(dict(
    slug="west-virginia", state="West Virginia", design="Wild and Wonderful",
    defs=linear("west-virginia-face", [("0", "#ffffff", None), ("1", "#e4ecf7", None)]),
    face="url(#west-virginia-face)",
    art=arch_bridge(16, 40, "2.7,1.06", "#17427a", ".22"),
    name="West Virginia", name_fill="#17427a", name_size=20, name_ls=1.4,
    serial="1AB 234", serial_fill="#17427a",
    slogan="Wild, Wonderful", slogan_fill="#17427a", slogan_size=13, rim="#17427a",
))

SPECS.append(dict(
    slug="wisconsin", state="Wisconsin", design="America's Dairyland",
    defs=linear("wisconsin-face", [("0", "#ffffff", None), ("1", "#ecf2f8", None)]),
    face="url(#wisconsin-face)",
    art=(
        ridge([(0, 150), (0, 118), (70, 110), (150, 120), (230, 108), (300, 118), (300, 150)],
              "#3f6f45", ".9")
        + barn(96, 62, 0.62, "#1e3a1c", ".95")
        + '<g stroke="#ffffff" stroke-width="1.6" opacity=".26" fill="none">'
          '<path d="M0 132 h300"/><path d="M0 140 h300"/></g>'
    ),
    name="Wisconsin", name_fill="#17427a", name_size=22, name_ls=1.6,
    serial="ABC-1234", serial_fill="#17427a", serial_size=42, serial_y=96,
    slogan="America's Dairyland", slogan_fill="#ffffff", slogan_size=12, slogan_y=143, rim="#17427a",
))

SPECS.append(dict(
    slug="wyoming", state="Wyoming", design="State Flag Design (2025)",
    defs=linear("wyoming-face", [("0", "#ffffff", None), ("1", "#eef1f6", None)]),
    face="url(#wyoming-face)",
    art=(
        horse(88, 30, 1.14, "#17427a", ".16", rear=True)
        + '<rect y="118" width="300" height="4" fill="#c8102e" opacity=".8"/>'
          '<rect y="122" width="300" height="4" fill="#17427a" opacity=".8"/>'
    ),
    name="WYOMING", name_fill="#17427a", name_size=21, name_ls=3.4,
    serial="22 1234", serial_fill="#17427a",
    slogan="Forever West", slogan_fill="#17427a", slogan_size=13, slogan_y=142, rim="#17427a",
))


# -------------------------------------------------------------------- output

SQL_HEADER = """-- Plate artwork for every US state plus the District of Columbia.
--
-- GENERATED by scripts/build_plate_svgs.py -- edit the generator, not this file.
--
-- Matches on `state`, so it is safe to re-run: every execution overwrites
-- svg_code with the current artwork and touches nothing else.
--
--     psql -d platefind_db -f migrations/002_plate_svgs.sql
--
-- Each SVG is dollar-quoted because the markup contains single quotes.

BEGIN;

WITH designs(state, svg) AS (VALUES
"""

SQL_FOOTER = """)
UPDATE plates AS p
   SET svg_code = d.svg
  FROM designs AS d
 WHERE p.state = d.state
   AND p.country = 'United States';

COMMIT;

-- Anything listed here did not get artwork: the plates row is missing, its
-- country is not 'United States', or its state is spelled differently.
SELECT state, country
  FROM plates
 WHERE svg_code IS NULL OR svg_code = ''
 ORDER BY state;
"""


def write_sql(built):
    rows = []
    for i, (spec, svg) in enumerate(built):
        assert "$svg$" not in svg, f"{spec['slug']}: markup collides with the dollar quote"
        state = spec["state"].replace("'", "''")
        cast = "::text" if i == 0 else ""
        comma = "," if i < len(built) - 1 else ""
        rows.append(f"  ('{state}'{cast}, $svg${svg}$svg${cast}){comma}")
    os.makedirs(os.path.dirname(SQL_PATH), exist_ok=True)
    with open(SQL_PATH, "w") as fh:
        fh.write(SQL_HEADER + "\n".join(rows) + "\n" + SQL_FOOTER)


PREVIEW = """<!doctype html>
<meta charset="utf-8"><title>PlateFind artwork</title>
<style>
 body{{margin:0;padding:28px;background:#11151c;color:#e7ecf3;
      font:15px/1.4 -apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}}
 h1{{font-size:19px;margin:0 0 4px}} p{{margin:0 0 24px;color:#93a0b2;font-size:13.5px}}
 .grid{{display:grid;gap:20px;grid-template-columns:repeat(auto-fill,minmax(230px,1fr))}}
 figure{{margin:0}} .p{{aspect-ratio:2/1;border-radius:10px;overflow:hidden}}
 figcaption{{margin-top:7px;font-size:12.5px;color:#93a0b2}}
 b{{display:block;color:#e7ecf3;font-size:13.5px;font-weight:600}}
</style>
<h1>PlateFind plate artwork</h1>
<p>{n} designs &middot; generated by scripts/build_plate_svgs.py</p>
<div class="grid">{cards}</div>
"""


def write_preview(built):
    cards = "".join(
        f'<figure><div class="p">{svg}</div>'
        f'<figcaption><b>{esc(s["state"])}</b>{esc(s["design"])}</figcaption></figure>'
        for s, svg in built
    )
    with open(os.path.join(SVG_DIR, "preview.html"), "w") as fh:
        fh.write(PREVIEW.format(n=len(built), cards=cards))


def main():
    os.makedirs(SVG_DIR, exist_ok=True)
    seen = set()
    built = []
    for spec in SPECS:
        assert spec["state"] not in seen, f"duplicate state {spec['state']}"
        seen.add(spec["state"])
        svg = build(spec)
        built.append((spec, svg))
        with open(os.path.join(SVG_DIR, f"{spec['slug']}.svg"), "w") as fh:
            fh.write(svg + "\n")

    # the CSV is the roster; drifting from it is the bug worth catching
    csv_path = os.path.join(ROOT, "us-license-plates-imp.csv")
    if os.path.exists(csv_path):
        import csv
        with open(csv_path, newline="") as fh:
            wanted = {row["state"] for row in csv.DictReader(fh)}
        missing = sorted(wanted - seen)
        extra = sorted(seen - wanted)
        if missing:
            raise SystemExit(f"no artwork for: {', '.join(missing)}")
        if extra:
            raise SystemExit(f"artwork for states not in the CSV: {', '.join(extra)}")

    write_sql(built)
    write_preview(built)
    sizes = sorted(len(svg) for _, svg in built)
    print(f"{len(built)} plates -> {SVG_DIR}")
    print(f"  svg bytes: min {sizes[0]}, median {sizes[len(sizes) // 2]}, max {sizes[-1]}, "
          f"total {sum(sizes) / 1024:.1f} KiB")
    print(f"  sql: {os.path.relpath(SQL_PATH, ROOT)}")
    print(f"  preview: {os.path.relpath(os.path.join(SVG_DIR, 'preview.html'), ROOT)}")


if __name__ == "__main__":
    main()
