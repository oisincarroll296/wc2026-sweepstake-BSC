"""
WC 2026 Sweepstake – promotional graphic generator.
Run from:  C:\World Cup
Output:    promo/sweepstake_promo.jpg
"""
import os, sys
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch
import numpy as np

# ── Palette ────────────────────────────────────────────────────────────────────
BG      = '#0D1B2A'
PANEL   = '#162032'
BORDER  = '#2D4460'
GOLD    = '#D4A017'
GOLD_DK = '#A07810'
WHITE   = '#FFFFFF'
MUTED   = '#CBD5E1'
BLUE    = '#1A6FC4'
GREEN   = '#16A34A'
AMBER   = '#D97706'
RED     = '#DC2626'
PURPLE  = '#7C3AED'
TEAL    = '#0891B2'
DIM     = '#1E293B'
ACCENT  = '#1E3A5F'

PAD = 0.07

# ── Figure ─────────────────────────────────────────────────────────────────────
W, H = 14, 22
fig = plt.figure(figsize=(W, H), facecolor=BG, dpi=150)
ax  = fig.add_axes([0, 0, 1, 1])
ax.set_xlim(0, W)
ax.set_ylim(0, H)
ax.axis('off')
ax.set_facecolor(BG)

# ── Helpers ────────────────────────────────────────────────────────────────────
def box(x, y, w, h, fc=PANEL, ec=BORDER, lw=0.8, z=2):
    p = FancyBboxPatch(
        (x + PAD, y + PAD), w - 2 * PAD, h - 2 * PAD,
        boxstyle=f'round,pad={PAD}',
        facecolor=fc, edgecolor=ec, linewidth=lw, zorder=z,
    )
    ax.add_patch(p)

def t(x, y, s, sz=12, c=WHITE, bold=False, italic=False, ha='left', va='center', z=4):
    ax.text(x, y, s, fontsize=sz, color=c,
            fontweight='bold' if bold else 'normal',
            fontstyle='italic' if italic else 'normal',
            ha=ha, va=va, zorder=z, clip_on=False)

def section_bar(x, y, w, label, fc=BLUE):
    box(x, y, w, 0.72, fc=fc, ec='none', z=3)
    t(x + w / 2, y + 0.36, label, sz=14, bold=True, ha='center', z=4)

def divider(y, x0, x1, color=BORDER, lw=0.8):
    ax.plot([x0, x1], [y, y], color=color, linewidth=lw, zorder=3)

# ═══════════════════════════════════════════════════════════════════════════════
# HEADER
# ═══════════════════════════════════════════════════════════════════════════════
box(0, 19.8, W, 2.2, fc=GOLD, ec='none', z=2)
for xi in np.arange(-1, W + 2, 0.9):
    ax.fill_betweenx([19.8, 22.0], [xi, xi + 1.4], [xi + 0.15, xi + 1.55],
                     color=GOLD_DK, alpha=0.35, zorder=3)

# "STARTS" callout — top right
box(10.3, 20.55, 3.5, 1.25, fc=BG, ec=GOLD_DK, lw=2.0, z=5)
t(12.05, 21.25, 'STARTS',        sz=9.5, c=MUTED, bold=True, ha='center', z=6)
t(12.05, 20.88, 'JUNE 11, 2026', sz=13,  c=GOLD,  bold=True, ha='center', z=6)

# Title
t(5.1, 21.42, 'WORLD CUP 2026', sz=36, c=BG, bold=True, ha='center', z=6)
t(5.1, 20.78, 'SWEEPSTAKE',     sz=30, c=BG, bold=True, ha='center', z=6)

# Tagline strip
box(0, 19.2, W, 0.62, fc=DIM, ec='none', z=2)
t(W / 2, 19.52,
  '13 Players  ·  48 Teams  ·  4 Tiers  ·  1st 50%  ·  2nd 30%  ·  3rd 20%',
  sz=12.5, c=MUTED, ha='center', z=3)

# ═══════════════════════════════════════════════════════════════════════════════
# LEFT PANEL — WHAT TO BUY
# ═══════════════════════════════════════════════════════════════════════════════
LX, LY, LW, LH = 0.3, 10.05, 6.65, 9.0
box(LX, LY, LW, LH)
section_bar(LX, LY + LH - 0.80, LW, 'WHAT TO BUY', fc=BLUE)

packages = [
    ('Buy In',          '€5', GOLD,   'Your entry  ·  8 teams across 4 tiers',      True),
    ('Prediction Pack', '€5', GREEN,  'WC Winner  ·  Golden Boot  ·  Dark Horse',    False),
    ('Mulligan',        '€3', AMBER,  'Full redraw of all 8 teams  ·  buy multiple', False),
    ('9th Team',        '€3', PURPLE, 'Extra team for the knockout stage',            False),
    ('Resurrection',    '€5', RED,    'Replace one eliminated team',                  False),
    ('Insurance',       '€2', TEAL,   '+25 pts per Tier 1 team out before R16',      False),
]

