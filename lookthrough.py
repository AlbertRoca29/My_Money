"""Look-through exposure of the portfolio's equity (countries, regions, currencies, sectors, companies,
valuation, costs, overlap) compared with a benchmark ETF.

Data sources (fetched live, cached per day by storage.py, under cache/lookthrough/):
  - iShares: "Detailed Holdings and Analytics" workbook (holdings, GICS sectors, countries, TER, P/E, P/B)
  - Vanguard: public GraphQL feed (per-holding GICS sector and country, TER, P/E, P/B), monthly
  - Avantis: product page (full holdings with ISIN, sector weights, P/E, P/B)
"""
import bisect
import collections
import html
import json
import re
import urllib.request
from datetime import datetime

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np

import storage
import pandas as pd
from matplotlib.colors import LinearSegmentedColormap, to_rgb

# ---------------------------------------------------------------------------
# Classification tables
# ---------------------------------------------------------------------------
COUNTRY_NAMES = {
    "US": "United States", "JP": "Japan", "GB": "United Kingdom", "CA": "Canada", "FR": "France",
    "DE": "Germany", "CH": "Switzerland", "NL": "Netherlands", "AU": "Australia", "ES": "Spain",
    "IT": "Italy", "SE": "Sweden", "DK": "Denmark", "NO": "Norway", "FI": "Finland", "BE": "Belgium",
    "AT": "Austria", "IE": "Ireland", "PT": "Portugal", "LU": "Luxembourg", "IL": "Israel",
    "HK": "Hong Kong", "SG": "Singapore", "NZ": "New Zealand", "CY": "Cyprus",
    "CN": "China", "TW": "Taiwan", "KR": "South Korea", "IN": "India", "BR": "Brazil",
    "ZA": "South Africa", "SA": "Saudi Arabia", "MX": "Mexico", "PL": "Poland", "TH": "Thailand",
    "AE": "United Arab Emirates", "MY": "Malaysia", "KW": "Kuwait", "ID": "Indonesia", "CL": "Chile",
    "TR": "Turkey", "QA": "Qatar", "HU": "Hungary", "PH": "Philippines", "CO": "Colombia",
    "CZ": "Czech Republic", "EG": "Egypt", "GR": "Greece", "PE": "Peru",
    "VN": "Vietnam", "NG": "Nigeria", "KE": "Kenya", "MA": "Morocco", "RO": "Romania",
    "EZ": "Other Eurozone", "XD": "Other developed", "XE": "Other emerging",
}
# MSCI market classification (Korea = emerging; FTSE would call it developed)
DEVELOPED = {"US", "JP", "GB", "CA", "FR", "DE", "CH", "NL", "AU", "ES", "IT", "SE", "DK", "NO",
             "FI", "BE", "AT", "IE", "PT", "LU", "IL", "HK", "SG", "NZ", "CY", "EZ", "XD"}
EMERGING = {"CN", "TW", "KR", "IN", "BR", "ZA", "SA", "MX", "PL", "TH", "AE", "MY", "KW", "ID",
            "CL", "TR", "QA", "HU", "PH", "CO", "CZ", "EG", "GR", "PE", "XE"}
FRONTIER = {"VN", "NG", "KE", "MA", "RO", "BD", "PK", "LK", "KZ", "IS", "EE", "LT", "LV", "SI",
            "HR", "RS", "OM", "BH", "JO", "TN", "MU", "UA", "BG", "WA"}
EUROZONE = {"FR", "DE", "NL", "ES", "IT", "FI", "BE", "AT", "IE", "PT", "LU"}

# Continents, west to east: pure geography, so developed/emerging (see market_type) stays a
# separate dimension. Israel and Turkey sit with the Middle East, not with Europe.
REGIONS = {
    **dict.fromkeys(["US", "CA", "BR", "MX", "CL", "CO", "PE"], "Americas"),
    **dict.fromkeys(["GB", "FR", "DE", "CH", "NL", "ES", "IT", "SE", "DK", "NO", "FI", "BE", "AT",
                     "IE", "PT", "LU", "CY", "GR", "PL", "CZ", "HU", "RO", "BG", "UA", "IS", "EE",
                     "LT", "LV", "SI", "HR", "RS", "EZ"], "Europe"),
    **dict.fromkeys(["IL", "TR", "SA", "AE", "QA", "KW", "OM", "BH", "JO", "EG", "ZA", "NG", "KE",
                     "MA", "TN", "MU", "WA"], "Middle East & Africa"),
    **dict.fromkeys(["JP", "CN", "TW", "KR", "IN", "HK", "SG", "TH", "MY", "ID", "PH", "VN", "AU",
                     "NZ", "BD", "PK", "LK", "KZ"], "Asia-Pacific"),
}
# Currency of the listing country (a proxy: multinationals earn in many currencies)
CURRENCIES = {
    "US": "USD", "CA": "CAD", "GB": "GBP", "CH": "CHF", "JP": "JPY", "SE": "SEK", "DK": "DKK",
    "NO": "NOK", "AU": "AUD", "HK": "HKD", "SG": "SGD", "NZ": "NZD", "IL": "ILS",
    **dict.fromkeys(list(EUROZONE) + ["CY", "GR", "EZ"], "EUR"),
    "CN": "CNY/HKD", "TW": "TWD", "KR": "KRW", "IN": "INR", "BR": "BRL", "ZA": "ZAR", "SA": "SAR",
    "MX": "MXN", "PL": "PLN", "TH": "THB", "AE": "AED", "MY": "MYR",
}

CCY_DM = {"USD": "US", "JPY": "JP", "GBP": "GB", "CAD": "CA", "AUD": "AU", "CHF": "CH",
          "SEK": "SE", "DKK": "DK", "NOK": "NO", "HKD": "HK", "SGD": "SG", "ILS": "IL", "NZD": "NZ"}
CCY_EM = {"TWD": "TW", "KRW": "KR", "HKD": "CN", "CNY": "CN", "CNH": "CN", "INR": "IN", "BRL": "BR",
          "ZAR": "ZA", "SAR": "SA", "MXN": "MX", "PLN": "PL", "THB": "TH", "AED": "AE", "MYR": "MY",
          "KWD": "KW", "IDR": "ID", "CLP": "CL", "TRY": "TR", "QAR": "QA", "HUF": "HU", "PHP": "PH",
          "COP": "CO", "CZK": "CZ", "EGP": "EG", "EUR": "GR"}
# Offshore registries in ISINs: overwhelmingly US-listed/US-HQ (or UK crown dependencies)
ISIN_OFFSHORE = {"BM": "US", "MH": "US", "PR": "US", "KY": "US", "VG": "US", "PA": "US",
                 "GG": "GB", "JE": "GB", "IM": "GB"}
SECTOR_ALIASES = {"Communication": "Communication Services"}
CATCH_ALL = {"Other Eurozone", "Other developed", "Other emerging"}  # unallocated residual buckets


def market_type(code):
    if code in DEVELOPED:
        return "Developed"
    if code in EMERGING:
        return "Emerging"
    if code in FRONTIER:
        return "Frontier"
    return "Developed"  # unmapped registries (tiny weights) default to developed


def region(code):
    return REGIONS.get(code, "Unclassified")  # the residual XD/XE buckets have no geography


_SUFFIX = re.compile(r"(?:^|\s)(CLASS [A-Z]|CL [A-Z]|NON VOTING PRE|NON VOTING|SUBORDINATE VOTING|PREF|PRE|PAR|"
                     r"PS|ADR|DEF|SERIES|REIT|INC|CORP|CORPORATION|COMPANY|COMPANIES|COS|CO|LTD|LIMITED|PUBLIC|"
                     r"PLC|AG|SA|SE|NV|ASA|AB|ABP|SCA|OYJ|SPA|FUNDING|HOLDINGS?|GROUP|GROEP|THE|&|[A-Z])$")
# Same company, different names across providers (renames, abbreviations)
KEY_ALIASES = {"GEAEROSPACE": "GENERALELECTRIC", "GLAXOSMITHKLINE": "GSK", "DHL": "DEUTSCHEPOST",
               "LVMH": "LVMHMOETHENNESSYLOUISVUITTON", "LAIRLIQUIDESOCIETEANONYMEPOUR": "AIRLIQUIDE",
               "ASSICURAZIONIGENERALI": "GENERALI", "BMW": "BAYERISCHEMOTORENWERKE",
               "ERICSSON": "TELEFONAKTIEBOLAGETLMERICSSON", "MICHELIN": "CIEGENERALEDESETABLISSEMENTSMICHELIN",
               "ZOOMCOMMUNICATIONS": "ZOOMVIDEOCOMMUNICATIONS", "HENKELKGAA": "HENKELAGCOKGAA",
               "INTERNATIONALAIRLINES": "INTERNATIONALCONSOLIDATEDAIRLINES",
               "AMERIPRISEFINANCE": "AMERIPRISEFINANCIAL", "HARTFORDINSURANCE": "HARTFORDFINANCIALSERVICES"}
