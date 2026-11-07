"""Made-up data for the "Show demo data" switch (Settings > Demo), so the app can be shown without real numbers.

demo.entries() are Gastos' movements and demo.portfolios() the portfolio snapshots, in the same shapes as the
real ones (gastos/db.py all_entries, web/data.py portfolios). Both are generated from a fixed seed, so they are
the same on every device and every run, and they are linked: the weekly snapshots grow with the savings the
movements say were made, plus some market ups and downs.

Nothing here touches the Google Sheet, and while the switch is on, saving or deleting is refused.
"""
import calendar
import functools
import random
from datetime import date, timedelta

import pandas as pd

import config
import etfs

START = date(2025, 3, 1)
SEED = 7


def _id(rng):
    return f"{rng.getrandbits(32):08x}"


def _months(today):
    y, m = START.year, START.month
    while date(y, m, 1) <= today:
        yield y, m
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)


@functools.lru_cache(maxsize=2)
def _entries(today):
    rng = random.Random(SEED)
    out = []

    def add(kind, day, name, category, amount, gross=None, other=False, note=None):
        if day <= today:
            out.append({"id": _id(rng), "kind": kind, "name": name, "category": category, "date": day.isoformat(),
                        "amount": round(amount, 2), "gross": gross, "paid_by_other": other, "receipt": None, "note": note})

    def spread(n, y, m, names, category, low, high):
        last = calendar.monthrange(y, m)[1]
        for _ in range(n):
            add("expense", date(y, m, rng.randint(1, last)), rng.choice(names), category, rng.uniform(low, high))

    for y, m in _months(today):
        last = calendar.monthrange(y, m)[1]
        raise_ = 1.04 if (y, m) >= (2026, 1) else 1  # a small raise in January
        add("income", date(y, m, min(27, last)), "Salary", "💼 Job", 2380 * raise_, gross=round(3050 * raise_, 2))
        add("expense", date(y, m, 1), "Rent", "🏡 Housing", 720)
        add("expense", date(y, m, 8), "Electricity", "🏡 Housing", rng.uniform(38, 74) + (22 if m in (1, 2, 12) else 0))
        add("expense", date(y, m, 12), "Internet", "🏡 Housing", 39.9)
        add("expense", date(y, m, 14), "Phone", "🏡 Housing", 12.5)
        add("expense", date(y, m, 2), "Transit pass", "🚌 Transportation", 40)
        add("expense", date(y, m, 5), "Spotify", "🎨 Arts & Culture", 10.99)
        add("expense", date(y, m, 5), "Netflix", "🎨 Arts & Culture", 13.99)
        add("expense", date(y, m, 3), "Gym", "🩺 Health & Personal Care", 29.9)

        spread(rng.randint(8, 11), y, m, ["Mercadona", "Lidl", "Carrefour", "Bonpreu", "Fruit shop"], "🛒 Groceries", 9, 62)
        spread(rng.randint(4, 7), y, m, ["Café Central", "Sushi Time", "Bar La Plaça", "Pizzeria Napoli", "Brunch"],
               "🍽️ Restaurants & Cafés", 6, 46)
        spread(rng.randint(1, 3), y, m, ["Uber", "Train ticket", "Bike repair"], "🚌 Transportation", 6, 28)
        spread(rng.randint(0, 2), y, m, ["Pharmacy", "Haircut", "Dentist"], "🩺 Health & Personal Care", 8, 40)
        spread(rng.randint(0, 2), y, m, ["Zara", "Decathlon", "Uniqlo"], "👕 Clothing", 18, 85)
        spread(rng.randint(1, 3), y, m, ["Cinema", "Concert", "Museum", "Bookshop"], "🎨 Arts & Culture", 8, 45)
        spread(rng.randint(1, 3), y, m, ["Drinks with friends", "Club", "Birthday dinner"], "🎉 Parties & Nightlife", 12, 55)
        spread(rng.randint(1, 2), y, m, ["Amazon", "Hardware store", "Gift"], "🤷 Miscellaneous", 8, 60)

        if m in (3, 6, 9, 12):  # dividends: a return, not new savings
            add("income", date(y, m, min(20, last)), "ETF dividend", "📈 Investments", rng.uniform(14, 34))
        if rng.random() < 0.3:
            add("income", date(y, m, rng.randint(1, last)), rng.choice(["Wallapop", "Old bike", "Used books"]),
                "📦 Selling", rng.uniform(25, 130))
        if rng.random() < 0.25:
            add("expense", date(y, m, rng.randint(1, last)), "Dinner with the family", "🍽️ Restaurants & Cafés",
                rng.uniform(40, 90), other=True, note="Paid by my parents")
        if m == 8:
            add("expense", date(y, m, 9), "Flights to Lisbon", "🤷 Miscellaneous", 186.4, note="Summer trip")
            add("expense", date(y, m, 10), "Hotel in Lisbon", "🤷 Miscellaneous", 248, note="Summer trip")
            add("income", date(y, m, 18), "Birthday money", "🎁 Gifts", 100)
        if m == 12:
            spread(4, y, m, ["Christmas gift", "Toy store", "Perfume"], "🤷 Miscellaneous", 18, 70)
            add("income", date(y, m, 25), "Christmas gift", "🎁 Gifts", 150)

    return sorted(out, key=lambda e: e["date"], reverse=True)