ROW = 1.27
for i, (name, price, colour, desc, highlight) in enumerate(packages):
    ry = LY + LH - 1.38 - i * ROW
    if highlight:
        box(LX + 0.1, ry - 0.44, LW - 0.2, 0.96, fc=ACCENT, ec=GOLD, lw=1.2, z=3)
    # price pill
    box(LX + 0.25, ry - 0.37, 0.98, 0.80, fc=colour, ec='none', z=4)
    t(LX + 0.74, ry + 0.03, price, sz=17, bold=True, ha='center', z=5)
    # label + description
    t(LX + 1.45, ry + 0.22, name, sz=13.5, bold=True,           z=4)
    t(LX + 1.45, ry - 0.13, desc, sz=11,   c=MUTED,             z=4)
    if i < len(packages) - 1:
        divider(ry - 0.48, LX + 0.15, LX + LW - 0.15)

# ═══════════════════════════════════════════════════════════════════════════════
# RIGHT PANEL — WHAT TO SEND
# ═══════════════════════════════════════════════════════════════════════════════
RX, RY, RW, RH = 7.05, 10.05, 6.65, 9.0
box(RX, RY, RW, RH)
section_bar(RX, RY + RH - 0.80, RW, 'WHAT TO SEND', fc=GREEN)

groups = [
    ('Your name',
     [('Your full name  (first + last)',  WHITE, False)]),
    ('Payment ref on Revolut Shared Pocket',
     [('"NAME  -  BUY IN"',               GOLD,  True),
      ('"NAME  -  BUY IN, PRED PACK"',    GOLD,  True)]),
    ('Captain picks — send to me directly',
     [('Pre-tournament captain',           MUTED, False),
      ('Knockout stage captain',           MUTED, False)]),
    ('Predictions — Pred Pack buyers only',
     [('World Cup Winner',                 MUTED, False),
      ('Golden Boot winner',               MUTED, False),
      ('Dark Horse  (Tier 3 or 4 team)',   MUTED, False)]),
]

gy = RY + RH - 1.32
for gi, (header, bullets) in enumerate(groups):
    t(RX + 0.40, gy, header, sz=12, bold=True, c=WHITE, z=4)
    gy -= 0.47
    for text, clr, itl in bullets:
        t(RX + 0.85, gy, f'→  {text}', sz=11, c=clr, italic=itl, z=4)
        gy -= 0.44
    if gi < len(groups) - 1:
        divider(gy + 0.10, RX + 0.2, RX + RW - 0.2)
        gy -= 0.18

# Contact box
box(RX + 0.2, RY + 0.2, RW - 0.4, 1.22, fc=DIM, ec=GOLD, lw=1.8, z=4)
t(RX + RW / 2, RY + 0.94, 'Send your details to:',     sz=11,  c=MUTED, ha='center', z=5)
t(RX + RW / 2, RY + 0.54, 'oisincarroll296@gmail.com', sz=12.5, c=GOLD, bold=True, ha='center', z=5)

# ═══════════════════════════════════════════════════════════════════════════════
# TIMELINE
# ═══════════════════════════════════════════════════════════════════════════════
TX, TY, TW, TH = 0.3, 1.2, W - 0.6, 8.65
box(TX, TY, TW, TH)
section_bar(TX, TY + TH - 0.80, TW, 'KEY DATES & TIMELINE', fc=PURPLE)

events = [
    ('NOW',     'Sign up  ·  Pay your Buy In',                        GOLD),
    ('11 Jun',  'Tournament begins  —  48 teams, 6 weeks',            BLUE),
    ('19 Jun',  'All deadlines  —  Buy In, Mulligan, Predictions',    AMBER),
    ('28 Jun',  'Knockouts begin  —  Ninth Team & KO captain draws',  GREEN),
    ('29 Jun',  'Resurrection window closes',                         PURPLE),
    ('19 Jul',  'THE FINAL!',                                         GOLD),
]

DX   = TX + 2.6
TOP  = TY + TH - 1.38
BOT  = TY + 0.90
STEP = (TOP - BOT) / (len(events) - 1)

ax.plot([DX, DX], [BOT, TOP], color=BORDER, linewidth=3.0,
        solid_capstyle='round', zorder=3)

for i, (date, desc, colour) in enumerate(events):
    ey = TOP - i * STEP
    ax.plot(DX, ey, 'o', ms=22, color=colour, zorder=5)
    ax.plot(DX, ey, 'o', ms=10, color=BG,     zorder=6)
    t(DX - 0.32, ey, date, sz=13.5, c=colour, bold=True, ha='right', z=5)
    t(DX + 0.45, ey, desc, sz=13.5, c=WHITE,             ha='left',  z=5)

# ═══════════════════════════════════════════════════════════════════════════════
# FOOTER
# ═══════════════════════════════════════════════════════════════════════════════
box(0.3, 0.2, W - 0.6, 0.88, fc=DIM, ec=GOLD, lw=1.8, z=2)
t(W / 2, 0.68, 'Live scores, portfolios & full rules:', sz=11,  c=MUTED, ha='center', z=3)
t(W / 2, 0.37, 'https://fellas-wc2026-sweepstake.streamlit.app/', sz=13, c=GOLD, bold=True, ha='center', z=3)

# ── Save ───────────────────────────────────────────────────────────────────────
os.makedirs(os.path.dirname(os.path.abspath(__file__)), exist_ok=True)
out = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'sweepstake_promo.jpg')
plt.savefig(out, dpi=150, facecolor=BG)
print(f'Saved: {out}')
plt.close()
