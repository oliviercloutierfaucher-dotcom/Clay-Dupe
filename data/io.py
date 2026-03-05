"""CSV/Excel import with fuzzy column mapping and export."""

from __future__ import annotations

import csv
import io
from pathlib import Path
from typing import Any, Optional, Union

import pandas as pd
from rapidfuzz import fuzz, process

from data.models import Company, Person

# ---------------------------------------------------------------------------
# Canonical column aliases (70+ aliases)
# ---------------------------------------------------------------------------

COLUMN_ALIASES: dict[str, list[str]] = {
    "first_name": [
        "first name", "firstname", "first", "fname", "given name",
        "contact first name", "person first name",
    ],
    "last_name": [
        "last name", "lastname", "last", "lname", "surname",
        "family name", "contact last name", "person last name",
    ],
    "full_name": [
        "full name", "fullname", "name", "contact name", "person name",
    ],
    "email": [
        "email", "email address", "e-mail", "email_address",
        "work email", "business email", "contact email",
    ],
    "title": [
        "title", "job title", "position", "role", "job role",
        "job_title", "designation",
    ],
    "company_name": [
        "company", "company name", "organization", "org", "employer",
        "company_name", "account name", "business name",
    ],
    "company_domain": [
        "domain", "company domain", "website", "company website",
        "url", "company_domain", "web", "company url",
    ],
    "linkedin_url": [
        "linkedin", "linkedin url", "linkedin profile", "linkedin_url",
        "li url", "profile url", "linkedin link",
    ],
    "phone": [
        "phone", "phone number", "telephone", "tel", "direct phone",
        "work phone", "business phone", "phone_number",
    ],
    "city": [
        "city", "town", "location city",
    ],
    "state": [
        "state", "province", "region", "state/province",
    ],
    "country": [
        "country", "nation", "country code", "country/region",
    ],
    "industry": [
        "industry", "sector", "vertical",
    ],
    "employee_count": [
        "employees", "employee count", "company size", "headcount",
        "num employees", "number of employees", "size",
    ],
    "seniority": [
        "seniority", "seniority level", "level",
    ],
    "department": [
        "department", "dept", "function",
    ],
}

# Pre-build a reverse lookup: lowercase alias -> canonical field name
_ALIAS_LOOKUP: dict[str, str] = {}
for _canonical, _aliases in COLUMN_ALIASES.items():
    for _alias in _aliases:
        _ALIAS_LOOKUP[_alias.lower()] = _canonical
    # Also map the canonical name itself
    _ALIAS_LOOKUP[_canonical.lower()] = _canonical


# ---------------------------------------------------------------------------
# Null-like sentinels to replace with NaN
# ---------------------------------------------------------------------------

_NULL_STRINGS = {"nan", "none", "n/a", "na", "-", "null", ""}


# ---------------------------------------------------------------------------
# ColumnMapper
# ---------------------------------------------------------------------------