def entries():
    return [dict(e) for e in _entries(date.today())]


def _net_by_day(today):
    """Savings per day, counted like gastos/db.py daily_net (dividends and what others paid are left out)."""
    net = {}
    for e in _entries(today):
        if (e["kind"] == "income" and "Investments" in e["category"]) or e["paid_by_other"]:
            continue
        net[e["date"]] = net.get(e["date"], 0) + (e["amount"] if e["kind"] == "income" else -e["amount"])
    return net


# The demo should look like a typical small investor, not like the owner's own portfolio: mostly cash, one
# broad world ETF, an S&P 500 one and a bit of emerging markets, a few well-known stocks and some Bitcoin.
_SP500_TICKERS = {"CSPX", "SXR8", "VUAA", "VUSA", "IUSA", "SPY5", "SPXS"}
_POPULAR_STOCKS = ["Apple", "Nvidia", "Microsoft", "Alphabet", "Amazon", "ASML", "Inditex", "Mastercard"]


def _pick_funds():
    """The world fund (the comparison fund if it is one), an S&P 500 fund and one plain emerging-markets fund,
    picked among the funds named in config_local.py so Exposure and Backtest still have data for them."""
    all_funds = list(config.FUND_SOURCES)
    if not all_funds:
        return "World ETF", "S&P 500 ETF", "Emerging Markets ETF"
    sp500 = next((f for f in all_funds if config.FUND_SOURCES[f].get("ticker") in _SP500_TICKERS
                  or "S&P" in f.upper()), None)
    funds = all_funds
    if config.PRICE_SOURCES:  # funds without a price source are past holdings, and Backtest would drop them
        funds = [f for f in funds if f in config.PRICE_SOURCES] or funds
    spec = lambda f: config.FUND_SOURCES.get(f, {})
    developed = [f for f in funds if not spec(f).get("emerging")]
    emerging = [f for f in funds if spec(f).get("emerging")]
    bench = config.LOOKTHROUGH_BENCHMARK
    core = bench if bench in funds else next((f for f in developed if spec(f).get("bucket") == "Core index"),
                                             (developed or funds)[0])
    # a plain index fund (marked "proxy") rather than a factor one, like most people would buy
    em = next((f for f in emerging if spec(f).get("proxy")), emerging[0] if emerging else None)
    return core, sp500, em


def extra_price_sources():
    """PRICE_SOURCES entries for demo funds that have none in config_local.py (the S&P 500 fund, usually), taken
    from the etfs.py catalogue, so Backtest doesn't leave them out."""
    out = {}
    for name in _pick_funds():
        ticker = config.FUND_SOURCES.get(name, {}).get("ticker") if name else None
        if name and name not in config.PRICE_SOURCES and ticker in etfs.ETFS:
            out[name] = etfs.price_source(ticker)
    return out


def _pick_stocks(n=4):
    stocks = list(config.DIRECT_STOCKS)
    if not stocks:
        return ["Apple", "Nvidia", "Inditex", "Microsoft"][:n]
    popular = [s for s in _POPULAR_STOCKS if s in stocks]
    return (popular + [s for s in stocks if s not in popular])[:n]


def _assets():
    """asset: (category, value on the first snapshot (0 = not bought yet), expected weekly return, market beta,
    own weekly noise).

    The funds and stocks are a few of the ones named in config_local.py (FUND_SOURCES, DIRECT_STOCKS) with made-up
    amounts, so Exposure and Backtest, which download data for those names, work with demo data too. Without
    them, generic names are used (and those two pages stay empty)."""
    core, sp500, em = _pick_funds()
    first, second, third, later = _pick_stocks()
    out = {
        "Checking account": ("Cash", 3100, 0, 0, 0),
        "Savings account": ("Cash", 9200, 0.0004, 0, 0),
        core: ("ETFs", 6800, 0.0017, 1.0, 0.004),
        "Bitcoin": ("Crypto", 1600, 0.0040, 1.5, 0.050),
        first: ("Stocks", 0, 0.0022, 1.5, 0.025),  # bought in May
        second: ("Stocks", 900, 0.0020, 1.2, 0.018),
        third: ("Stocks", 700, 0.0012, 1.2, 0.020),  # swapped for `later` in October
        later: ("Stocks", 0, 0.0018, 1.0, 0.015),
    }
    if sp500:
        out[sp500] = ("ETFs", 1600, 0.0019, 1.05, 0.005)
    if em:
        out[em] = ("ETFs", 1100, 0.0012, 1.1, 0.004)
    return out


