from __future__ import annotations

import re
from io import StringIO
from typing import Iterable

import pandas as pd

MASTER_LABELS = {
    "registration no": "registration_no",
    "reference no": "reference_no",
    "registered for sales tax": "registered_for_sales_tax_raw",
    "name": "legal_name_fbr",
    "category": "taxpayer_category",
    "pp/reg/inc no.": "pp_reg_inc_no",
    "pp/reg/inc no": "pp_reg_inc_no",
    "email": "masked_email_fbr",
    "cell": "masked_cell_fbr",
    "address": "registered_address",
    "registered on": "registered_on",
    "tax office": "tax_office",
    "registration status": "registration_status_raw",
}


def clean(value) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    if not text or text.lower() in {"nan", "none"}:
        return None
    return text


def _flatten_columns(columns: Iterable) -> list[str]:
    out = []
    for col in columns:
        if isinstance(col, tuple):
            parts = [clean(x) for x in col if clean(x)]
            out.append(" ".join(dict.fromkeys(parts)))
        else:
            out.append(clean(col) or "")
    return out


def _extract_pairs_from_table(df: pd.DataFrame) -> dict:
    result: dict[str, str] = {}
    values = df.astype(object).where(pd.notna(df), None).values.tolist()
    for row in values:
        row_clean = [clean(x) for x in row]
        for i, value in enumerate(row_clean):
            if not value:
                continue
            key = MASTER_LABELS.get(value.lower().rstrip(":"))
            if not key:
                continue
            candidate = None
            for next_value in row_clean[i + 1 :]:
                if next_value:
                    candidate = next_value
                    break
            if candidate:
                result[key] = candidate
    return result


def _parse_master_from_tables(tables: list[pd.DataFrame]) -> dict:
    best: dict = {}
    for df in tables:
        text = " ".join(clean(x) or "" for x in df.astype(object).values.ravel())
        if "Reference No" not in text or "Tax Office" not in text:
            continue
        candidate = _extract_pairs_from_table(df)
        if len(candidate) > len(best):
            best = candidate
    return best


def _next_line(lines: list[str], label: str) -> str | None:
    label_norm = label.lower().rstrip(":")
    positions = [i for i, line in enumerate(lines) if line.lower().rstrip(":") == label_norm]
    for pos in reversed(positions):
        for line in lines[pos + 1 : pos + 5]:
            if line:
                return line
    return None


def _parse_master_from_text(body_text: str) -> dict:
    lines = [clean(line) for line in body_text.splitlines()]
    lines = [line for line in lines if line]
    result = {}
    for label, key in [
        ("Registration No", "registration_no"),
        ("Reference No", "reference_no"),
        ("Registered for Sales Tax", "registered_for_sales_tax_raw"),
        ("Name", "legal_name_fbr"),
        ("Category", "taxpayer_category"),
        ("PP/REG/INC No.", "pp_reg_inc_no"),
        ("Email", "masked_email_fbr"),
        ("Cell", "masked_cell_fbr"),
        ("Address", "registered_address"),
        ("Registered On", "registered_on"),
        ("Tax Office", "tax_office"),
        ("Registration Status", "registration_status_raw"),
    ]:
        value = _next_line(lines, label)
        if value:
            result[key] = value
    return result


def parse_business_activities(tables: list[pd.DataFrame], ntn: str) -> pd.DataFrame:
    rows = []
    for raw in tables:
        df = raw.copy()
        df.columns = _flatten_columns(df.columns)
        combined = " ".join(c.lower() for c in df.columns)
        if "principal activity" not in combined or "business" not in combined:
            continue

        sr_col = next((c for c in df.columns if "sr" in c.lower()), None)
        name_col = next((c for c in df.columns if "business" in c.lower() and "name" in c.lower()), None)
        addr_col = next((c for c in df.columns if "business" in c.lower() and "address" in c.lower()), None)
        act_col = next((c for c in df.columns if "principal" in c.lower() and "activity" in c.lower()), None)
        if not act_col:
            continue

        for _, record in df.iterrows():
            activity_raw = clean(record.get(act_col))
            business_name = clean(record.get(name_col)) if name_col else None
            business_address = clean(record.get(addr_col)) if addr_col else None
            business_sr = clean(record.get(sr_col)) if sr_col else None
            if not any([activity_raw, business_name, business_address]):
                continue
            activity_code = None
            activity_path = activity_raw
            if activity_raw:
                m = re.match(r"^(\d+)\s*-\s*(.*)$", activity_raw)
                if m:
                    activity_code = m.group(1)
                    activity_path = m.group(2)
            levels = [clean(x) for x in (activity_path or "").split("/") if clean(x)]
            rows.append({
                "ntn": str(ntn),
                "business_sr": business_sr,
                "business_name": business_name,
                "business_address": business_address,
                "activity_code": activity_code,
                "activity_level_1": levels[0] if len(levels) > 0 else None,
                "activity_level_2": levels[1] if len(levels) > 1 else None,
                "activity_detail": levels[-1] if levels else None,
                "principal_activity_raw": activity_raw,
            })

    columns = [
        "ntn", "business_sr", "business_name", "business_address", "activity_code",
        "activity_level_1", "activity_level_2", "activity_detail", "principal_activity_raw",
    ]
    return pd.DataFrame(rows, columns=columns).drop_duplicates().reset_index(drop=True)


def parse_profile(html: str, body_text: str, queried_ntn: str) -> tuple[dict, pd.DataFrame]:
    try:
        tables = pd.read_html(StringIO(html))
    except ValueError:
        tables = []

    master = _parse_master_from_tables(tables)
    fallback = _parse_master_from_text(body_text)
    for key, value in fallback.items():
        master.setdefault(key, value)

    raw_st = master.get("registered_for_sales_tax_raw") or ""
    master["registered_for_sales_tax"] = "Yes" if raw_st.lower().startswith("yes") else ("No" if raw_st.lower().startswith("no") else None)
    m = re.search(r"w\.?e\.?f\.?\s*([^,]+)$", raw_st, flags=re.I)
    master["sales_tax_registered_since"] = clean(m.group(1)) if m else None

    raw_status = master.get("registration_status_raw") or ""
    income = re.search(r"Income\s*Tax\s*:\s*([^,]+)", raw_status, flags=re.I)
    sales = re.search(r"Sales\s*Tax\s*:\s*([^,]+)", raw_status, flags=re.I)
    master["income_tax_status"] = clean(income.group(1)) if income else None
    master["sales_tax_status"] = clean(sales.group(1)) if sales else None
    master["queried_ntn"] = str(queried_ntn)

    activities = parse_business_activities(tables, str(queried_ntn))
    return master, activities
