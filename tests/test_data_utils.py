"""
Unit tests for the data-parsing helpers in data_utils.py.

Run with:
    pytest
"""

import pytest

from data_utils import discover_year_folders, fix_utm, load_year


@pytest.mark.parametrize(
    "raw, expected",
    [
        # Exact 3-digit blocks — the straightforward case.
        ("502.145", 502145.0),
        # The documented mistake-then-fix case from analysis.ipynb: a short
        # final block ("22") is decimal meters and must be padded with
        # trailing zeros, not treated as if it were already a full block —
        # naively stripping the dot would have produced 55722 instead of
        # the correct 557220.
        ("557.22", 557220.0),
        # Multiple thousand-separators.
        ("1.234.567", 1234567.0),
        # No separator at all.
        ("557220", 557220.0),
    ],
)
def test_fix_utm_handles_padded_and_short_blocks(raw, expected):
    assert fix_utm(raw) == expected


def test_discover_year_folders_filters_correctly(tmp_path):
    (tmp_path / "2019").mkdir()
    (tmp_path / "2019" / "zst9010_2019.csv").write_text("a;b\n1;2\n")
    (tmp_path / "2019" / "zst9011_2019.csv").write_text("a;b\n1;2\n")

    (tmp_path / "2023").mkdir()  # no CSVs inside -> must be excluded

    (tmp_path / "notayear").mkdir()  # not a 4-digit name -> must be excluded
    (tmp_path / "notayear" / "data.csv").write_text("a;b\n1;2\n")

    (tmp_path / "12345").mkdir()  # 5 digits -> must be excluded
    (tmp_path / "12345" / "data.csv").write_text("a;b\n1;2\n")

    result = discover_year_folders(str(tmp_path))

    assert result == [(2019, 2)]


def test_load_year_parses_semicolon_latin1_csv(tmp_path, monkeypatch):
    year_dir = tmp_path / "2019"
    year_dir.mkdir()
    (year_dir / "zst9010_2019.csv").write_text(
        "Zst;Wotag;Stunde;KFZ_R1;KFZ_R2;Lkw_R1;Lkw_R2;Datum\n"
        "9010;1;0;100;120;10;12;190101\n"
        "9010;1;1;90;110;9;11;190101\n",
        encoding="latin-1",
    )
    monkeypatch.chdir(tmp_path)

    df = load_year(2019)

    assert len(df) == 2
    assert df.iloc[0]['Zst'] == 9010
    assert df.iloc[0]['KFZ_R1'] == 100
    assert (df['year'] == 2019).all()