_WORD_SUBS = {"COMPAGNIE": "CIE", "CORPORATION": "CORP"}


def issuer_key(name):
    """Normalise an issuer name so share classes and provider spellings collapse to one key."""
    n = re.sub(r"['’]", "", name.upper())
    n = re.sub(r"/[A-Z]+", " ", n)  # "Inc/The", "Inc/DE"
    n = re.sub(r"\s+(COMMON STOCK|ADS REPR|ADR REPR|SPONSORED ADR).*$", "", n)
    n = re.sub(r"\s+", " ", re.sub(r"[^A-Z0-9& ]", " ", n)).strip()
    n = re.sub(r"\bAND\b", "&", n)
    n = " ".join(_WORD_SUBS.get(w, w) for w in n.split())
    prev = None
    while n != prev:
        prev, n = n, _SUFFIX.sub("", n).strip()
    key = re.sub(r"[^A-Z0-9]", "", n) or name.upper()
    return KEY_ALIASES.get(key, key)


DISPLAY_ALIASES = {"TAIWANSEMICONDUCTORMANUFACTURING": "TSMC", "ADVANCEDMICRODEVICES": "AMD", "AMAZONCOM": "Amazon"}


_DISPLAY_SUFFIX = re.compile(r"[\s,]+(&\s*CO|CO\s+LTD|COMMON STOCK.*|CLASS [A-Z]|NON VOTING PRE|INC|CORP|"
                             r"CORPORATION|CO|LTD|LIMITED|PLC|AG|SA|NV|SE|ASA|AB|OYJ|SPA|HOLDINGS?|GROUP|[A-Z])\.?$", re.I)


def _title(word, first):
    if not word.isalpha() or len(word) <= 2 and first or not set(word) & set("AEIOUY"):
        return word  # acronyms and tickers: AT&T, HSBC, BP
    if word in {"OF", "AND", "THE", "DE", "LA"} and not first:
        return word.lower()
    return word if len(word) <= 3 else word.capitalize()


def display_name(name):
    alias = DISPLAY_ALIASES.get(issuer_key(name))
    if alias:
        return alias
    n, prev = name.strip(), None
    while n != prev:
        prev, n = n, _DISPLAY_SUFFIX.sub("", n).strip()
    if name.isupper() and not (" " not in n and len(n) <= 4):  # keep SAP, UBS, BHP…
        n = " ".join(_title(w, i == 0) for i, w in enumerate(n.split()))
    return n


def _num(s):
    m = re.search(r"-?[\d,]*\.?\d+", str(s or ""))
    return float(m.group(0).replace(",", "")) if m else None


# ---------------------------------------------------------------------------
# Fetching (cached per calendar day)
# ---------------------------------------------------------------------------
CACHE_DIR = "lookthrough"  # storage.py folder under cache/
_UA = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 Chrome/128 Safari/537.36"}
ISHARES_URL = ("https://www.blackrock.com/varnish-api/uk-retail01-product-data/product-data/api/v1/"
               "get-fund-document?appType=PRODUCT_PAGE&appSubType=ISHARES&targetSite=ishares-uk"
               "&locale=en_GB&portfolioId={id}&component=fundDownloadV2&userType=individual")
AVANTIS_URL = "https://www.avantisinvestors.com/ucitsetf/{id}/"
AVANTIS_COOKIE = {"Cookie": "countrySelection=gb; country=gb"}  # without it the site redirects to a 404
VANGUARD_URL = "https://www.nl.vanguard/gpx/graphql"
VANGUARD_HOLDINGS_QUERY = """query FundsHoldingsQuery($portIds: [String!], $lastItemKey: String) {
  borHoldings(portIds: $portIds) {
    holdings(limit: 1500, lastItemKey: $lastItemKey) {
      items { issuerName gicsSectorDescription marketValuePercentage bloombergIsoCountry securityType effectiveDate }
      lastItemKey
    }
  }
}"""
VANGUARD_STATS_QUERY = """query Stats($portIds: [String!]!) {
  funds(portIds: $portIds) { profile { feesAndExpenses(getLatest: true) {
    feesAndExpensesType { expenseType(codes: ["TOTEXPRTPC"]) { code value } } } } }
  polarisAnalyticsHistory(portIds: $portIds) { monthly { analytics { fund(getLatest: true) { items { codes {
    PERATIO { analyticValue } PBRATIO { analyticValue } } } } } } }
}"""


def _http(url, data=None, headers=None):
    req = urllib.request.Request(url, data=data, headers={**_UA, **(headers or {})})
    with urllib.request.urlopen(req, timeout=90) as r:
        return r.read()


def _cached(cache_dir, name, fetch):
    return storage.cached_download(cache_dir, name, fetch)


def _vanguard(query, variables):
    body = json.dumps({"query": query, "variables": variables}).encode()
    return json.loads(_http(VANGUARD_URL, body, {"Content-Type": "application/json", "x-consumer-id": "nl0"}))


def _fetch_vanguard_holdings(port_id):
    items, key = [], None
    while True:
        h = _vanguard(VANGUARD_HOLDINGS_QUERY, {"portIds": [port_id], "lastItemKey": key})
        h = h["data"]["borHoldings"][0]["holdings"]
        items += h["items"]
        key = h["lastItemKey"]
        if not key:
            return json.dumps(items).encode()


# ---------------------------------------------------------------------------
# Parsing into fund profiles: {"as_of", "countries", "sectors", "holdings", "names", "stats"} (fractions)
# ---------------------------------------------------------------------------
def _normalize(d):
    tot = sum(v for v in d.values() if v > 0)
    return {k: v / tot for k, v in d.items() if v > 0}


def _sheet_rows(xml, sheet):
    m = re.search(r'<ss:Worksheet ss:Name="%s">(.*?)</ss:Worksheet>' % re.escape(sheet), xml, re.S)
    return [[html.unescape(re.sub(r"<[^>]+>", "", c)).strip()
             for c in re.findall(r"<ss:Cell[^>]*>(.*?)</ss:Cell>", row, re.S)]
            for row in re.findall(r"<ss:Row[^>]*>(.*?)</ss:Row>", m.group(1), re.S)] if m else []


def _ishares_profile(raw, emerging):
    xml = raw.decode("utf-8", errors="ignore")
    if not xml.lstrip().startswith("<?xml"):
        raise ValueError("iShares returned a web page instead of the holdings workbook")
    rows = _sheet_rows(xml, "Holdings")
    holdings, sectors, ccy = collections.Counter(), collections.Counter(), collections.Counter()
    names, keys_by_ccy = {}, collections.defaultdict(set)
    for r in rows[3:]:
        if len(r) > 8 and r[3] == "Equity":
            w, key = float(r[5].replace(",", "")), issuer_key(r[1])
            holdings[key] += w
            names.setdefault(key, display_name(r[1]))
            sectors[SECTOR_ALIASES.get(r[2], r[2])] += w
            ccy[r[8]] += w
            keys_by_ccy[r[8]].add(key)

    listed, other, in_geo = {}, 0.0, False
    for r in _sheet_rows(xml, "Exposure Breakdowns"):
        if r and r[0] == "Geography/Locations":
            in_geo = True
        elif in_geo and len(r) >= 3 and re.fullmatch(r"-?[\d.]+", r[1]):
            if r[2] == "OTHR":
                other = float(r[1])
            elif r[2] != "CASHD_C":
                listed[r[2]] = listed.get(r[2], 0) + float(r[1])

    # The country table only lists the largest ~12 countries: spread "Other" over the
    # unlisted countries implied by each holding's trading currency.
    ccy_map = CCY_EM if emerging else CCY_DM
    candidates = collections.Counter()
    for c, w in ccy.items():
        if ccy_map.get(c) and ccy_map[c] not in listed:
            candidates[ccy_map[c]] += w
    if not emerging:
        eur_rest = ccy.get("EUR", 0) - sum(v for c, v in listed.items() if c in EUROZONE)
        if eur_rest > 0:
            candidates["EZ"] = eur_rest
    countries = dict(listed)
    total = sum(candidates.values())
    scale = min(1.0, other / total) if total else 0
    for c, w in candidates.items():
        countries[c] = countries.get(c, 0) + w * scale
    leftover = other - total * scale
    if leftover > 1e-9:
        countries["XE" if emerging else "XD"] = leftover

    facts = {r[0]: r[1] for sheet in ("Key Facts", "Portfolio Characteristics")
             for r in _sheet_rows(xml, sheet) if len(r) >= 2}
    stats = {"ter": _num(facts.get("Total Expense Ratio")), "pe": _num(facts.get("P/E Ratio")),
             "pb": _num(facts.get("P/B Ratio")), "n_holdings": len(holdings)}
    return {"as_of": _to_iso(rows[1][1]), "holdings": _normalize(holdings), "names": names,
            "sectors": _normalize(sectors), "countries": _normalize(countries), "stats": stats,
            "_china_keys": keys_by_ccy["HKD"] | keys_by_ccy["CNY"] if emerging else set()}


