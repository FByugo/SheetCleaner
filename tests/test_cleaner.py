"""Cleaning rules against a deliberately messy sheet, plus the ways a bad input must fail."""
import json

import pandas as pd
import pytest
from typer.testing import CliRunner

from sheet_cleaner.cli import app
from sheet_cleaner.core import Rules, clean, read_table, write_outputs

MESSY = (
    " Customer Name ,E-mail,Amount Paid,Qty,Signup Date\n"
    "  Ana   Lopez ,ANA@Example.com,\"$1,234.50\",3,2026-01-05\n"     # row 2: whitespace, caps email, money
    "Ben Ode,ben@example.com,(12.00),2,01/02/2026\n"                  # row 3: negative money, US date
    ",,,,\n"                                                          # row 4: empty
    "Cy Park,not-an-email,10,1,2026-02-01\n"                          # row 5: bad email
    "Di Hart,di@example.com,ten dollars,1,2026-02-02\n"               # row 6: bad money
    ",ed@example.com,5,1,2026-02-03\n"                                # row 7: name blank (required)
    "Ana L.,ana@example.com,99,1,2026-03-01\n"                        # row 8: duplicate email of row 2
    "Fay Moe,fay@example.com,€7,2.5,2026-03-02\n"                     # row 9: qty has a fraction
    "Gus Ray,gus@example.com,8,4,not a date\n"                        # row 10: bad date
)
RULES = {"rename": {"e_mail": "email", "amount_paid": "amount"}, "required": ["customer_name", "email"],
         "types": {"amount": "money", "qty": "int", "signup_date": "date", "email": "email"},
         "dedupe_on": ["email"]}


@pytest.fixture
def res(tmp_path):
    p = tmp_path / "messy.csv"; p.write_text(MESSY)
    return clean(read_table(p), Rules(**RULES))


def reason(res, row):
    return res.rejects.loc[res.rejects["row"] == row, "reason"].iloc[0]


def test_counts_add_up(res):
    assert res.rows_in == 9 and len(res.clean) == 2 and len(res.rejects) == 7


def test_clean_values(res):
    c = res.clean.set_index("source_row")
    assert list(res.clean.columns) == ["source_row", "customer_name", "email", "amount", "qty", "signup_date"]
    assert c.loc[2, "customer_name"] == "Ana Lopez" and c.loc[2, "email"] == "ana@example.com"
    assert c.loc[2, "amount"] == 1234.50 and c.loc[3, "amount"] == -12.0
    assert c.loc[2, "signup_date"] == "2026-01-05" and c.loc[3, "signup_date"] == "2026-01-02"


def test_every_reject_has_its_reason(res):
    assert reason(res, 4) == "empty row"
    assert "email='not-an-email' is not a valid email" in reason(res, 5)
    assert "not a valid money" in reason(res, 6)
    assert "customer_name is blank" in reason(res, 7)
    assert reason(res, 8) == "duplicate of row 2 on email"
    assert "qty='2.5' is not a valid int" in reason(res, 9)
    assert "not a valid date" in reason(res, 10)
    assert res.rejects.loc[res.rejects["row"] == 5, "customer_name"].iloc[0] == "Cy Park"  # original values kept


def test_change_log(res):
    ch = res.changes
    assert ((ch.row == 2) & (ch.column == "amount") & (ch.before == "$1,234.50") & (ch.after == "1234.5")).any()
    assert ((ch.row == 2) & (ch.column == "customer_name") & (ch.rule == "whitespace")).any()
    assert set(ch.row) <= {2, 3}  # rejected rows are not in the change log
    assert ("E-mail", "email") in res.header_changes


def test_dedupe_case_rule(tmp_path):
    p = tmp_path / "k.csv"; p.write_text("sku\nAB1\nab1\n")
    assert len(clean(read_table(p), Rules(dedupe_on=["sku"])).clean) == 1
    assert len(clean(read_table(p), Rules(dedupe_on=["sku"], dedupe_ignore_case=False)).clean) == 2


def test_mixed_currency_is_rejected(tmp_path):
    p = tmp_path / "m.csv"; p.write_text("amt\n$5\n$6\n€7\n8\n")
    out = clean(read_table(p), Rules(types={"amt": "money"}))
    assert list(out.clean["amt"]) == [5.0, 6.0, 8.0]
    assert "is in €, column is $" in out.rejects.loc[0, "reason"]
    out2 = clean(read_table(p), Rules(types={"amt": "money"}, currency="€"))
    assert len(out2.rejects) == 2 and list(out2.clean["amt"]) == [7.0, 8.0]


def test_dayfirst(tmp_path):
    p = tmp_path / "d.csv"; p.write_text("d\n01/02/2026\n")
    out = clean(read_table(p), Rules(types={"d": "date"}, dayfirst=True))
    assert out.clean.loc[0, "d"] == "2026-02-01"


def test_excel_and_latin1(tmp_path):
    x = tmp_path / "a.xlsx"
    pd.DataFrame({"Name ": [" a ", "b"], "N": ["1", "2"]}).to_excel(x, index=False)
    out = clean(read_table(x), Rules(types={"n": "int"}))
    assert list(out.clean["name"]) == ["a", "b"] and list(out.clean["n"]) == [1, 2]
    l1 = tmp_path / "l.csv"; l1.write_bytes("name\nJos\xe9\n".encode("latin-1"))
    assert read_table(l1).iloc[0, 0] == "José"


@pytest.mark.parametrize("rules,msg", [
    ({"types": {"nope": "int"}}, "does not have"),
    ({"types": {"qty": "integer"}}, "unknown types"),
    ({"colour": 1}, "unknown rule keys"),
])
def test_bad_rules_fail_loudly(tmp_path, rules, msg):
    p = tmp_path / "m.csv"; p.write_text(MESSY)
    rp = tmp_path / "r.json"; rp.write_text(json.dumps(rules))
    with pytest.raises(ValueError, match=msg):
        clean(read_table(p), Rules.load(rp))


def test_colliding_headers_fail(tmp_path):
    p = tmp_path / "c.csv"; p.write_text("Name,name \nx,y\n")
    with pytest.raises(ValueError, match="same name"):
        clean(read_table(p), Rules())


def test_lost_row_blocks_all_output(res, tmp_path):
    res.clean = res.clean.iloc[1:]  # simulate a bug that loses a row
    with pytest.raises(RuntimeError, match="do not add up"):
        write_outputs(res, tmp_path / "o", "x")
    assert not (tmp_path / "o").exists()


def test_outputs_and_cli(tmp_path):
    p = tmp_path / "messy.csv"; p.write_text(MESSY)
    rp = tmp_path / "rules.json"; rp.write_text(json.dumps(RULES))
    r = CliRunner()
    res = r.invoke(app, [str(p), "--rules", str(rp), "--out", str(tmp_path / "o")])
    assert res.exit_code == 0 and "9 rows in, 2 clean, 7 rejected" in res.output
    for f in ["clean.csv", "clean.xlsx", "rejects.csv", "changes.csv", "report.md"]:
        assert (tmp_path / "o" / f).exists()
    assert "| 8 | duplicate of row 2 on email |" in (tmp_path / "o" / "report.md").read_text()
    assert r.invoke(app, [str(p), "--rules", str(rp), "--out", str(tmp_path / "o2"), "--strict"]).exit_code == 1
    bad = tmp_path / "bad.json"; bad.write_text('{"types": {"zzz": "int"}}')
    assert r.invoke(app, [str(p), "--rules", str(bad), "--out", str(tmp_path / "o3")]).exit_code == 2
