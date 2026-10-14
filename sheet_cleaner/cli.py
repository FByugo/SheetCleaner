"""Command line entry point: `sheet-cleaner messy.csv --rules rules.json --out out`."""
from __future__ import annotations

import logging
from pathlib import Path

import typer

from .core import Rules, clean, read_table, write_outputs

app = typer.Typer(add_completion=False, help="Clean a messy spreadsheet and write down every change.")


@app.command()
def main(
    source: Path = typer.Argument(..., exists=True, readable=True, help="A .csv or .xlsx file."),
    rules: Path = typer.Option(None, "--rules", "-r", exists=True, help="JSON rules file (see examples/rules.json)."),
    out: Path = typer.Option(Path("out"), "--out", "-o", help="Folder for clean.csv, clean.xlsx, rejects.csv, changes.csv, report.md."),
    sheet: str = typer.Option("0", help="Excel sheet name or index."),
    strict: bool = typer.Option(False, help="Exit with code 1 if any row was rejected."),
    verbose: bool = typer.Option(False, "--verbose", "-v"),
):
    """Clean SOURCE by the rules and save the results."""
    logging.basicConfig(level=logging.INFO if verbose else logging.WARNING, format="%(levelname)s %(message)s")
    try:
        df = read_table(source, int(sheet) if sheet.isdigit() else sheet)
        res = clean(df, Rules.load(rules))
    except ValueError as e:
        typer.echo(f"error: {e}", err=True)
        raise typer.Exit(2)
    c = write_outputs(res, out, source.name)
    typer.echo(f"{c['rows_in']} rows in, {c['clean']} clean, {c['rejected']} rejected, "
               f"{c['cells_changed']} cells changed. Report: {out / 'report.md'}")
    if strict and c["rejected"]:
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