def _avantis_profile(raw):
    t = raw.decode("utf-8", errors="ignore")
    as_of = re.search(r'etfHoldingsAsOfDate:"([^"]+)"', t).group(1).replace("/", "-")
    seg = t[t.find("etfHoldings:["):]
    seg = seg[:seg.find("}]") + 2]
    holdings, countries, names = collections.Counter(), collections.Counter(), {}
    for name, sec_type, isin, weight in re.findall(
            r'\{name:"(.*?)",ticker:".*?",securityType:"(.*?)",cusip:".*?",isin:"(.*?)",.*?weight:"(-?[\d.]+)%"', seg):
        w = float(weight)
        if "CURRENCY" in sec_type or w <= 0:
            continue
        key = issuer_key(name)
        holdings[key] += w
        names.setdefault(key, display_name(name))
        code = ISIN_OFFSHORE.get(isin[:2], isin[:2])
        countries[code if code in COUNTRY_NAMES else "XD"] += w
    sec = re.search(r"sectorWeightings:\[(.*?)\]", t).group(1)
    sectors = {SECTOR_ALIASES.get(n, n): (0.5 if ("<" in w or "003C" in w) else float(w.rstrip("%")))
               for n, w in re.findall(r'name:"(.*?)",weight:"(.*?)"', sec)}  # "<1%" -> 0.5
    sectors.pop("Cash and Cash Equivalents", None)
    field = lambda k: _num((re.search(k + r':"([^"]*)"', t) or [None, None])[1])
    stats = {"ter": None, "pe": field("priceEarningsRatio"), "pb": field("priceBookRatio"),
             "n_holdings": len(holdings)}
    return {"as_of": as_of, "holdings": _normalize(holdings), "names": names,
            "sectors": _normalize(sectors), "countries": _normalize(countries), "stats": stats}


def _vanguard_profile(raw, raw_stats, china_keys):
    items = json.loads(raw)
    holdings, sectors, countries, names = (collections.Counter(), collections.Counter(),
                                           collections.Counter(), {})
    for i in items:
        w = i["marketValuePercentage"] or 0
        if not (i["securityType"] or "").startswith("EQ.") or w <= 0 or not i["issuerName"]:
            continue
        key = issuer_key(i["issuerName"])
        holdings[key] += w
        names.setdefault(key, display_name(i["issuerName"]))
        sectors[i["gicsSectorDescription"] or "Unclassified"] += w
        code = i["bloombergIsoCountry"] or "XD"
        if code == "HK" and key in china_keys:  # HK-listed Chinese companies
            code = "CN"
        countries[code if code in COUNTRY_NAMES else ISIN_OFFSHORE.get(code, "XD")] += w
    d = json.loads(raw_stats)["data"]
    fees = d["funds"][0]["profile"]["feesAndExpenses"]["feesAndExpensesType"][0]["expenseType"]
    codes = d["polarisAnalyticsHistory"][0]["monthly"]["analytics"]["fund"]["items"][0]["codes"]
    stats = {"ter": fees[0]["value"] if fees else None,
             "pe": _num((codes.get("PERATIO") or {}).get("analyticValue")),
             "pb": _num((codes.get("PBRATIO") or {}).get("analyticValue")), "n_holdings": len(holdings)}
    return {"as_of": items[0]["effectiveDate"], "holdings": _normalize(holdings), "names": names,
            "sectors": _normalize(sectors), "countries": _normalize(countries), "stats": stats}


def _to_iso(s):
    for fmt in ("%d/%b/%Y", "%d/%B/%Y"):
        try:
            return datetime.strptime(s.replace("Sept", "Sep"), fmt).strftime("%Y-%m-%d")
        except ValueError:
            pass
    return s


def fetch_fund(spec, cache_dir=CACHE_DIR, china_keys=frozenset()):
    """spec: {"provider": "ishares"|"vanguard"|"avantis", "id", "ticker", optional "emerging", "ter", "proxy"}"""
    p, fid, tk = spec["provider"], spec["id"], spec["ticker"]
    if p == "ishares":
        raw = _cached(cache_dir, f"{tk}.xml", lambda: _http(ISHARES_URL.format(id=fid)))
        prof = _ishares_profile(raw, emerging=spec.get("emerging", False))
    elif p == "avantis":
        prof = _avantis_profile(_cached(cache_dir, f"{tk}.html", lambda: _http(AVANTIS_URL.format(id=fid), headers=AVANTIS_COOKIE)))
    elif p == "vanguard":
        raw = _cached(cache_dir, f"{tk}.json", lambda: _fetch_vanguard_holdings(fid))
        raw_stats = _cached(cache_dir, f"{tk}_stats.json",
                            lambda: json.dumps(_vanguard(VANGUARD_STATS_QUERY, {"portIds": [fid]})).encode())
        prof = _vanguard_profile(raw, raw_stats, china_keys)
    else:
        raise ValueError(f"Unknown provider {p!r}")
    prof["ticker"], prof["provider"] = tk, p
    return prof


# An emerging-markets fund spec whose HKD/CNY holdings mark the HK-listed Chinese companies in Vanguard
# data (which only gives the listing country). Set by the caller; None leaves them under Hong Kong.
CHINA_REFERENCE = None


def _china_reference(cache_dir):
    return fetch_fund(CHINA_REFERENCE, cache_dir)["_china_keys"] if CHINA_REFERENCE else frozenset()


def _stock_profile(label, spec, canon=lambda k: k):
    name, country, sector = spec
    key = canon(issuer_key(name))
    return {"as_of": "direct", "ticker": label, "provider": "direct", "holdings": {key: 1.0},
            "names": {key: name}, "sectors": {sector: 1.0}, "countries": {country: 1.0},
            "stats": {"ter": 0.0, "pe": None, "pb": None, "n_holdings": 1}}


# ---------------------------------------------------------------------------
# Aggregation
# ---------------------------------------------------------------------------
def _blend(parts):
    out = collections.Counter()
    for w, d in parts:
        for k, v in d.items():
            out[k] += w * v
    return out


def _group(countries, fn):
    out = collections.Counter()
    for c, w in countries.items():
        out[fn(c)] += w
    return out


def _market_split(countries):
    return {"Developed": 0.0, "Emerging": 0.0, "Frontier": 0.0, **_group(countries, market_type)}


def _pct(d, digits=4):
    return {k: round(100 * v, digits) for k, v in sorted(d.items(), key=lambda x: -x[1])}


def _country_pct(d):
    return {COUNTRY_NAMES.get(k, k): v for k, v in _pct(d).items()}


def _headline(countries, sectors, holdings, bench_holdings=None):
    """Headline metrics shared by snapshots and the estimated history (percentages)."""
    w = np.array(sorted(holdings.values(), reverse=True))
    out = {"Emerging markets %": 100 * sum(v for c, v in countries.items() if market_type(c) == "Emerging"),
           "United States %": 100 * countries.get("US", 0),
           "Information Technology %": 100 * sectors.get("Information Technology", 0),
           "Top 10 companies %": 100 * w[:10].sum(),
           "Effective # of companies": 1 / (w ** 2).sum()}
    if bench_holdings is not None:
        keys = set(holdings) | set(bench_holdings)
        out["Active share vs benchmark %"] = 50 * sum(abs(holdings.get(k, 0) - bench_holdings.get(k, 0)) for k in keys)
    return {k: round(v, 3) for k, v in out.items()}


def _harmonic(pairs):
    """Weighted harmonic mean (the right average for P/E and P/B) and the weight it covers."""
    pairs = [(w, v) for w, v in pairs if v and v > 0]
    cover = sum(w for w, _ in pairs)
    return (cover / sum(w / v for w, v in pairs) if pairs else None), cover


def _concentration_curve(holdings):
    w = np.cumsum(sorted(holdings.values(), reverse=True)) * 100
    ranks = np.unique(np.geomspace(1, len(w), 80).astype(int))
    return [[int(r), round(float(w[r - 1]), 3)] for r in ranks]


def _positions(portfolio, fund_sources, direct_stocks, funds, canon=lambda k: k):
    """[(label, kind, bucket, eur, profile)] for mapped equity positions + {label: eur} unmapped."""
    out, unmapped = [], {}
    for label, eur in portfolio.get("ETFs", {}).items():
        if not eur:
            continue
        if label in fund_sources:
            spec, prof = fund_sources[label], funds[fund_sources[label]["ticker"]]
            if "ter" in spec or spec.get("proxy"):  # a proxy ETF's fee says nothing about your own fund
                prof = {**prof, "stats": {**prof["stats"], "ter": spec.get("ter")}}
            out.append((label, "ETF", spec.get("bucket", "Other"), eur, prof))
        else:
            unmapped[label] = eur
    for label, eur in portfolio.get("Stocks", {}).items():
        if not eur:
            continue
        if label in direct_stocks:
            out.append((label, "Stock", "Direct stocks", eur, _stock_profile(label, direct_stocks[label], canon)))
        else:
            unmapped[label] = eur
    return out, unmapped


