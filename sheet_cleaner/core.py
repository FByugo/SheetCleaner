"""Clean messy CSV and Excel files by a small set of rules, and write down every change.

Nothing is dropped silently. A row that cannot be cleaned goes to rejects.csv with the reason and
its original spreadsheet row number, and every cell that was changed is listed in changes.csv.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass, field
from pathlib import Path

import pandas as pd

log = logging.getLogger("sheet_cleaner")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[a-z]{2,}$", re.I)
MONEY_RE = re.compile(r"^\(?-?\s*[$€£]?\s*-?[\d,]*\.?\d+\s*\)?$")
TYPES = ("text", "int", "number", "money", "date", "email")


@dataclass
class Rules:
    rename: dict = field(default_factory=dict)     # header after normalising -> new name
    required: list = field(default_factory=list)   # columns that must not be blank
    types: dict = field(default_factory=dict)      # column -> one of TYPES
    dedupe_on: list = field(default_factory=list)  # columns that together identify a row
    dayfirst: bool = False                         # 03/04/2026 = 3 April instead of 4 March
    currency: str | None = None                    # expected symbol for money columns, e.g. "$"; others are rejected
    dedupe_ignore_case: bool = True                # "Ana" and "ANA" count as the same; turn off for codes like SKUs

    @classmethod
    def load(cls, path: Path | None) -> "Rules":
        if path is None:
            return cls()
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        unknown = set(data) - set(cls.__dataclass_fields__)
        if unknown:
            raise ValueError(f"unknown rule keys: {sorted(unknown)}")
        rules = cls(**data)
        bad = {c: t for c, t in rules.types.items() if t not in TYPES}
        if bad:
            raise ValueError(f"unknown types {bad}; allowed: {TYPES}")
        return rules


@dataclass
class Result:
    clean: pd.DataFrame
    rejects: pd.DataFrame
    changes: pd.DataFrame
    header_changes: list
    rows_in: int


def read_table(path: Path, sheet: str | int = 0) -> pd.DataFrame:
    """Read a CSV (UTF-8, falling back to Latin-1) or one Excel sheet, every cell as text."""
    path = Path(path)
    if path.suffix.lower() in (".xlsx", ".xlsm", ".xls"):
        return pd.read_excel(path, sheet_name=sheet, dtype=str, keep_default_na=False)
    for enc in ("utf-8-sig", "latin-1"):
        try:
            return pd.read_csv(path, dtype=str, keep_default_na=False, encoding=enc)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"could not decode {path}")


def norm_header(h: str) -> str:
    h = re.sub(r"[^0-9a-zA-Z]+", "_", str(h).strip()).strip("_").lower()
    return h or "unnamed"


def to_money(v: str):
    s = v.replace(" ", "")
    if not MONEY_RE.match(s):
        raise ValueError("not a money amount")
    neg = s.startswith("(") and s.endswith(")") or "-" in s
    n = float(re.sub(r"[^\d.]", "", s))
    return round(-n if neg else n, 2)


def to_int(v: str):
    f = float(v.replace(",", ""))
    if f != int(f):
        raise ValueError("has a fraction")
    return int(f)


def to_number(v: str):
    return float(v.replace(",", ""))


def to_date(v: str, dayfirst: bool):
    d = pd.to_datetime(v, dayfirst=dayfirst, errors="raise")
    return d.strftime("%Y-%m-%d")


def to_email(v: str):
    e = v.strip().lower()
    if not EMAIL_RE.match(e):
        raise ValueError("not an email address")
    return e


def clean(df: pd.DataFrame, rules: Rules) -> Result:
    rows_in = len(df)
    changes, rejects = [], []

    # headers
    header_changes, cols = [], []
    for h in df.columns:
        new = rules.rename.get(norm_header(h), norm_header(h))
        if new != h:
            header_changes.append((str(h), new))
        cols.append(new)
    dupes = {c for c in cols if cols.count(c) > 1}
    if dupes:
        raise ValueError(f"two columns end up with the same name: {sorted(dupes)}")
    df = df.copy()
    df.columns = cols
    missing = [c for c in set(rules.required) | set(rules.types) | set(rules.dedupe_on) if c not in df.columns]
    if missing:
        raise ValueError(f"rules name columns this file does not have: {sorted(missing)}; it has {cols}")

    # sheet row number = position + 2 (row 1 is the header)
    df.insert(0, "_row", range(2, rows_in + 2))
    original = df.copy()

    # whitespace
    for c in cols:
        new = df[c].astype(str).str.strip().str.replace(r"\s+", " ", regex=True)
        for i in df.index[new != df[c]]:
            changes.append((int(df.at[i, "_row"]), c, df.at[i, c], new[i], "whitespace"))
        df[c] = new

    # fully empty rows are dropped and listed
    empty = df[cols].eq("").all(axis=1)
    for i in df.index[empty]:
        rejects.append((int(df.at[i, "_row"]), "empty row"))
    df = df[~empty]

    reasons: dict[int, list] = {}
    # required
    for c in rules.required:
        for i in df.index[df[c] == ""]:
            reasons.setdefault(i, []).append(f"{c} is blank")

    # types
    conv = {"int": to_int, "number": to_number, "money": to_money, "email": to_email,
            "date": lambda v: to_date(v, rules.dayfirst), "text": lambda v: v}
    for c, t in rules.types.items():
        if t == "money":
            # mixed currencies in one column would be added together later with no warning, so they are rejected:
            # against the declared symbol if there is one, otherwise against the column's most common symbol
            syms = df[c].str.extract(r"([$€£])", expand=False)
            expected = rules.currency or (syms.mode().iloc[0] if syms.notna().any() else None)
            if expected:
                for i in df.index[syms.notna() & (syms != expected)]:
                    reasons.setdefault(i, []).append(f"{c}={df.at[i, c]!r} is in {syms[i]}, column is {expected}")
        out = []
        for i, v in df[c].items():
            if v == "":
                out.append(v)
                continue
            try:
                nv = conv[t](v)
            except (ValueError, TypeError, OverflowError, pd.errors.ParserError) as e:
                reasons.setdefault(i, []).append(f"{c}={v!r} is not a valid {t}")
                out.append(v)
                continue
            if str(nv) != v:
                changes.append((int(df.at[i, "_row"]), c, v, str(nv), t))
            out.append(nv)
        df[c] = out

    for i, rs in reasons.items():
        rejects.append((int(df.at[i, "_row"]), "; ".join(rs)))
    df = df.drop(index=list(reasons))

    # duplicates: first one wins, later ones are rejected and point back to it
    if rules.dedupe_on:
        key = df[rules.dedupe_on].astype(str).apply(lambda r: "\x1f".join(r), axis=1)
        if rules.dedupe_ignore_case:
            key = key.str.lower()
        first_row = {}
        drop = []
        for i, k in key.items():
            if k in first_row:
                rejects.append((int(df.at[i, "_row"]), f"duplicate of row {first_row[k]} on {', '.join(rules.dedupe_on)}"))
                drop.append(i)
            else:
                first_row[k] = int(df.at[i, "_row"])
        df = df.drop(index=drop)

    rej = pd.DataFrame(rejects, columns=["row", "reason"]).sort_values("row", kind="stable")
    rej = rej.merge(original.rename(columns={"_row": "row"}), on="row", how="left")
    ch = pd.DataFrame(changes, columns=["row", "column", "before", "after", "rule"])
    # the change log only keeps rows that survived; a rejected row's edits are moot
    ch = ch[ch["row"].isin(df["_row"])].reset_index(drop=True)
    return Result(clean=df.rename(columns={"_row": "source_row"}).reset_index(drop=True),
                  rejects=rej.reset_index(drop=True), changes=ch, header_changes=header_changes, rows_in=rows_in)


def write_outputs(res: Result, out_dir: Path, source: str) -> dict:
    counts = {"rows_in": res.rows_in, "clean": len(res.clean), "rejected": len(res.rejects),
              "cells_changed": len(res.changes)}
    if counts["clean"] + counts["rejected"] != counts["rows_in"] or res.rejects["row"].duplicated().any():
        # checked before anything is written, and not with assert (python -O would skip it)
        raise RuntimeError(f"rows do not add up, nothing written: {counts}")
    out_dir.mkdir(parents=True, exist_ok=True)
    res.clean.to_csv(out_dir / "clean.csv", index=False)
    res.clean.to_excel(out_dir / "clean.xlsx", index=False)
    res.rejects.to_csv(out_dir / "rejects.csv", index=False)
    res.changes.to_csv(out_dir / "changes.csv", index=False)
    lines = [f"# Cleaning report for {source}", "",
             f"{counts['rows_in']} rows in, {counts['clean']} clean, {counts['rejected']} rejected, "
             f"{counts['cells_changed']} cells changed.", ""]
    if res.header_changes:
        lines += ["## Column names", ""] + [f"- `{a}` became `{b}`" for a, b in res.header_changes] + [""]
    if len(res.changes):
        lines += ["## Changes by rule", ""]
        lines += [f"- {r}: {n}" for r, n in res.changes["rule"].value_counts().items()] + [""]
    if len(res.rejects):
        lines += ["## Rejected rows", "", "| row | reason |", "|---|---|"]
        lines += [f"| {r.row} | {r.reason} |" for r in res.rejects.itertuples()] + [""]
    lines += ["Every changed cell is listed in changes.csv with its row, the old value and the new one."]
    (out_dir / "report.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return counts