class ColumnMapper:
    """Maps input column names to canonical field names via exact + fuzzy match."""

    MATCH_THRESHOLD = 70  # minimum fuzzy match score (0-100)

    def __init__(self, input_columns: list[str]) -> None:
        self.input_columns = list(input_columns)
        self.mapping: dict[str, str] = {}       # input_col -> canonical_field
        self.unmapped: list[str] = []
        self.match_scores: dict[str, int] = {}  # input_col -> match score
        self._auto_detect()

    # ---- internal ---------------------------------------------------------

    def _auto_detect(self) -> None:
        """Auto-detect column mappings using exact match then fuzzy matching."""
        # Track which canonical fields have already been claimed so we never
        # map two input columns to the same canonical field.
        claimed: set[str] = set()

        # Collect all alias strings for fuzzy matching (lowercase).
        all_alias_strings = list(_ALIAS_LOOKUP.keys())

        # Also include canonical field names as choices for fuzzy matching.
        canonical_names = list(COLUMN_ALIASES.keys())
        fuzzy_choices = list(set(all_alias_strings + canonical_names))

        for col in self.input_columns:
            col_lower = col.strip().lower()

            # 1. Exact match against alias lookup
            if col_lower in _ALIAS_LOOKUP:
                canonical = _ALIAS_LOOKUP[col_lower]
                if canonical not in claimed:
                    self.mapping[col] = canonical
                    self.match_scores[col] = 100
                    claimed.add(canonical)
                    continue

            # 2. Fuzzy match using rapidfuzz
            result = process.extractOne(
                col_lower,
                fuzzy_choices,
                scorer=fuzz.token_sort_ratio,
                score_cutoff=self.MATCH_THRESHOLD,
            )
            if result is not None:
                best_match, score, _ = result
                # Resolve the best match string to its canonical field
                canonical = _ALIAS_LOOKUP.get(best_match.lower(), best_match)
                # If the fuzzy match hit a canonical name directly, use it
                if canonical not in COLUMN_ALIASES and best_match in COLUMN_ALIASES:
                    canonical = best_match
                if canonical in COLUMN_ALIASES and canonical not in claimed:
                    self.mapping[col] = canonical
                    self.match_scores[col] = int(score)
                    claimed.add(canonical)
                    continue

            # No match found
            self.unmapped.append(col)

    # ---- public API -------------------------------------------------------

    def set_mapping(self, input_col: str, canonical_field: Optional[str]) -> None:
        """Manual override. Set *canonical_field* to ``None`` to unmap."""
        # Remove any previous mapping for this input column
        if input_col in self.mapping:
            del self.mapping[input_col]
            self.match_scores.pop(input_col, None)
        if input_col in self.unmapped:
            self.unmapped.remove(input_col)

        if canonical_field is None:
            self.unmapped.append(input_col)
            return

        # If another input column already maps to this canonical field, evict it
        for existing_col, existing_canon in list(self.mapping.items()):
            if existing_canon == canonical_field and existing_col != input_col:
                del self.mapping[existing_col]
                self.match_scores.pop(existing_col, None)
                if existing_col not in self.unmapped:
                    self.unmapped.append(existing_col)

        self.mapping[input_col] = canonical_field
        self.match_scores[input_col] = 100  # manual override = perfect score

    def get_mapping_summary(self) -> dict[str, Any]:
        """Return a summary of the current mapping state."""
        total = len(self.input_columns)
        mapped_count = len(self.mapping)
        coverage = (mapped_count / total * 100.0) if total > 0 else 0.0
        return {
            "mapped": dict(self.mapping),
            "unmapped": list(self.unmapped),
            "scores": dict(self.match_scores),
            "coverage": round(coverage, 1),
        }

    def validate(self) -> dict[str, Any]:
        """Check minimum requirements for enrichment.

        Need (first_name OR full_name) AND (company_name OR company_domain).
        Returns ``{valid, missing, warnings}``.
        """
        mapped_fields = set(self.mapping.values())

        missing: list[str] = []
        warnings: list[str] = []

        has_name = bool({"first_name", "full_name"} & mapped_fields)
        has_company = bool({"company_name", "company_domain"} & mapped_fields)

        if not has_name:
            missing.append("first_name or full_name")
        if not has_company:
            missing.append("company_name or company_domain")

        # Helpful warnings
        if "first_name" in mapped_fields and "last_name" not in mapped_fields:
            warnings.append("first_name mapped without last_name — results may be less accurate")
        if "company_name" in mapped_fields and "company_domain" not in mapped_fields:
            warnings.append("company_name mapped without company_domain — domain lookup will be needed")
        if "email" not in mapped_fields:
            warnings.append("email not mapped — email enrichment will run for all rows")
        if "linkedin_url" not in mapped_fields:
            warnings.append("linkedin_url not mapped — LinkedIn enrichment may be limited")

        return {
            "valid": len(missing) == 0,
            "missing": missing,
            "warnings": warnings,
        }


# ---------------------------------------------------------------------------
# read_input_file
# ---------------------------------------------------------------------------