def _reconcile(funds, bt):
    """Map every fund's issuer keys onto the benchmark's spelling where one name is an unambiguous
    prefix of the other ("TEXASINSTRUMENT" -> "TEXASINSTRUMENTS", "PROLOGISREIT" -> "PROLOGIS")."""
    bench_keys = sorted(funds[bt]["holdings"])
    bset, memo = set(bench_keys), {}

    def canon(k):
        if k in memo:
            return memo[k]
        out = k
        if k not in bset and len(k) >= 5:
            # only small leftovers (legal/listing suffixes) or long, specific names count as the same company
            ok = lambda short, long_: len(long_) - len(short) <= 8 or len(short) >= 12
            shorter = next((k[:n] for n in range(len(k) - 1, 4, -1) if k[:n] in bset and ok(k[:n], k)), None)
            i = bisect.bisect_left(bench_keys, k)
            longer = [b for b in bench_keys[i:i + 2] if b.startswith(k) and ok(k, b)]
            out = shorter or (longer[0] if len(longer) == 1 else k)
        memo[k] = out
        return out

    for tk, p in funds.items():
        if tk == bt:
            continue
        holdings, names = collections.Counter(), {}
        for k, w in p["holdings"].items():
            holdings[canon(k)] += w
        for k, n in p["names"].items():
            names.setdefault(canon(k), n)
        p["holdings"], p["names"] = dict(holdings), names
    return canon


def _fetch_all(fund_sources, benchmark, cache_dir):
    china = _china_reference(cache_dir)
    specs = {s["ticker"]: s for s in list(fund_sources.values()) + [benchmark]}
    funds = {tk: fetch_fund(s, cache_dir, china) for tk, s in specs.items()}
    return funds, _reconcile(funds, benchmark["ticker"])


def build_lookthrough(portfolio, fund_sources, direct_stocks, benchmark, date=None, top_n=100,
                      cache_dir=CACHE_DIR):
    """Return a JSON-serialisable look-through snapshot (all weights in % of equity).

    portfolio:      a snapshot dict ({"ETFs": {label: eur}, "Stocks": {label: eur}, ...})
    fund_sources:   {etf label: spec}      direct_stocks: {stock label: (name, ISO country, GICS sector)}
    benchmark:      spec of the comparison fund (e.g. a world index ETF)
    """
    funds, canon = _fetch_all(fund_sources, benchmark, cache_dir)
    sources, unmapped = _positions(portfolio, fund_sources, direct_stocks, funds, canon)
    if unmapped:
        raise KeyError(f"Add these positions to FUND_SOURCES / DIRECT_STOCKS first: {list(unmapped)}")
    bench = funds[benchmark["ticker"]]
    bt = benchmark["ticker"]
    total = sum(s[3] for s in sources)
    names = {}
    for prof in [bench] + [s[4] for s in sources]:
        for k, n in prof["names"].items():
            names.setdefault(k, n)

    agg = {dim: _blend((eur / total, p[dim]) for *_, eur, p in sources)
           for dim in ("countries", "sectors", "holdings")}
    via = collections.defaultdict(dict)
    for label, _, _, eur, p in sources:
        for k, v in p["holdings"].items():
            via[k][label] = round(100 * eur / total * v, 4)

    def top(holdings, with_via):
        rows = []
        for k, w in sorted(holdings.items(), key=lambda x: -x[1])[:top_n]:
            row = {"name": names.get(k, k), "key": k, "weight": round(100 * w, 4),
                   "benchmark_weight": round(100 * bench["holdings"].get(k, 0), 4)}
            if with_via:
                row["eur"] = round(w * total, 2)
                row["direct"] = round(sum(v for l, v in via[k].items() if l in portfolio.get("Stocks", {})), 4)
                row["via"] = dict(sorted(via[k].items(), key=lambda x: -x[1]))
            rows.append(row)
        return rows

    def summary(p, n_holdings):
        return {"as_of": p["as_of"], "market_type": _pct(_market_split(p["countries"])),
                "regions": _pct(_group(p["countries"], region)),
                "currencies": _pct(_group(p["countries"], lambda c: CURRENCIES.get(c, "Other"))),
                "countries": _country_pct(p["countries"]), "sectors": _pct(p["sectors"]),
                "holdings": [{"name": names.get(k, k), "weight": round(100 * w, 4)}
                             for k, w in sorted(p["holdings"].items(), key=lambda x: -x[1])[:n_holdings]]}

    # valuation & costs
    pe, pe_cover = _harmonic((eur / total, p["stats"]["pe"]) for *_, eur, p in sources)
    pb, _ = _harmonic((eur / total, p["stats"]["pb"]) for *_, eur, p in sources)
    known_ter = [(eur, p["stats"]["ter"]) for *_, eur, p in sources if p["stats"]["ter"] is not None]
    ter_cover = sum(e for e, _ in known_ter) / total
    ter = sum(e * t for e, t in known_ter) / sum(e for e, _ in known_ter) if known_ter else None
    port_stats = {**_headline(agg["countries"], agg["sectors"], agg["holdings"], bench["holdings"]),
                  "Companies held": sum(1 for v in agg["holdings"].values() if v > 0),
                  "Direct stocks %": round(100 * sum(s[3] for s in sources if s[1] == "Stock") / total, 3),
                  "Euro currency %": round(100 * _group(agg["countries"], lambda c: CURRENCIES.get(c)).get("EUR", 0), 3),
                  "P/E": pe and round(pe, 2), "P/E coverage %": round(100 * pe_cover, 1),
                  "P/B": pb and round(pb, 2), "TER %": ter and round(ter, 3),
                  "TER coverage %": round(100 * ter_cover, 1),
                  "Cost €/year": round(sum(e * t / 100 for e, t in known_ter), 2)}
    b_stats = {**_headline(bench["countries"], bench["sectors"], bench["holdings"], bench["holdings"]),
               "Companies held": bench["stats"]["n_holdings"], "Direct stocks %": 0.0,
               "Euro currency %": round(100 * _group(bench["countries"], lambda c: CURRENCIES.get(c)).get("EUR", 0), 3),
               "P/E": bench["stats"]["pe"], "P/B": bench["stats"]["pb"], "TER %": bench["stats"]["ter"],
               "Cost €/year": round(total * (bench["stats"]["ter"] or 0) / 100, 2)}

    # overlap between the ETFs you hold (share of holdings in common)
    etf_labels = [s[0] for s in sources if s[1] == "ETF"]
    profs = {s[0]: s[4]["holdings"] for s in sources if s[1] == "ETF"}
    if not any(s[4]["ticker"] == bt for s in sources):
        etf_labels.append(f"{bt} (benchmark)")
        profs[f"{bt} (benchmark)"] = bench["holdings"]
    overlap = [[round(100 * sum(min(v, profs[b].get(k, 0)) for k, v in profs[a].items()), 1)
                for b in etf_labels] for a in etf_labels]

    # which strategy bucket drives each sector / region weight
    attribution = {dim: collections.defaultdict(collections.Counter) for dim in ("sectors", "regions", "countries")}
    for _, _, bucket, eur, p in sources:
        for s, v in p["sectors"].items():
            attribution["sectors"][bucket][s] += 100 * eur / total * v
        for c, v in p["countries"].items():
            attribution["regions"][bucket][region(c)] += 100 * eur / total * v
            attribution["countries"][bucket][COUNTRY_NAMES.get(c, c)] += 100 * eur / total * v

    # largest company-level over/underweights vs the benchmark (full holdings on both sides)
    active = sorted(((k, agg["holdings"].get(k, 0) - bench["holdings"].get(k, 0))
                     for k in set(agg["holdings"]) | set(bench["holdings"])), key=lambda x: x[1])
    active_holdings = [{"name": names.get(k, k), "weight": round(100 * agg["holdings"].get(k, 0), 4),
                        "benchmark_weight": round(100 * bench["holdings"].get(k, 0), 4), "active": round(100 * v, 4)}
                       for k, v in active[:50] + active[-50:]]

    result = {
        "date": date,
        "generated": datetime.now().isoformat(timespec="seconds"),
        "total_equity_eur": total,
        "positions": [{"label": l, "type": kind, "bucket": bucket, "ticker": p["ticker"],
                       "provider": p["provider"], "as_of": p["as_of"], "eur": eur,
                       "weight": round(100 * eur / total, 4), **p["stats"],
                       "em_share": round(100 * _market_split(p["countries"])["Emerging"], 2),
                       "top_holding": names.get(max(p["holdings"], key=p["holdings"].get))}
                      for l, kind, bucket, eur, p in sources],
        "portfolio": {**summary({"as_of": None, **agg}, 0), "holdings": top(agg["holdings"], with_via=True)},
        "benchmark": {"ticker": bt, **summary(bench, top_n)},
        "stats": {"portfolio": port_stats, "benchmark": b_stats},
        "active_holdings": active_holdings,
        "overlap": {"labels": etf_labels, "matrix": overlap},
        "attribution": {dim: {b: {k: round(v, 4) for k, v in c.items()} for b, c in d.items()}
                        for dim, d in attribution.items()},
        "concentration": {"portfolio": _concentration_curve(agg["holdings"]),
                          "benchmark": _concentration_curve(bench["holdings"])},
        "funds": {tk: summary(p, 15) for tk, p in funds.items()},
    }
    result["portfolio"].pop("as_of")
    result["insights"] = insights(result)
    return result


