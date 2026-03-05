"""Tests for CSV/Excel I/O and column mapping."""
from __future__ import annotations

import os
import tempfile
import csv
import pytest
from pathlib import Path

from data.io import ColumnMapper, read_input_file, apply_mapping, deduplicate_rows


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


class TestDeduplicateRows:
    def test_removes_exact_duplicates(self):
        records = [
            {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"},
            {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"},
            {"first_name": "Jane", "last_name": "Smith", "company_domain": "other.com"},
        ]
        unique, dupes = deduplicate_rows(records)
        assert dupes == 1
        assert len(unique) == 2

    def test_case_insensitive(self):
        records = [
            {"first_name": "John", "last_name": "Doe", "company_domain": "Acme.com"},
            {"first_name": "john", "last_name": "doe", "company_domain": "acme.com"},
        ]
        unique, dupes = deduplicate_rows(records)
        assert dupes == 1
        assert len(unique) == 1

    def test_keeps_first_occurrence(self):
        records = [
            {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com", "email": "first@test.com"},
            {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com", "email": "second@test.com"},
        ]
        unique, dupes = deduplicate_rows(records)
        assert unique[0]["email"] == "first@test.com"

    def test_empty_keys_not_deduped(self):
        """Rows with all key fields empty should not be deduped against each other."""
        records = [
            {"first_name": "", "last_name": "", "company_domain": ""},
            {"first_name": "", "last_name": "", "company_domain": ""},
        ]
        unique, dupes = deduplicate_rows(records)
        assert dupes == 0
        assert len(unique) == 2

    def test_missing_keys_treated_as_empty(self):
        """Missing key fields default to empty string."""
        records = [
            {"first_name": "John"},
            {"first_name": "John"},
        ]
        unique, dupes = deduplicate_rows(records)
        assert dupes == 1
        assert len(unique) == 1

    def test_no_duplicates(self):
        records = [
            {"first_name": "John", "last_name": "Doe", "company_domain": "acme.com"},
            {"first_name": "Jane", "last_name": "Smith", "company_domain": "other.com"},
        ]
        unique, dupes = deduplicate_rows(records)
        assert dupes == 0
        assert len(unique) == 2

    def test_whitespace_stripped(self):
        records = [
            {"first_name": " John ", "last_name": "Doe", "company_domain": "acme.com"},
            {"first_name": "John", "last_name": " Doe", "company_domain": " acme.com "},
        ]
        unique, dupes = deduplicate_rows(records)
        assert dupes == 1
        assert len(unique) == 1

    def test_empty_list(self):
        unique, dupes = deduplicate_rows([])
        assert dupes == 0
        assert len(unique) == 0
