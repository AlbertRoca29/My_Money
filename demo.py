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


def _assets():
    """asset: (category, value on the first snapshot, expected weekly return, market beta, own weekly noise,
    share of the new savings it receives; the shares add up to 1).

    The funds and stocks are the ones named in config_local.py (FUND_SOURCES, DIRECT_STOCKS) with made-up amounts, so
    Exposure and Backtest, which download data for those names, work with demo data too. Without them, generic names
    are used (and those two pages stay empty)."""
    funds = list(config.FUND_SOURCES) or ["World ETF", "Emerging Markets ETF", "Small Cap Value ETF"]
    stocks = list(config.DIRECT_STOCKS) or ["Apple", "Nvidia", "Inditex"]
    bench = config.LOOKTHROUGH_BENCHMARK
    if bench in funds:  # the comparison fund is the biggest holding
        funds.insert(0, funds.pop(funds.index(bench)))
    fund_values = [14500 * 0.6 ** i for i in range(len(funds))]
    out = {
        "Checking account": ("Cash", 2400, 0, 0, 0, 0.10),
        "Savings account": ("Cash", 5200, 0.0005, 0, 0, 0.10),
        "Gold": ("Commodities", 1300, 0.0014, 0.0, 0.016, 0.04),
        "Bitcoin": ("Crypto", 900, 0.0030, 1.5, 0.050, 0.02),
    }
    for name, value in zip(funds, fund_values):
        emerging = bool(config.FUND_SOURCES.get(name, {}).get("emerging"))
        out[name] = ("ETFs", round(value), 0.0012 if emerging else 0.0017, 1.1 if emerging else 1.0, 0.004,
                     0.60 * value / sum(fund_values))
    for i, name in enumerate(stocks):
        out[name] = ("Stocks", round(1600 * 0.85 ** i), 0.0020, 1.3, 0.020, 0.14 / len(stocks))
    return out


@functools.lru_cache(maxsize=2)
def _portfolios(today):
    rng = random.Random(SEED + 1)
    net = _net_by_day(today)
    assets = _assets()
    day = START + timedelta(days=6)
    values = {name: float(spec[1]) for name, spec in assets.items()}
    snaps = {}
    while True:
        snap = snaps[pd.Timestamp(day)] = {}
        for name, spec in assets.items():
            snap.setdefault(spec[0], {})[name] = round(values[name], 2)
        if day >= today:
            return snaps
        nxt = min(day + timedelta(days=7), today)
        saved = sum(v for d, v in net.items() if day < date.fromisoformat(d) <= nxt)
        market = rng.gauss(0, 0.017)
        for name, (_c, _v, drift, beta, noise, share) in assets.items():
            values[name] = max(0.0, values[name] * (1 + drift + beta * market + rng.gauss(0, noise)) + saved * share)
        day = nxt


def portfolios():
    """{Timestamp: {category: {asset: amount}}}, oldest first, like web/data.py portfolios()."""
    return _portfolios(date.today())