def estimate_history(portfolios, fund_sources, direct_stocks, benchmark, cache_dir=CACHE_DIR):
    """Headline exposures for every past snapshot, using *today's* fund holdings.

    Shows how your allocation decisions moved your exposures (fund compositions are held constant).
    Returns (DataFrame indexed by Date, benchmark headline metrics, {unmapped label: number of snapshots}).
    """
    funds, canon = _fetch_all(fund_sources, benchmark, cache_dir)
    bench = funds[benchmark["ticker"]]
    rows, missing = [], collections.Counter()
    for date, pf in sorted(portfolios.items()):
        sources, unmapped = _positions(pf, fund_sources, direct_stocks, funds, canon)
        missing.update(unmapped.keys())
        total = sum(s[3] for s in sources)
        if not total:
            continue
        agg = {dim: _blend((eur / total, p[dim]) for *_, eur, p in sources)
               for dim in ("countries", "sectors", "holdings")}
        rows.append({"Date": pd.Timestamp(date), "Equity €": total,
                     "Coverage %": round(100 * total / (total + sum(unmapped.values())), 1),
                     **_headline(agg["countries"], agg["sectors"], agg["holdings"], bench["holdings"])})
    bench_row = _headline(bench["countries"], bench["sectors"], bench["holdings"], bench["holdings"])
    return pd.DataFrame(rows).set_index("Date"), bench_row, dict(missing)


# ---------------------------------------------------------------------------
# Insights (plain-language findings)
# ---------------------------------------------------------------------------
def insights(r):
    bt, sp, sb = r["benchmark"]["ticker"], r["stats"]["portfolio"], r["stats"]["benchmark"]
    port, bench = r["portfolio"], r["benchmark"]
    out = []

    h = port["holdings"][0]
    ratio = h["weight"] / h["benchmark_weight"] if h["benchmark_weight"] else float("inf")
    src = max(h["via"], key=h["via"].get)
    out.append(f"Largest single company: **{h['name']} {h['weight']:.1f}%** of equity "
               f"({'not in ' + bt if ratio == float('inf') else f'{ratio:.1f}× its {bt} weight'}), "
               f"mostly via {src} ({h['via'][src]:.1f} pp).")

    big = [x for x in port["holdings"] if x["weight"] >= 1 and x["weight"] >= 3 * x["benchmark_weight"]]
    if big:
        out.append("Concentrated bets (≥1% and ≥3× the benchmark): "
                   + ", ".join(f"{x['name']} {x['weight']:.1f}%" for x in big) + ".")

    a = sp["Active share vs benchmark %"]
    label = "close to an index fund" if a < 20 else "a moderately active portfolio" if a < 60 else "a highly active portfolio"
    out.append(f"Active share vs {bt}: **{a:.0f}%** → {label}. It behaves like "
               f"**{sp['Effective # of companies']:.0f} equally weighted companies** "
               f"({bt}: {sb['Effective # of companies']:.0f}).")

    def gaps(p, b):
        d = {k: p.get(k, 0) - b.get(k, 0) for k in set(p) | set(b) if k not in CATCH_ALL}
        s = sorted(d.items(), key=lambda x: x[1])
        return s[-1], s[0]

    (so, sov), (su, suv) = gaps(port["sectors"], bench["sectors"])
    (co, cov), (cu, cuv) = gaps(port["countries"], bench["countries"])
    out.append(f"Biggest sector tilts: **{so} {sov:+.1f} pp**, {su} {suv:+.1f} pp. "
               f"Biggest country tilts: **{co} {cov:+.1f} pp**, {cu} {cuv:+.1f} pp.")

    out.append(f"Emerging markets {sp['Emerging markets %']:.1f}% vs {sb['Emerging markets %']:.1f}% in {bt}; "
               f"euro-listed companies {sp['Euro currency %']:.1f}% vs {sb['Euro currency %']:.1f}% "
               f"(the rest is currency exposure for a euro investor).")

    labels, m = r["overlap"]["labels"], r["overlap"]["matrix"]
    pairs = [(m[i][j], labels[i], labels[j]) for i in range(len(labels)) for j in range(i + 1, len(labels))]
    if pairs:
        v, x, y = max(pairs)
        out.append(f"Most redundant pair of funds: **{x} & {y}** share {v:.0f}% of their holdings.")

    if sp["P/E"] and sb["P/E"]:
        cheaper = (1 - sp["P/E"] / sb["P/E"]) * 100
        out.append(f"Valuation: P/E **{sp['P/E']:.1f}** vs {sb['P/E']:.1f} ({abs(cheaper):.0f}% "
                   f"{'cheaper' if cheaper > 0 else 'more expensive'}); P/B {sp['P/B']:.2f} vs {sb['P/B']:.2f} "
                   f"(funds only, {sp['P/E coverage %']:.0f}% of equity).")

    if sp["TER %"] is not None:
        note = "" if sp["TER coverage %"] >= 99.9 else f" — {100 - sp['TER coverage %']:.0f}% of equity has no fee set"
        out.append(f"Ongoing charges: **{sp['TER %']:.2f}%/yr ≈ €{sp['Cost €/year']:.0f}/yr** vs "
                   f"{sb['TER %']:.2f}% ≈ €{sb['Cost €/year']:.0f}/yr if everything were in {bt}{note}.")

    sec = r["attribution"]["sectors"]
    over = max(port["sectors"], key=lambda s: port["sectors"][s] - bench["sectors"].get(s, 0))
    driver = max(sec, key=lambda b: sec[b].get(over, 0))
    out.append(f"Your {over} overweight comes mainly from **{driver}** "
               f"({sec[driver].get(over, 0):.1f} of {port['sectors'][over]:.1f} pp).")
    return out


# ---------------------------------------------------------------------------
# Snapshots
# ---------------------------------------------------------------------------
def save_snapshot(result):
    """Keep one look-through result per day, as lookthrough/<date>.json (see storage.py)."""
    key = f"lookthrough/{result['date']}.json"
    storage.write(key, json.dumps(result, indent=1, ensure_ascii=False).encode(), "application/json")
    return key


def load_snapshots():
    return {k.split("/")[-1].removesuffix(".json"): json.loads(storage.read(k))
            for k in storage.keys("lookthrough/") if k.endswith(".json")}


# ---------------------------------------------------------------------------
# Tables
# ---------------------------------------------------------------------------
def tables(r, n_countries=25, n_holdings=50):
    bench, port = r["benchmark"], r["portfolio"]
    bt = bench["ticker"]

    def compare(p, b, index_name):
        df = pd.DataFrame({"Portfolio %": pd.Series(p, dtype=float), f"{bt} %": pd.Series(b, dtype=float)}).fillna(0)
        df["Active (pp)"] = df["Portfolio %"] - df[f"{bt} %"]
        df.index.name = index_name
        df = df[(df["Portfolio %"] >= 0.005) | (df[f"{bt} %"] >= 0.005)]
        return df.sort_values("Portfolio %", ascending=False).round(2)

    holdings = pd.DataFrame([{"Company": h["name"], "Portfolio %": h["weight"], "€": h["eur"],
                              f"{bt} %": h["benchmark_weight"], "Direct %": h["direct"],
                              "Via": ", ".join(f"{k} {v:.2f}" for k, v in h["via"].items() if v >= 0.005)}
                             for h in port["holdings"][:n_holdings]]).round(2)
    holdings.index = range(1, len(holdings) + 1)
    active = pd.DataFrame(r.get("active_holdings", [])).rename(
        columns={"name": "Company", "weight": "Portfolio %", "benchmark_weight": f"{bt} %", "active": "Active (pp)"})
    positions = pd.DataFrame(r["positions"]).set_index("label")
    cards = positions.rename(columns={"type": "Type", "bucket": "Bucket", "ticker": "Data from", "eur": "€",
                                      "weight": "Weight %", "ter": "TER %", "pe": "P/E", "pb": "P/B",
                                      "em_share": "EM %", "n_holdings": "Holdings", "top_holding": "Top holding",
                                      "as_of": "As of"})
    cards = cards[["Type", "Bucket", "Data from", "€", "Weight %", "TER %", "P/E", "P/B", "EM %",
                   "Holdings", "Top holding", "As of"]].round(2)
    sp, sb = r["stats"]["portfolio"], r["stats"]["benchmark"]

    def fmt(metric, v):
        if v is None or pd.isna(v):
            return "—"
        if metric == "TER %":
            return f"{v:.2f}%"
        if metric.endswith("%"):
            return f"{v:.1f}%"
        if metric == "Cost €/year":
            return f"€{v:,.0f}"
        if metric in ("P/E", "P/B"):
            return f"{v:.2f}"
        return f"{v:,.0f}"

    rows = [m for m in sp if "coverage" not in m]
    score = pd.DataFrame({"Portfolio": [fmt(m, sp.get(m)) for m in rows],
                          bt: [fmt(m, sb.get(m)) for m in rows]},
                         index=[m.replace(" %", " (%)") for m in rows])
    return {"scorecard": score, "positions": cards, "market": compare(port["market_type"], bench["market_type"], "Market"),
            "regions": compare(port["regions"], bench["regions"], "Region"),
            "currencies": compare(port["currencies"], bench["currencies"], "Currency"),
            "countries": compare(port["countries"], bench["countries"], "Country"),
            "top_countries": compare(port["countries"], bench["countries"], "Country").head(n_countries),
            "sectors": compare(port["sectors"], bench["sectors"], "Sector"), "holdings": holdings,
            "active_holdings": active.round(3),
            "overlap": pd.DataFrame(r["overlap"]["matrix"], index=r["overlap"]["labels"],
                                    columns=r["overlap"]["labels"])}