def read_input_file(
    file_path: Union[str, Path, io.BytesIO],
    filename: str = "",
) -> pd.DataFrame:
    """Read CSV or Excel file into a DataFrame.

    Handles messy data: auto-detects delimiter for CSVs, strips whitespace,
    replaces null-like strings, and drops empty rows.

    Parameters
    ----------
    file_path : str, Path, or BytesIO
        Local path or in-memory buffer (e.g. from Streamlit ``file_uploader``).
    filename : str
        Original filename hint (used when *file_path* is a BytesIO).
    """
    # Determine extension
    if isinstance(file_path, io.BytesIO):
        ext = Path(filename).suffix.lower() if filename else ""
    else:
        file_path = Path(file_path)
        ext = file_path.suffix.lower()

    # Read into DataFrame
    if ext in (".xlsx", ".xls"):
        df = pd.read_excel(
            file_path,
            dtype=str,
            engine="openpyxl" if ext == ".xlsx" else None,
        )
    else:
        # CSV (default)
        raw: Union[str, bytes]
        if isinstance(file_path, io.BytesIO):
            raw = file_path.read()
            file_path.seek(0)  # reset for potential re-read
            if isinstance(raw, bytes):
                raw = raw.decode("utf-8-sig")
        else:
            with open(file_path, "r", encoding="utf-8-sig") as fh:
                raw = fh.read()

        # Auto-detect delimiter
        delimiter = ","
        try:
            sample = raw[:8192]
            dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
            delimiter = dialect.delimiter
        except csv.Error:
            pass

        df = pd.read_csv(
            io.StringIO(raw),
            sep=delimiter,
            dtype=str,
            engine="python",
        )

    # --- Clean up (single pass per column) -----------------------------------

    # Strip whitespace from column names
    df.columns = [str(c).strip() for c in df.columns]

    # Strip whitespace and replace null-like strings in one pass per column
    for col in df.columns:
        series = df[col]
        if series.dtype == object:
            # .str accessor handles NaN gracefully (returns NaN)
            stripped = series.str.strip()
            df[col] = stripped.where(
                ~stripped.str.lower().isin(_NULL_STRINGS), other=pd.NA,
            )

    # Drop fully empty rows
    df = df.dropna(how="all")

    # Reset index
    df = df.reset_index(drop=True)

    return df


# ---------------------------------------------------------------------------
# apply_mapping
# ---------------------------------------------------------------------------

def deduplicate_rows(
    records: list[dict],
    key_fields: tuple[str, ...] = ("first_name", "last_name", "company_domain"),
) -> tuple[list[dict], int]:
    """Remove duplicate rows based on key fields.

    Returns (deduplicated_records, duplicate_count).
    Keys are case-insensitive.
    """
    seen: set[tuple[str, ...]] = set()
    unique: list[dict] = []
    dupes = 0
    for record in records:
        key = tuple(
            (record.get(f) or "").strip().lower()
            for f in key_fields
        )
        # Skip if all key fields are empty (would match all empty rows)
        if all(k == "" for k in key):
            unique.append(record)
            continue
        if key in seen:
            dupes += 1
            continue
        seen.add(key)
        unique.append(record)
    return unique, dupes


# ---------------------------------------------------------------------------
# apply_mapping
# ---------------------------------------------------------------------------

def apply_mapping(df: pd.DataFrame, mapping: dict[str, str]) -> list[dict[str, str]]:
    """Apply column mapping to a DataFrame.

    Parameters
    ----------
    df : DataFrame
        Raw input data.
    mapping : dict
        ``{input_column_name: canonical_field_name}``.

    Returns
    -------
    list[dict]
        One dict per non-empty row with canonical field names as keys.
        Empty string / NaN values are skipped.  Entirely empty rows are omitted.
    """
    records: list[dict[str, str]] = []

    for _, row in df.iterrows():
        canonical_row: dict[str, str] = {}
        for input_col, canonical_field in mapping.items():
            if input_col not in df.columns:
                continue
            value = row.get(input_col)
            if pd.isna(value):
                continue
            value = str(value).strip()
            if value == "" or value.lower() in _NULL_STRINGS:
                continue
            canonical_row[canonical_field] = value

        if canonical_row:
            records.append(canonical_row)

    return records


# ---------------------------------------------------------------------------
# export_results
# ---------------------------------------------------------------------------

