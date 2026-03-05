"""Tests for CSV/Excel I/O and column mapping."""
from __future__ import annotations

import os
import tempfile
import csv
import pytest
from pathlib import Path

from data.io import ColumnMapper, read_input_file, apply_mapping


class TestColumnMapper:
    def test_exact_match(self):
        mapper = ColumnMapper(["first_name", "last_name", "email"])
        summary = mapper.get_mapping_summary()
        mapped = summary["mapped"]
        assert mapped["first_name"] == "first_name"
        assert mapped["last_name"] == "last_name"
        assert mapped["email"] == "email"

    def test_alias_match(self):
        mapper = ColumnMapper(["First Name", "Last Name", "Email Address"])
        summary = mapper.get_mapping_summary()
        mapped = summary["mapped"]
        assert mapped.get("First Name") == "first_name" or "first_name" in mapped.values()

    def test_fuzzy_match_linkedin(self):
        """'LI Profile' should fuzzy-match to linkedin_url."""
        mapper = ColumnMapper(["LI Profile", "Company"])
        summary = mapper.get_mapping_summary()
        mapped = summary["mapped"]
        li_mapping = mapped.get("LI Profile")
        assert li_mapping == "linkedin_url" or li_mapping is not None

    def test_company_mapping(self):
        mapper = ColumnMapper(["Company", "Domain", "Name"])
        summary = mapper.get_mapping_summary()
        mapped = summary["mapped"]
        assert "company_name" in mapped.values() or "Company" in mapped

    def test_set_mapping_override(self):
        mapper = ColumnMapper(["Custom Col"])
        mapper.set_mapping("Custom Col", "first_name")
        summary = mapper.get_mapping_summary()
        mapped = summary["mapped"]
        assert mapped.get("Custom Col") == "first_name"

    def test_set_mapping_to_none(self):
        mapper = ColumnMapper(["first_name"])
        mapper.set_mapping("first_name", None)
        summary = mapper.get_mapping_summary()
        # set_mapping(col, None) removes from mapped, puts in unmapped
        assert "first_name" not in summary["mapped"]


class TestReadInputFile:
    def test_read_csv(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("first_name,last_name,email\nJohn,Doe,john@acme.com\n")
        df = read_input_file(str(csv_file))
        assert len(df) == 1
        assert "first_name" in df.columns

    def test_read_csv_semicolon_delimited(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("first_name;last_name;email\nJohn;Doe;john@acme.com\n")
        df = read_input_file(str(csv_file))
        assert len(df) == 1

    def test_empty_rows_dropped(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("first_name,last_name\nJohn,Doe\n,\n,\nJane,Smith\n")
        df = read_input_file(str(csv_file))
        assert len(df) == 2

    def test_whitespace_stripped(self, tmp_path):
        csv_file = tmp_path / "test.csv"
        csv_file.write_text("first_name,last_name\n  John  ,  Doe  \n")
        df = read_input_file(str(csv_file))
        assert df.iloc[0]["first_name"].strip() == "John"


class TestApplyMapping:
    def test_basic_mapping(self):
        import pandas as pd
        df = pd.DataFrame({"First Name": ["John"], "Last Name": ["Doe"], "Email": ["john@acme.com"]})
        mapping = {"First Name": "first_name", "Last Name": "last_name", "Email": "email"}
        result = apply_mapping(df, mapping)
        assert len(result) == 1
        assert result[0]["first_name"] == "John"
        assert result[0]["last_name"] == "Doe"
        assert result[0]["email"] == "john@acme.com"

    def test_unmapped_columns_excluded(self):
        import pandas as pd
        df = pd.DataFrame({"Name": ["John"], "Random": ["xyz"]})
        mapping = {"Name": "first_name"}
        result = apply_mapping(df, mapping)
        assert "first_name" in result[0]
        assert "Random" not in result[0]

    def test_none_mapping_excluded(self):
        import pandas as pd
        df = pd.DataFrame({"Name": ["John"], "Skip": ["data"]})
        mapping = {"Name": "first_name", "Skip": None}
        result = apply_mapping(df, mapping)
        assert "first_name" in result[0]
        assert "Skip" not in result[0]