# ---------------------------------------------------------------------------
# Charts (palette validated for colour-vision deficiency; light surface)
# ---------------------------------------------------------------------------
PORTFOLIO_C, BENCH_C, DIRECT_C = "#2a78d6", "#eb6834", "#1baf7a"
OVER_C, UNDER_C = "#2a78d6", "#e34948"
BUCKET_COLORS = {"Core index": "#2a78d6", "US": "#3f5fa8", "Europe": "#5fa8d3", "Japan & Pacific": "#c0392b",
                 "Emerging markets": "#008300", "Small-cap": "#7d6bd1", "Small-cap value": "#4a3aa7",
                 "Value": "#eda100", "Momentum": "#e87ba4", "Quality": "#0f9b8e", "Minimum volatility": "#8aa1b1",
                 "Multi-factor": "#b5651d", "Dividend": "#d4a017", "ESG": "#6aa84f", "Sector & theme": "#a64d79",
                 "Real estate": "#8d6e63", "Bonds": "#5c6f80", "Money market": "#a9b4c2",
                 "Gold & commodities": "#c9a227", "Direct stocks": "#1baf7a"}
SEQUENTIAL = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#256abf", "#184f95", "#0d366b"]
SURFACE, INK, INK_2, MUTED, GRID, BASELINE = "#fcfcfb", "#0b0b0b", "#52514e", "#898781", "#e1e0d9", "#c3c2b7"


def _fmt_date(d):
    return f"{d[:4]}-{d[4:6]}-{d[6:]}" if d and len(d) == 8 else str(d)


def _style(ax, title, xlabel="% of equity"):
    ax.set_facecolor(SURFACE)
    ax.figure.set_facecolor(SURFACE)
    for side in ("top", "right"):
        ax.spines[side].set_visible(False)
    for side in ("left", "bottom"):
        ax.spines[side].set_color(BASELINE)
    ax.tick_params(colors=MUTED, labelcolor=INK_2, length=0, labelsize=9)
    ax.grid(True, axis="x", color=GRID, lw=0.8)
    ax.set_axisbelow(True)
    ax.set_xlabel(xlabel, color=MUTED, fontsize=9)
    ax.set_title(title, loc="left", color=INK, fontsize=12, weight="bold", pad=10)


def _legend(ax, **kw):
    return ax.legend(frameon=False, fontsize=9, labelcolor=INK_2, **kw)


def _suptitle(fig, text):
    fig.suptitle(text, x=0.01, ha="left", fontsize=14, weight="bold", color=INK)


def _grouped_barh(ax, df, bt):
    y = np.arange(len(df))
    h = 0.38
    ax.barh(y - h / 2, df["Portfolio %"], height=h, color=PORTFOLIO_C, label="Portfolio",
            edgecolor=SURFACE, linewidth=1)
    ax.barh(y + h / 2, df[f"{bt} %"], height=h, color=BENCH_C, label=bt, edgecolor=SURFACE, linewidth=1)
    ax.set_yticks(y, df.index)
    ax.invert_yaxis()
    _legend(ax, loc="lower right")


def _without_us(df, bt):
    """Drop the United States row (it dwarfs everything else) and describe it in words instead."""
    if "United States" not in df.index:
        return df, ""
    us = df.loc["United States"]
    return df.drop("United States"), f" — ex-US (US: {us['Portfolio %']:.1f}% vs {us[f'{bt} %']:.1f}%)"


def plot_overview(r, n_countries=25):
    """Market type, top countries (ex-US) and sectors: portfolio vs benchmark."""
    t, bt = tables(r), r["benchmark"]["ticker"]
    countries, us_note = _without_us(t["countries"].drop(CATCH_ALL, errors="ignore"), bt)
    countries = countries.head(n_countries)
    fig = plt.figure(figsize=(14, 0.3 * len(countries) + 5.5), layout="constrained")
    gs = fig.add_gridspec(2, 2, height_ratios=[1, 0.3 * len(countries) + 1])
    ax0 = fig.add_subplot(gs[0, :])
    m = t["market"].reindex(["Developed", "Emerging", "Frontier"]).fillna(0)
    _grouped_barh(ax0, m, bt)
    for i, (p, b) in enumerate(zip(m["Portfolio %"], m[f"{bt} %"])):
        ax0.text(p + 0.8, i - 0.19, f"{p:.1f}%", va="center", fontsize=9, color=INK_2)
        ax0.text(b + 0.8, i + 0.19, f"{b:.1f}%", va="center", fontsize=9, color=INK_2)
    _style(ax0, "Developed vs emerging vs frontier (MSCI classification)")
    ax1 = fig.add_subplot(gs[1, 0])
    _grouped_barh(ax1, countries, bt)
    _style(ax1, f"Top {len(countries)} countries{us_note}")
    ax2 = fig.add_subplot(gs[1, 1])
    _grouped_barh(ax2, t["sectors"], bt)
    _style(ax2, "Sectors (GICS)")
    _suptitle(fig, f"Look-through exposure vs {bt} — {_fmt_date(r['date'])}")
    return fig


def plot_regions_currencies(r):
    """Regions and listing currencies: portfolio vs benchmark."""
    t, bt = tables(r), r["benchmark"]["ticker"]
    cur = t["currencies"]
    named = cur.drop("Other", errors="ignore")
    tail = pd.concat([named.iloc[15:], cur.loc[["Other"]] if "Other" in cur.index else None])
    cur = pd.concat([named.iloc[:15], pd.DataFrame([tail.drop(columns="Active (pp)").sum()], index=["Other"])])
    fig, axes = plt.subplots(1, 2, figsize=(14, 0.32 * len(cur) + 2.5), layout="constrained")
    _grouped_barh(axes[0], t["regions"], bt)
    _style(axes[0], "Regions")
    _grouped_barh(axes[1], cur, bt)
    _style(axes[1], "Currency of the listing market")
    _suptitle(fig, f"Where your companies are listed vs {bt}")
    return fig


# Country pies: hue = continent, lighter shades = the smaller countries inside it. The four hues
# pass the CVD validator on every pair (worst ΔE 9.2 deutan, 16.3 normal vision); the per-panel
# legend and the in-wedge labels carry identity as well as colour.
REGION_COLORS = {
    "Americas": "#2a78d6", "Europe": "#1baf7a", "Middle East & Africa": "#eb6834",
    "Asia-Pacific": "#4a3aa7", "Unclassified": "#8d8b84",
}
OTHER_C = "#dcdad2"
COUNTRY_CODES = {name: code for code, name in COUNTRY_NAMES.items()}


def _shades(base, n):
    """n tints of one hue, the full hue first — the biggest country in a region keeps it."""
    rgb = np.array(to_rgb(base))
    return [tuple(rgb + (1 - rgb) * t) for t in np.linspace(0, min(0.16 * (n - 1), 0.62), n)]


def _country_slices(countries, min_pct, max_slices):
    """(labels, values, colors) for one pie: named countries grouped by region, then 'Other'."""
    scale = 100 / (sum(countries.values()) or 1)   # direct-stock panels arrive as % of the portfolio
    ranked = sorted(((c, v * scale) for c, v in countries.items() if v > 0), key=lambda x: -x[1])
    named, rest = ranked[:max_slices], ranked[max_slices:]
    cut = next((i for i, (_, v) in enumerate(named) if v < min_pct), len(named))
    named, rest = named[:cut], named[cut:] + rest
    by_region = collections.defaultdict(list)
    for c, v in named:
        by_region[region(COUNTRY_CODES.get(c, c))].append((c, v))
    labels, values, colors = [], [], []
    for reg in list(REGION_COLORS) + [k for k in by_region if k not in REGION_COLORS]:
        group = by_region.get(reg, [])
        for (c, v), color in zip(group, _shades(REGION_COLORS.get(reg, MUTED), len(group))):
            labels.append(c)
            values.append(v)
            colors.append(color)
    if rest:
        labels.append(f"Rest of the world · {len(rest)} countr{'y' if len(rest) == 1 else 'ies'}")
        values.append(sum(v for _, v in rest))
        colors.append(OTHER_C)
    return labels, values, colors


