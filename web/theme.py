"""Colours, number formats and the Plotly chart style (clean, airy, rounded).

Every chart on the site goes through `style(fig)`, so changing a value here restyles all of them.
"""
import plotly.graph_objects as go
import plotly.io as pio

# Palette
INK = "#191C1F"        # main text
INK_2 = "#505A63"      # secondary text
MUTED = "#8B959E"      # axis labels, captions
GRID = "#EEF0F3"       # gridlines
BASELINE = "#D5DAE0"   # zero lines
BLUE = "#4B80DF"       # you / portfolio (calm, not saturated: the charts should not shout)
CORAL = "#D9826A"      # benchmark
GREEN = "#2FA383"      # gains, direct stocks
RED = "#D9686C"        # losses, underweights
VIOLET = "#7A6AD0"
SEQUENTIAL = ["#EEF3FC", "#D3E0F6", "#AFC6EE", "#86A8E4", "#5F88D6", "#456CB8", "#33538F"]

BUCKET_COLORS = {"Core index": BLUE, "US": "#3F5E9E", "Europe": "#7FAFD6", "Japan & Pacific": "#C9787A",
                 "Emerging markets": "#4FA9B8", "Small-cap": "#B3A6E6", "Small-cap value": VIOLET,
                 "Value": "#D1A93C", "Momentum": "#C2639A", "Quality": "#3E9483", "Minimum volatility": "#9AAAB8",
                 "Multi-factor": "#C98A4E", "Dividend": "#D6B65C", "ESG": "#7EA868", "Sector & theme": "#9C6A8A",
                 "Real estate": "#8D6E63", "Bonds": "#5C6F80", "Money market": "#A9B4C2",
                 "Gold & commodities": "#C9A227", "Direct stocks": GREEN}  # same names as etfs.BUCKETS
REGION_COLORS = {"Americas": BLUE, "Europe": GREEN, "Middle East & Africa": "#D1A93C",
                 "Asia-Pacific": VIOLET, "Unclassified": MUTED}
REST_COLOR = "#E3E7EC"

FONT = "Inter, -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif"


# ---------------------------------------------------------------------------
# Number formats used across the site
# ---------------------------------------------------------------------------
def eur(x, sign=False, decimals=0):
    """€1,234 / +€1,234 / −€1,234."""
    if x is None:
        return "—"
    s = "−" if x < 0 else "+" if sign else ""
    return f"{s}€{abs(x):,.{decimals}f}"


def pct(x, decimals=1, sign=False):
    """12.3% / +12.3% (x is already in percent)."""
    if x is None or x != x:
        return "—"
    return f"{x:+.{decimals}f}%" if sign else f"{x:.{decimals}f}%"


def frac(x, decimals=1, sign=False):
    """0.123 -> 12.3%."""
    return pct(None if x is None else 100 * x, decimals, sign)


def tone(x):
    """'pos' / 'neg' / None: the frontend colours text green / red."""
    if x is None or x != x or x == 0:
        return None
    return "pos" if x > 0 else "neg"


def hex_color(c):
    """matplotlib-style (r, g, b) floats -> '#rrggbb'; strings pass through."""
    if isinstance(c, str):
        return c
    return "#" + "".join(f"{round(255 * max(0, min(1, v))):02x}" for v in c[:3])


def shades(base, n, spread=0.55):
    """n tints of one colour, the full colour first (lighter = later)."""
    base = base.lstrip("#")
    rgb = [int(base[i:i + 2], 16) / 255 for i in (0, 2, 4)]
    if n <= 1:
        return ["#" + base]
    return [hex_color([v + (1 - v) * spread * i / (n - 1) for v in rgb]) for i in range(n)]


def ink_on(color):
    """White or dark text, whichever reads better on a fill of this colour."""
    h = hex_color(color).lstrip("#")
    r, g, b = (int(h[i:i + 2], 16) / 255 for i in (0, 2, 4))
    lin = lambda c: c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
    lum = 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    return "#FFFFFF" if lum < 0.3 else INK


# ---------------------------------------------------------------------------
# Plotly template
# ---------------------------------------------------------------------------
_axis = dict(showline=False, zeroline=False, ticks="", tickfont=dict(color=MUTED, size=11),
             title=dict(font=dict(color=MUTED, size=11)), automargin=True)

pio.templates["my_money"] = go.layout.Template(layout=dict(
    font=dict(family=FONT, color=INK, size=12),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    colorway=[BLUE, CORAL, GREEN, VIOLET, "#D1A93C", "#4FA9B8", "#C2639A", MUTED],
    xaxis=dict(**_axis, showgrid=False),
    yaxis=dict(**_axis, showgrid=True, gridcolor=GRID, gridwidth=1),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                font=dict(color=INK_2, size=12), bgcolor="rgba(0,0,0,0)"),
    # No bgcolor: Plotly then colours each label like its point, and static/app.js reads that colour for the dark
    # details card it shows instead (Plotly's own label is hidden by static/style.css)
    hoverlabel=dict(font=dict(family=FONT, size=13), align="left", namelength=-1),
    margin=dict(l=8, r=8, t=36, b=8),
    bargap=0.3,
    hovermode="x unified",
))
pio.templates.default = "my_money"


def style(fig, height=380, legend=True, hover="x unified", **layout):
    """Apply the site look to a figure. Extra keyword arguments go straight to fig.update_layout."""
    fig.update_layout(template="my_money", height=height, showlegend=legend, hovermode=hover, **layout)
    return fig
