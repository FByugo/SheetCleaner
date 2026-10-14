cd "$(dirname "$0")/.."; source docs/_say.sh; export PATH="$PWD/.venv/bin:$PATH"; clear
note "a messy order sheet: spaces, caps, \$ and € mixed, three date formats, a blank row"
run "head -5 examples/orders_messy.csv"
run "python -m sheet_cleaner examples/orders_messy.csv --rules examples/rules.json --out /tmp/out"
run "sed -n '3,4p;18,30p' /tmp/out/report.md"
run "head -4 /tmp/out/clean.csv"
