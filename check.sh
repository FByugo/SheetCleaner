#!/usr/bin/env bash
# One command: tests, then the example run must reproduce its committed counts exactly.
set -u
cd "$(dirname "$0")"
[ -x .venv/bin/python ] || { python3 -m venv .venv && .venv/bin/pip install -q -e '.[test]'; } || exit 2
.venv/bin/python -m pytest -q tests || exit 1
got=$(.venv/bin/python -W error -m sheet_cleaner examples/orders_messy.csv --rules examples/rules.json --out "$(mktemp -d)") || exit 1
want="62 rows in, 40 clean, 22 rejected, 76 cells changed."
case "$got" in "$want"*) echo "check: all green ($want)";; *) echo "example drifted: $got" >&2; exit 1;; esac
