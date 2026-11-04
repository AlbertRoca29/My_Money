"""A catalogue of popular UCITS ETFs among investors in Spain and the rest of Europe.

Ready-made specs to copy into config_local.py, so you don't have to look ISINs up:
    PRICE_SOURCES = {"My world ETF": etfs.price_source("IWDA")}       # backtest page (justETF, by ISIN)
    FUND_SOURCES = {"My world ETF": {**etfs.spec("IWDA"), "provider": "ishares", "id": "<fund id>"}}

Each entry: ticker -> (name, ISIN, issuer, strategy bucket). The bucket is the default "bucket" used by
the exposure page; any name works there, these are just the common ones (see BUCKETS).
Look-through holdings are only downloaded for iShares, Vanguard and Avantis funds (see lookthrough.py).
"""

# Strategy buckets in chart order (the exposure page stacks them in this order)
BUCKETS = ["Core index", "US", "Europe", "Japan & Pacific", "Emerging markets", "Small-cap",
           "Small-cap value", "Value", "Momentum", "Quality", "Minimum volatility", "Multi-factor",
           "Dividend", "ESG", "Sector & theme", "Real estate", "Bonds", "Money market",
           "Gold & commodities", "Direct stocks"]

ETFS = {
    # World / all-world
    "VWCE": ("Vanguard FTSE All-World (Acc)", "IE00BK5BQT80", "Vanguard", "Core index"),
    "VWRL": ("Vanguard FTSE All-World (Dist)", "IE00B3RBWM25", "Vanguard", "Core index"),
    "IWDA": ("iShares Core MSCI World (Acc)", "IE00B4L5Y983", "iShares", "Core index"),
    "SSAC": ("iShares MSCI ACWI (Acc)", "IE00B6R52259", "iShares", "Core index"),
    "SPYI": ("SPDR MSCI All Country World IMI (Acc)", "IE00B3YLTY66", "SPDR", "Core index"),
    "SPPW": ("SPDR MSCI World (Acc)", "IE00BFY0GT14", "SPDR", "Core index"),
    "XDWD": ("Xtrackers MSCI World 1C", "IE00BJ0KDQ92", "Xtrackers", "Core index"),
    "WEBN": ("Amundi Prime All Country World (Acc)", "IE0003XJA0J9", "Amundi", "Core index"),
    "AVWC": ("Avantis Global Equity (Acc)", "IE000RJECXS5", "Avantis", "Core index"),
    # United States
    "CSPX": ("iShares Core S&P 500 (Acc)", "IE00B5BMR087", "iShares", "US"),
    "VUAA": ("Vanguard S&P 500 (Acc)", "IE00BFMXXD54", "Vanguard", "US"),
    "VUSA": ("Vanguard S&P 500 (Dist)", "IE00B3XXRP09", "Vanguard", "US"),
    "SPY5": ("SPDR S&P 500 (Dist)", "IE00B6YX5C33", "SPDR", "US"),
    "XD9U": ("Xtrackers MSCI USA 1C", "IE00BJ0KDR00", "Xtrackers", "US"),
    "EQAC": ("Invesco EQQQ Nasdaq-100 (Acc)", "IE00BFZXGZ54", "Invesco", "US"),
    "CNDX": ("iShares Nasdaq 100 (Acc)", "IE00B53SZB19", "iShares", "US"),
    # Europe
    "SMEA": ("iShares Core MSCI Europe (Acc)", "IE00B4K48X80", "iShares", "Europe"),
    "VEUR": ("Vanguard FTSE Developed Europe (Dist)", "IE00B945VV12", "Vanguard", "Europe"),
    "MEUD": ("Amundi Core Stoxx Europe 600 (Acc)", "LU0908500753", "Amundi", "Europe"),
    "EXSA": ("iShares STOXX Europe 600 (DE)", "DE0002635307", "iShares", "Europe"),
    "CSX5": ("iShares Core EURO STOXX 50 (Acc)", "IE00B53L3W79", "iShares", "Europe"),
    "XESX": ("Xtrackers Euro Stoxx 50 1C", "LU0380865021", "Xtrackers", "Europe"),
    "LYXIB": ("Amundi IBEX 35 (Dist)", "FR0010251744", "Amundi", "Europe"),
    # Japan & Pacific
    "SJPA": ("iShares Core MSCI Japan IMI (Acc)", "IE00B4L5YX21", "iShares", "Japan & Pacific"),
    "VJPA": ("Vanguard FTSE Japan (Acc)", "IE00BFMXYX26", "Vanguard", "Japan & Pacific"),
    "CPXJ": ("iShares Core MSCI Pacific ex-Japan (Acc)", "IE00B52MJY50", "iShares", "Japan & Pacific"),
    # Emerging markets
    "EIMI": ("iShares Core MSCI EM IMI (Acc)", "IE00BKM4GZ66", "iShares", "Emerging markets"),
    "VFEA": ("Vanguard FTSE Emerging Markets (Acc)", "IE00BK5BR733", "Vanguard", "Emerging markets"),
    "VFEM": ("Vanguard FTSE Emerging Markets (Dist)", "IE00B3VVMM84", "Vanguard", "Emerging markets"),
    "XMME": ("Xtrackers MSCI Emerging Markets 1C", "IE00BTJRMP35", "Xtrackers", "Emerging markets"),
    "AEEM": ("Amundi MSCI Emerging Markets Swap (Acc)", "LU1681045370", "Amundi", "Emerging markets"),
    "AVEM": ("Avantis Emerging Markets Equity (Acc)", "IE000K975W13", "Avantis", "Emerging markets"),
    "NDIA": ("iShares MSCI India (Acc)", "IE00BZCQB185", "iShares", "Emerging markets"),
    # Small caps and factors
    "IUSN": ("iShares MSCI World Small Cap (Acc)", "IE00BF4RFH31", "iShares", "Small-cap"),
    "WSML": ("SPDR MSCI World Small Cap (Acc)", "IE00BCBJG560", "SPDR", "Small-cap"),
    "ZPRV": ("SPDR MSCI USA Small Cap Value Weighted (Acc)", "IE00BSPLC413", "SPDR", "Small-cap value"),
    "ZPRX": ("SPDR MSCI Europe Small Cap Value Weighted (Acc)", "IE00BSPLC298", "SPDR", "Small-cap value"),
    "AVWS": ("Avantis Global Small Cap Value (Acc)", "IE0003R87OG3", "Avantis", "Small-cap value"),
    "IWVL": ("iShares Edge MSCI World Value Factor (Acc)", "IE00BP3QZB59", "iShares", "Value"),
    "XDEV": ("Xtrackers MSCI World Value 1C", "IE00BL25JM42", "Xtrackers", "Value"),
    "IWMO": ("iShares Edge MSCI World Momentum Factor (Acc)", "IE00BP3QZ825", "iShares", "Momentum"),
    "XDEM": ("Xtrackers MSCI World Momentum 1C", "IE00BL25JP72", "Xtrackers", "Momentum"),
    "IWQU": ("iShares Edge MSCI World Quality Factor (Acc)", "IE00BP3QZ601", "iShares", "Quality"),
    "XDEQ": ("Xtrackers MSCI World Quality 1C", "IE00BL25JL35", "Xtrackers", "Quality"),
    "MVOL": ("iShares Edge MSCI World Minimum Volatility (Acc)", "IE00B8FHGS14", "iShares", "Minimum volatility"),
    "IFSW": ("iShares STOXX World Equity Multifactor (Acc)", "IE00BZ0PKT83", "iShares", "Multi-factor"),
    # Dividend and ESG
    "VHYL": ("Vanguard FTSE All-World High Dividend Yield (Dist)", "IE00B8GKDB10", "Vanguard", "Dividend"),
    "TDIV": ("VanEck Morningstar Developed Markets Dividend Leaders", "NL0011683594", "VanEck", "Dividend"),
    "SPYW": ("SPDR S&P Euro Dividend Aristocrats", "IE00B5M1WJ87", "SPDR", "Dividend"),
    "SUSW": ("iShares MSCI World SRI (Acc)", "IE00BYX2JD69", "iShares", "ESG"),
    # Sectors, themes and real estate
    "IUIT": ("iShares S&P 500 Information Technology Sector (Acc)", "IE00B3WJKG14", "iShares", "Sector & theme"),
    "INRG": ("iShares Global Clean Energy Transition (Dist)", "IE00B1XNHC34", "iShares", "Sector & theme"),
    "IWDP": ("iShares Developed Markets Property Yield (Dist)", "IE00B1FZS350", "iShares", "Real estate"),
    # Bonds and money market
    "AGGH": ("iShares Core Global Aggregate Bond EUR Hedged (Acc)", "IE00BDBRDM35", "iShares", "Bonds"),
    "VAGF": ("Vanguard Global Aggregate Bond EUR Hedged (Acc)", "IE00BG47KH54", "Vanguard", "Bonds"),
    "IBCI": ("iShares Euro Inflation Linked Govt Bond (Acc)", "IE00B0M62X26", "iShares", "Bonds"),
    "XEON": ("Xtrackers II EUR Overnight Rate Swap 1C", "LU0290358497", "Xtrackers", "Money market"),
    "CSH2": ("Amundi Smart Overnight Return (Acc)", "LU1190417599", "Amundi", "Money market"),
    # Gold
    "SGLD": ("Invesco Physical Gold ETC", "IE00B579F325", "Invesco", "Gold & commodities"),
    "EGLN": ("iShares Physical Gold ETC", "IE00B4ND3602", "iShares", "Gold & commodities"),
}


def price_source(ticker):
    """PRICE_SOURCES spec for a catalogue ETF (justETF daily EUR series, dividends included)."""
    return {"justetf": ETFS[ticker][1]}


def spec(ticker):
    """The catalogue fields of a FUND_SOURCES spec; add "provider" and "id" for the look-through."""
    return {"ticker": ticker, "bucket": ETFS[ticker][3]}