def _country_pie(ax, legend_ax, title, countries, subtitle, min_pct, max_slices):
    labels, values, colors = _country_slices(countries, min_pct, max_slices)
    wedges, _ = ax.pie(values, colors=colors, startangle=90, counterclock=False,
                       wedgeprops={"edgecolor": SURFACE, "linewidth": 1.6})
    for w, label, v in zip(wedges, labels, values):
        if v < 6:
            continue  # too thin to label inside — the legend below names it
        angle = np.deg2rad((w.theta1 + w.theta2) / 2)
        lum = np.dot(to_rgb(w.get_facecolor()), [0.299, 0.587, 0.114])
        ax.text(0.62 * np.cos(angle), 0.62 * np.sin(angle),
                f"{COUNTRY_CODES.get(label, '')}\n{v:.0f}%".strip(), ha="center", va="center",
                fontsize=8.5, weight="bold", color=INK if lum > 0.62 else "white")
    ax.set_title(title, fontsize=12, weight="bold", color=INK, pad=18)
    ax.text(0.5, 1.01, subtitle, transform=ax.transAxes, ha="center", va="bottom",
            fontsize=8.5, color=MUTED)
    legend_ax.legend(wedges, [f"{l}  {v:.1f}%" for l, v in zip(labels, values)], loc="upper center",
                     ncols=2, frameon=False, fontsize=8, labelcolor=INK_2, handlelength=0.9,
                     handleheight=0.9, labelspacing=0.45, columnspacing=1.2, borderpad=0)


