"""Merge spellings of the same name in your Movements ("zara shrt", "ZARA" -> "Zara"), from a file you edit by hand.

This is not part of the running app. List the merges in name_merges.json (next to this file, git-ignored):

    {
      "expense": {"Zara": ["zara shrt", "T-SHIRT 👕"], "Mercadona": ["mercadona 2"]},
      "income":  {"Salary": ["salario"]}
    }

Each key is the name to keep, the list holds the spellings that become it. A listed spelling also catches names
that only differ in case, accents, punctuation or emoji, and so does the name to keep ("Zara": [] is fine). Then:

    .venv/bin/python tidy_names.py             show what would change
    .venv/bin/python tidy_names.py --go        change the Name cells in the sheet
    .venv/bin/python tidy_names.py --suggest   print names that look alike, as a starting point for the file

(name_merges.example.json shows the format; copy it to name_merges.json.)
"""
import difflib
import json
import sys
import unicodedata
from collections import Counter
from pathlib import Path

from gastos import db

FILE = Path(__file__).parent / "name_merges.json"


def norm(s):
    s = unicodedata.normalize("NFD", s)
    return "".join(c for c in s.lower() if c.isalnum())


def names(entries, kind):
    return Counter(e["name"] for e in entries if e["kind"] == kind)


def suggest(entries):
    out = {}
    for kind in ("expense", "income"):
        counts = names(entries, kind)
        left = sorted(counts, key=lambda n: -counts[n])
        groups = {}
        while left:
            keep = left.pop(0)
            like = [n for n in left if norm(n) == norm(keep) or (
                min(len(norm(n)), len(norm(keep))) >= 5 and difflib.SequenceMatcher(None, norm(n), norm(keep)).ratio() >= 0.85)]
            if like:
                groups[keep] = like
                left = [n for n in left if n not in like]
        out[kind] = groups
    return out


def main():
    entries = db.all_entries()
    if "--suggest" in sys.argv:
        print(json.dumps(suggest(entries), indent=2, ensure_ascii=False))
        return
    if not FILE.exists():
        sys.exit(f"{FILE.name} not found: copy name_merges.example.json to it and list your merges.")
    merges = json.loads(FILE.read_text())
    go = "--go" in sys.argv
    plan = make_plan(entries, merges)
    for kind, old, keep, n in plan:
        print(f"{kind:8} {', '.join(old)}  ->  {keep}   ({n} entries)")
        if go:
            db.rename(kind, old, keep)
    total = sum(n for *_, n in plan)
    print(f"\n{total} entries {'renamed' if go else 'would be renamed; run with --go to do it'}.")


def make_plan(entries, merges):
    """[(kind, names to change, name to keep, entries affected)]. The kept name's own case/accent variants join too."""
    plan = []
    for kind in ("expense", "income"):
        counts = names(entries, kind)
        for keep, spellings in (merges.get(kind) or {}).items():
            wanted = {norm(s) for s in [keep, *spellings]}
            old = [n for n in counts if n != keep and norm(n) in wanted]
            if old:
                plan.append((kind, old, keep, sum(counts[o] for o in old)))
    return plan


if __name__ == "__main__":
    main()