def export_results(
    people: list[Any],
    companies: dict[str, Any],
    enrichment_meta: dict[str, dict[str, Any]],
    output_path: Union[str, Path],
    format: str = "csv",
) -> Path:
    """Export enriched results to CSV or Excel.

    Parameters
    ----------
    people : list
        ``Person`` objects or dicts with Person-like keys.
    companies : dict
        ``company_id -> Company`` object or dict.
    enrichment_meta : dict
        ``person_id -> metadata dict`` with keys like source_provider,
        confidence_score, verification_status, etc.
    output_path : str or Path
        Destination file path (extension may be overridden by *format*).
    format : str
        ``"csv"`` or ``"excel"`` / ``"xlsx"``.

    Returns
    -------
    Path
        The path to the written file.
    """
    output_path = Path(output_path)

    rows: list[dict[str, Any]] = []

    for person_obj in people:
        # Normalise to dict
        if isinstance(person_obj, Person):
            p = person_obj.model_dump()
        elif hasattr(person_obj, "__dict__"):
            p = vars(person_obj)
        else:
            p = dict(person_obj)

        person_id = p.get("id", "")
        company_id = p.get("company_id", "")

        # Resolve company
        c: dict[str, Any] = {}
        if company_id and company_id in companies:
            company_obj = companies[company_id]
            if isinstance(company_obj, Company):
                c = company_obj.model_dump()
            elif hasattr(company_obj, "__dict__"):
                c = vars(company_obj)
            else:
                c = dict(company_obj)

        # Resolve enrichment metadata
        meta = enrichment_meta.get(person_id, {})
        if not isinstance(meta, dict):
            if hasattr(meta, "__dict__"):
                meta = vars(meta)
            else:
                meta = dict(meta)

        row: dict[str, Any] = {
            # Person fields
            "First Name": p.get("first_name", ""),
            "Last Name": p.get("last_name", ""),
            "Full Name": p.get("full_name", ""),
            "Title": p.get("title", ""),
            "Seniority": p.get("seniority", ""),
            "Department": p.get("department", ""),
            "Email": p.get("email", ""),
            "Email Status": p.get("email_status", ""),
            "Personal Email": p.get("personal_email", ""),
            "Phone": p.get("phone", ""),
            "Mobile Phone": p.get("mobile_phone", ""),
            "LinkedIn URL": p.get("linkedin_url", ""),
            # Company fields
            "Company Name": p.get("company_name", "") or c.get("name", ""),
            "Company Domain": p.get("company_domain", "") or c.get("domain", ""),
            "Industry": c.get("industry", ""),
            "Employee Count": c.get("employee_count", ""),
            "Revenue (USD)": c.get("revenue_usd", ""),
            "EBITDA (USD)": c.get("ebitda_usd", ""),
            "Company LinkedIn": c.get("linkedin_url", ""),
            "Company Phone": c.get("phone", ""),
            # Location (prefer person-level, fall back to company)
            "City": p.get("city", "") or c.get("city", ""),
            "State": p.get("state", "") or c.get("state", ""),
            "Country": p.get("country", "") or c.get("country", ""),
            # Metadata (prefixed with _)
            "_Source Provider": meta.get("source_provider", ""),
            "_Confidence Score": meta.get("confidence_score", ""),
            "_Verification Status": meta.get("verification_status", ""),
            "_Waterfall Position": meta.get("waterfall_position", ""),
            "_Found At": meta.get("found_at", ""),
            "_Cost Credits": meta.get("cost_credits", ""),
            "_From Cache": meta.get("from_cache", ""),
        }

        # Normalise enum values to their string representation
        for key, val in row.items():
            if hasattr(val, "value"):
                row[key] = val.value
            if val is None:
                row[key] = ""

        rows.append(row)

    df = pd.DataFrame(rows)

    # Write output
    if format.lower() in ("excel", "xlsx"):
        if output_path.suffix.lower() not in (".xlsx", ".xls"):
            output_path = output_path.with_suffix(".xlsx")
        df.to_excel(output_path, index=False, engine="openpyxl")
    else:
        if output_path.suffix.lower() != ".csv":
            output_path = output_path.with_suffix(".csv")
        df.to_csv(output_path, index=False)

    return output_path
