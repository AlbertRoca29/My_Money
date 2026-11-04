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
BLUE = "#0666EB"       # you / portfolio
CORAL = "#FF6B4A"      # benchmark
GREEN = "#00B67A"      # gains, direct stocks
RED = "#E5484D"        # losses, underweights
VIOLET = "#8E5CF7"
SEQUENTIAL = ["#EAF2FE", "#C4DAFC", "#8DB8F8", "#4F8FF2", "#0666EB", "#0450B8", "#023A87"]

BUCKET_COLORS = {"Core index": BLUE, "US": "#3F5FA8", "Europe": "#5FA8D3", "Japan & Pacific": "#D64545",
                 "Emerging markets": "#00A2C7", "Small-cap": "#B79CFA", "Small-cap value": VIOLET,
                 "Value": "#F2B705", "Momentum": "#F0509A", "Quality": "#0F9B8E", "Minimum volatility": "#8AA1B1",
                 "Multi-factor": "#C2700B", "Dividend": "#E0B000", "ESG": "#6AA84F", "Sector & theme": "#A64D79",
                 "Real estate": "#8D6E63", "Bonds": "#5C6F80", "Money market": "#A9B4C2",
                 "Gold & commodities": "#C9A227", "Direct stocks": GREEN}  # same names as etfs.BUCKETS
REGION_COLORS = {"Americas": BLUE, "Europe": GREEN, "Middle East & Africa": CORAL,
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


# ---------------------------------------------------------------------------
# Plotly template
# ---------------------------------------------------------------------------
_axis = dict(showline=False, zeroline=False, ticks="", tickfont=dict(color=MUTED, size=11),
             title=dict(font=dict(color=MUTED, size=11)), automargin=True)

pio.templates["my_money"] = go.layout.Template(layout=dict(
    font=dict(family=FONT, color=INK, size=12),
    paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
    colorway=[BLUE, CORAL, GREEN, VIOLET, "#F2B705", "#00A2C7", "#F0509A", MUTED],
    xaxis=dict(**_axis, showgrid=False),
    yaxis=dict(**_axis, showgrid=True, gridcolor=GRID, gridwidth=1),
    legend=dict(orientation="h", yanchor="bottom", y=1.02, xanchor="left", x=0,
                font=dict(color=INK_2, size=12), bgcolor="rgba(0,0,0,0)"),
    hoverlabel=dict(bgcolor=INK, bordercolor=INK, font=dict(color="white", family=FONT, size=12)),
    margin=dict(l=8, r=8, t=36, b=8),
    bargap=0.3,
    hovermode="x unified",
))
pio.templates.default = "my_money"


def style(fig, height=380, legend=True, hover="x unified", **layout):
    """Apply the site look to a figure. Extra keyword arguments go straight to fig.update_layout."""
    fig.update_layout(template="my_money", height=height, showlegend=legend, hovermode=hover, **layout)
    return fig
