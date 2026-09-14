# My Money

Work in progress: scripts to keep track of my savings and investments.

- `mwr.py`: money-weighted (and time-weighted) return of the portfolio, treating net savings as the money put in.
- `lookthrough.py`: look-through exposure of a set of ETFs (countries, sectors, companies, costs…) vs a benchmark.
- `backtest.py`: how a fixed fund mix would have done against a benchmark.

The portfolio is a folder of snapshots, `portfolios/YYYYMMDD.json` (`{category: {asset: amount}}`), and
`cashflows.csv` holds the net savings per day (`date,net`). Both are personal and git-ignored.

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
.venv/bin/python mwr.py
```