def plot_country_pies(r, min_pct=1.0, max_slices=12, ncols=3, include_stocks=True):
    """A country pie for the whole portfolio, for the benchmark and for every ETF you hold.

    Countries below `min_pct` of the panel collapse into a grey "Other" slice; the exact figure for
    every country is in `tables(r)["countries"]`.
    """
    bt = r["benchmark"]["ticker"]
    n_countries = sum(1 for v in r["portfolio"]["countries"].values() if v > 0)
    panels = [("Portfolio (look-through)", r["portfolio"]["countries"],
               f"\u20ac{r['total_equity_eur']:,.0f} of equity \u00b7 {n_countries} countries"),
              (f"{bt} \u2014 benchmark", r["benchmark"]["countries"],
               f"as of {r['benchmark']['as_of']}")]
    for p in sorted((p for p in r["positions"] if p["type"] == "ETF"), key=lambda p: -p["weight"]):
        fund = r["funds"][p["ticker"]]
        panels.append((f"{p['label']} ({p['ticker']})", fund["countries"],
                       f"{p['weight']:.1f}% of equity \u00b7 as of {fund['as_of']}"))
    direct = r.get("attribution", {}).get("countries", {}).get("Direct stocks")
    if include_stocks and direct:
        panels.append(("Direct stocks", direct, f"{sum(direct.values()):.1f}% of equity"))

    nrows = -(-len(panels) // ncols)
    fig = plt.figure(figsize=(5.0 * ncols, 6.3 * nrows), layout="constrained")
    gs = fig.add_gridspec(2 * nrows, ncols, height_ratios=[1, 0.5] * nrows)
    for i, panel in enumerate(panels):
        row, col = divmod(i, ncols)
        legend_ax = fig.add_subplot(gs[2 * row + 1, col])
        legend_ax.axis("off")
        _country_pie(fig.add_subplot(gs[2 * row, col]), legend_ax, *panel, min_pct, max_slices)
    shown = {region(COUNTRY_CODES.get(c, c))
             for _, countries, _ in panels
             for c in _country_slices(countries, min_pct, max_slices)[0] if c in countries}
    keys = [reg for reg in REGION_COLORS if reg in shown]
    colors = [REGION_COLORS[reg] for reg in keys] + [OTHER_C]
    fig.legend([plt.Rectangle((0, 0), 1, 1, color=c) for c in colors], keys + ["Rest of the world"],
               loc="outside lower center", ncols=min(len(colors), 5), frameon=False, fontsize=9,
               labelcolor=INK_2, title="Slice colour = continent (lighter = smaller country in it)",
               title_fontproperties={"size": 9, "weight": "bold"})
    fig.set_facecolor(SURFACE)
    _suptitle(fig, f"Country exposure \u2014 portfolio, {bt} and each fund \u00b7 {_fmt_date(r['date'])}")
    return fig


def plot_active(r, n_countries=20):
    """Over/underweights vs the benchmark (percentage points)."""
    t, bt = tables(r), r["benchmark"]["ticker"]
    c = t["countries"]["Active (pp)"].drop(CATCH_ALL, errors="ignore")
    c = c.reindex(c.abs().sort_values(ascending=False).index[:n_countries]).sort_values()
    s = t["sectors"]["Active (pp)"].sort_values()
    fig, axes = plt.subplots(1, 2, figsize=(14, 0.3 * max(len(c), len(s)) + 2), layout="constrained")
    for ax, ser, title in [(axes[0], s, "Sectors"), (axes[1], c, f"Countries (largest {n_countries} gaps)")]:
        ax.barh(ser.index, ser.values, height=0.6, color=[OVER_C if v >= 0 else UNDER_C for v in ser.values])
        ax.axvline(0, color=BASELINE, lw=1)
        _style(ax, title, xlabel=f"percentage points vs {bt}")
        lim = max(abs(ser.values).max() * 1.15, 1)
        ax.set_xlim(-lim, lim)
    handles = [plt.Rectangle((0, 0), 1, 1, color=OVER_C), plt.Rectangle((0, 0), 1, 1, color=UNDER_C)]
    fig.legend(handles, ["Overweight", "Underweight"], loc="upper right", frameon=False, fontsize=9,
               labelcolor=INK_2, ncols=2)
    _suptitle(fig, f"Active weights vs {bt}")
    return fig


def plot_attribution(r, n_countries=20):
    """Which strategy bucket each sector / region / country weight comes from, with the benchmark weight."""
    bt, attr = r["benchmark"]["ticker"], r["attribution"]
    buckets = [b for b in BUCKET_COLORS if b in attr["sectors"]] + \
              [b for b in attr["sectors"] if b not in BUCKET_COLORS]
    has_countries = "countries" in attr
    fig = plt.figure(figsize=(14, 6 + (0.3 * n_countries + 1.5 if has_countries else 0)), layout="constrained")
    gs = fig.add_gridspec(2 if has_countries else 1, 2, height_ratios=[6, 0.3 * n_countries + 1.5] if has_countries else [1])
    panels = [(fig.add_subplot(gs[0, 0]), "sectors", "Sectors", None),
              (fig.add_subplot(gs[0, 1]), "regions", "Regions", None)]
    if has_countries:
        us = r["portfolio"]["countries"].get("United States", 0)
        panels.append((fig.add_subplot(gs[1, :]), "countries",
                       f"Top {n_countries} countries — ex-US (US: {us:.1f}% vs "
                       f"{r['benchmark']['countries'].get('United States', 0):.1f}%)", n_countries))
    for ax, dim, title, limit in panels:
        order = sorted(r["portfolio"][dim], key=lambda k: -r["portfolio"][dim][k])
        order = [k for k in order if r["portfolio"][dim][k] >= 0.05 and not (limit and k in {"United States"} | CATCH_ALL)]
        order = order[:limit] if limit else order
        y, left = np.arange(len(order)), np.zeros(len(order))
        for b in buckets:
            vals = np.array([attr[dim].get(b, {}).get(k, 0) for k in order])
            ax.barh(y, vals, left=left, height=0.62, color=BUCKET_COLORS.get(b, MUTED), label=b,
                    edgecolor=SURFACE, lw=1)
            left += vals
        ax.scatter([r["benchmark"][dim].get(k, 0) for k in order], y, marker="|", s=200,
                   linewidths=2.5, color=BENCH_C, label=f"{bt} weight", zorder=3)
        ax.set_yticks(y, order)
        ax.invert_yaxis()
        ax.margins(x=0.04)
        _style(ax, title)
    _legend(panels[1][0], loc="lower right")
    _suptitle(fig, "Where each exposure comes from")
    return fig


def plot_active_companies(r, n=20):
    """Largest company-level overweights and underweights vs the benchmark."""
    bt = r["benchmark"]["ticker"]
    a = sorted(r.get("active_holdings", []), key=lambda x: x["active"])
    rows = a[:n] + [x for x in a[-n:] if x not in a[:n]]
    fig, ax = plt.subplots(figsize=(12, 0.27 * len(rows) + 1.8), layout="constrained")
    y = np.arange(len(rows))
    vals = [x["active"] for x in rows]
    ax.barh(y, vals, height=0.62, color=[OVER_C if v >= 0 else UNDER_C for v in vals])
    for i, x in enumerate(rows):
        off = 0.05 if x["active"] >= 0 else -0.05
        ax.text(x["active"] + off, i, f"{x['weight']:.2f}% vs {x['benchmark_weight']:.2f}%", va="center",
                ha="left" if x["active"] >= 0 else "right", fontsize=7.5, color=INK_2)
    ax.axvline(0, color=BASELINE, lw=1)
    ax.set_yticks(y, [x["name"] for x in rows])
    ax.invert_yaxis()
    lim = max(abs(v) for v in vals) * 1.45
    ax.set_xlim(-lim, lim)
    _style(ax, f"Companies: {n} largest overweights and underweights vs {bt}  (labels: portfolio vs {bt})",
           xlabel=f"percentage points vs {bt}")
    handles = [plt.Rectangle((0, 0), 1, 1, color=OVER_C), plt.Rectangle((0, 0), 1, 1, color=UNDER_C)]
    ax.legend(handles, ["Overweight", "Underweight"], loc="lower right", frameon=False, fontsize=9, labelcolor=INK_2)
    return fig


def plot_fund_profiles(r, n_countries=20):
    """Heatmaps of each fund's sector and country mix, next to the portfolio and the benchmark."""
    bt = r["benchmark"]["ticker"]
    cols = [("Portfolio", r["portfolio"]), (f"{bt} (benchmark)", r["benchmark"])]
    cols += [(p["label"], r["funds"][p["ticker"]]) for p in r["positions"]
             if p["type"] == "ETF" and p["ticker"] != bt]
    sectors = [s for s in r["portfolio"]["sectors"] if r["portfolio"]["sectors"][s] >= 0.05]
    countries = [c for c in r["portfolio"]["countries"] if c not in CATCH_ALL][:n_countries]
    fig, axes = plt.subplots(1, 2, figsize=(18, 0.36 * max(len(countries), len(sectors)) + 3),
                             layout="constrained", gridspec_kw={"width_ratios": [1, 1]})
    cmap = LinearSegmentedColormap.from_list("seq", SEQUENTIAL)
    for ax, dim, rows, title in [(axes[0], "sectors", sectors, "Sector mix of each fund (%)"),
                                 (axes[1], "countries", countries, f"Top {len(countries)} countries in each fund (%)")]:
        m = np.array([[c[dim].get(k, 0) for _, c in cols] for k in rows])
        vmax = m.max()
        ax.imshow(m, cmap=cmap, vmin=0, vmax=vmax, aspect="auto")
        for i in range(m.shape[0]):
            for j in range(m.shape[1]):
                v = m[i, j]
                ax.text(j, i, "·" if v < 0.05 else f"{v:.1f}", ha="center", va="center", fontsize=7.5,
                        color="white" if v > 0.55 * vmax else INK)
        ax.set_xticks(range(len(cols)), [c for c, _ in cols], rotation=35, ha="right")
        ax.set_yticks(range(len(rows)), rows)
        ax.axvline(1.5, color=SURFACE, lw=3)  # separate the two reference columns from the funds
        ax.tick_params(length=0, labelsize=9, labelcolor=INK_2)
        for sp_ in ax.spines.values():
            sp_.set_visible(False)
        ax.set_title(title, loc="left", color=INK, fontsize=12, weight="bold", pad=10)
    fig.set_facecolor(SURFACE)
    _suptitle(fig, "What each fund brings")
    return fig


def plot_overlap(r):
    """Share of holdings two funds have in common (sum of the smaller weight of each company)."""
    labels, m = r["overlap"]["labels"], np.array(r["overlap"]["matrix"], dtype=float)
    np.fill_diagonal(m, np.nan)
    n = len(labels)
    fig, ax = plt.subplots(figsize=(0.8 * n + 2.4, 0.8 * n + 1.6), layout="constrained")
    ax.imshow(m, cmap=LinearSegmentedColormap.from_list("seq", SEQUENTIAL), vmin=0, vmax=100)
    for i in range(n):
        for j in range(n):
            txt, color = ("—", MUTED) if i == j else (f"{m[i, j]:.0f}%", "white" if m[i, j] > 55 else INK)
            ax.text(j, i, txt, ha="center", va="center", fontsize=9, color=color)
    ax.set_xticks(range(n), labels, rotation=35, ha="right")
    ax.set_yticks(range(n), labels)
    ax.set_facecolor(SURFACE)
    fig.set_facecolor(SURFACE)
    ax.tick_params(length=0, labelsize=9, labelcolor=INK_2)
    for s in ax.spines.values():
        s.set_visible(False)
    ax.set_title("Fund overlap — % of holdings in common", loc="left", color=INK, fontsize=12, weight="bold", pad=10)
    return fig


def plot_concentration(r):
    """Cumulative weight of the largest N companies (log scale)."""
    bt, sp, sb = r["benchmark"]["ticker"], r["stats"]["portfolio"], r["stats"]["benchmark"]
    fig, ax = plt.subplots(figsize=(10, 4.8), layout="constrained")
    for key, color, name, stats in [("portfolio", PORTFOLIO_C, "Portfolio", sp), ("benchmark", BENCH_C, bt, sb)]:
        x, y = zip(*r["concentration"][key])
        ax.plot(x, y, color=color, lw=2,
                label=f"{name} — behaves like {stats['Effective # of companies']:.0f} equal-weight companies")
    ax.set_xscale("log")
    ax.xaxis.set_major_formatter(plt.FuncFormatter(lambda v, _: f"{v:,.0f}"))
    ax.set_ylim(0, 100)
    ax.set_xlim(1, None)
    for n in (10, 100):
        ax.axvline(n, color=BASELINE, lw=1)
    _style(ax, "Concentration: weight held by the largest N companies", xlabel="number of companies (log scale)")
    ax.grid(True, axis="y", color=GRID, lw=0.8)
    ax.set_ylabel("cumulative % of equity", color=MUTED, fontsize=9)
    _legend(ax, loc="lower right")
    return fig


def plot_top_holdings(r, n=50):
    """Top companies split into direct stake and exposure through funds, with benchmark weight."""
    t, bt = tables(r, n_holdings=n)["holdings"], r["benchmark"]["ticker"]
    y = np.arange(len(t))
    via_funds = t["Portfolio %"] - t["Direct %"]
    fig, ax = plt.subplots(figsize=(12, 0.28 * len(t) + 1.6), layout="constrained")
    ax.barh(y, via_funds, height=0.62, color=PORTFOLIO_C, label="Through funds", edgecolor=SURFACE, lw=1)
    ax.barh(y, t["Direct %"], left=via_funds, height=0.62, color=DIRECT_C, label="Direct stake",
            edgecolor=SURFACE, lw=1)
    ax.scatter(t[f"{bt} %"], y, marker="|", s=260, linewidths=2.5, color=BENCH_C, label=f"{bt} weight", zorder=3)
    for i, v in enumerate(t["Portfolio %"]):
        ax.text(v + 0.06, i, f"{v:.2f}%", va="center", fontsize=8, color=INK_2)
    ax.set_yticks(y, t["Company"])
    ax.invert_yaxis()
    _style(ax, f"Top {n} underlying companies")
    _legend(ax, loc="lower right")
    return fig


def plot_history(est, bench_row, snapshots=None, bt="Benchmark"):
    """Estimated exposure history (today's fund holdings × your past allocations) + saved snapshots."""
    metrics = ["Emerging markets %", "United States %", "Information Technology %",
               "Top 10 companies %", "Active share vs benchmark %", "Effective # of companies"]
    saved = pd.DataFrame({pd.to_datetime(d, format="%Y%m%d"): s["stats"]["portfolio"]
                          for d, s in (snapshots or {}).items() if "stats" in s}).T
    low = est["Coverage %"] < 90
    fig, axes = plt.subplots(2, 3, figsize=(15, 7), layout="constrained")
    for ax, m in zip(axes.flat, metrics):
        ax.plot(est.index, est[m], color=PORTFOLIO_C, lw=2, label="Portfolio (estimated)")
        ax.scatter(est.index[low.values], est[m][low.values], s=30, facecolor=SURFACE, edgecolor=PORTFOLIO_C, zorder=3,
                   label="<90% of equity mapped")
        if m in bench_row and not m.startswith("Active"):
            ax.axhline(bench_row[m], color=BENCH_C, lw=2, label=f"{bt} today")
        if m in saved:
            ax.scatter(saved.index, saved[m], s=40, color=INK, zorder=4, label="Saved snapshot")
        _style(ax, m.replace(" %", " (%)"), xlabel="")
        ax.grid(True, axis="y", color=GRID, lw=0.8)
        ax.grid(False, axis="x")
        loc = mdates.AutoDateLocator(maxticks=5)
        ax.xaxis.set_major_locator(loc)
        ax.xaxis.set_major_formatter(mdates.ConciseDateFormatter(loc))
    handles, labels = axes.flat[0].get_legend_handles_labels()
    fig.legend(handles, labels, loc="upper right", frameon=False, fontsize=9, labelcolor=INK_2, ncols=4)
    _suptitle(fig, "Exposure history — your past allocations × today's fund holdings")
    return fig