def _script():
    """What the demo investor does, as {date: [(action, ...)]}; each runs on the first snapshot on or after it.

    Like most people: a monthly automatic buy of the funds (see _portfolios), and now and then a decision -- buying
    a dip, picking up a stock everybody talks about, swapping one they gave up on, a new-year lump sum, taking some
    profit after a big run. Money comes from, and goes back to, the savings account."""
    core, sp500, em = _pick_funds()
    first, second, third, later = _pick_stocks()
    sp500 = sp500 or core
    return {
        date(2025, 4, 14): [("buy", core, 1500)],                     # buying the April dip
        date(2025, 5, 12): [("buy", first, 1000)],                    # the stock everybody talks about
        date(2025, 7, 21): [("buy", "Bitcoin", 400)],                 # summer crypto hype
        date(2025, 10, 6): [("swap", third, later, 1.0)],             # gives up on one stock for another
        date(2026, 1, 12): [("buy", sp500, 3000)],                    # new-year lump sum
        date(2026, 3, 9): [("sell", "Bitcoin", 0.3)],                # takes some profit after the run
        date(2026, 6, 15): [("sell", first, 0.5), ("buy", core, 0)],  # halves the stock, the money into the world fund
    }


# Market moves that every risky asset feels (times its beta), and ones only Bitcoin feels, by week.
_MARKET_SHOCKS = {date(2025, 4, 7): -0.085, date(2025, 4, 14): -0.03, date(2025, 4, 21): 0.045,
                  date(2025, 4, 28): 0.035, date(2025, 11, 17): -0.035, date(2026, 8, 3): -0.05,
                  date(2026, 8, 17): 0.03}
_CRYPTO_SHOCKS = {date(2025, 7, 14): 0.18, date(2025, 11, 17): -0.22, date(2025, 11, 24): -0.12,
                  date(2026, 2, 16): 0.25, date(2026, 2, 23): 0.12,
                  date(2026, 9, 21): 0.2, date(2026, 10, 5): 0.12}

MONTHLY_BUY = 450  # the automatic buy, a few days after payday
CHECKING_BUFFER = 3000  # above this, what's left over is moved to the savings account at the start of the month


def _shock(table, day, nxt):
    return sum(v for d, v in table.items() if day < d <= nxt)


@functools.lru_cache(maxsize=2)
def _portfolios(today):
    rng = random.Random(SEED + 1)
    net = _net_by_day(today)
    assets = _assets()
    core, sp500, em = _pick_funds()
    plan = {f: w for f, w in ((core, 0.6), (sp500, 0.25), (em, 0.15)) if f}
    plan = {f: w / sum(plan.values()) for f, w in plan.items()}
    script = sorted(_script().items())
    values = {name: float(spec[1]) for name, spec in assets.items()}

    def move(src, dst, amount):
        amount = min(amount, values[src])
        values[src] -= amount
        values[dst] += amount
        return amount

    day = START + timedelta(days=6)
    snaps = {}
    while True:
        snap = snaps[pd.Timestamp(day)] = {}
        for name, spec in assets.items():
            if values[name] >= 0.5 or spec[0] == "Cash":  # what was sold, or not bought yet, isn't listed
                snap.setdefault(spec[0], {})[name] = round(values[name], 2)
        if day >= today:
            return snaps
        nxt = min(day + timedelta(days=7), today)

        market = rng.gauss(0, 0.017) + _shock(_MARKET_SHOCKS, day, nxt)
        crypto = _shock(_CRYPTO_SHOCKS, day, nxt)
        for name, (_c, _v, drift, beta, noise) in assets.items():
            values[name] *= 1 + drift + beta * market + rng.gauss(0, noise) + (crypto if name == "Bitcoin" else 0)
            values[name] = max(0.0, values[name])
        values["Checking account"] += sum(v for d, v in net.items() if day < date.fromisoformat(d) <= nxt)

        if nxt.month != day.month:  # a new month: the automatic buy, and the leftover to savings
            for fund, w in plan.items():
                move("Checking account", fund, MONTHLY_BUY * w)
            if values["Checking account"] > CHECKING_BUFFER:
                move("Checking account", "Savings account", values["Checking account"] - CHECKING_BUFFER)
        proceeds = 0.0
        while script and script[0][0] <= nxt:
            for action, *args in script.pop(0)[1]:
                if action == "buy":  # an amount of 0 spends what the sales just before it brought in
                    move("Savings account", args[0], args[1] or proceeds)
                elif action == "sell":
                    proceeds = move(args[0], "Savings account", values[args[0]] * args[1])
                elif action == "swap":
                    move(args[0], args[1], values[args[0]] * args[2])
        day = nxt


def portfolios():
    """{Timestamp: {category: {asset: amount}}}, oldest first, like web/data.py portfolios()."""
    return _portfolios(date.today())
