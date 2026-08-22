from __future__ import annotations

import html
import re
from dataclasses import dataclass
from typing import Iterable

import numpy as np
import pandas as pd

ALIASES = {
    "hs_chapter_query": ["hs_chapter_query", "hs_chapter", "chapter", "hs2"],
    "source_record_id": ["source_record_id", "id", "record_id"],
    "company_id": ["company_id"],
    "exporter_name": ["exporter_name", "master_name", "company_name_detail", "company_name"],
    "hs2": ["hs2", "hs_chapter"],
    "hs4": ["hs4"],
    "hs8": ["hs8", "ptc_code", "pct_code"],
    "product_name": ["product_name", "commodity_description"],
    "product_hierarchy": ["product_hierarchy", "product"],
    "reported_record_count": ["reported_record_count", "Count(*)", "count"],
    "exported_value_rs": ["exported_value_rs", "ExpSum", "exported_value", "export_value"],
    "ntn": ["ntn", "detail_NTN", "NTN"],
    "address": ["address", "detail_address"],
    "email": ["master_email_search_result", "master_email", "email", "detail_master_email"],
    "telephone": ["telephone", "detail_telephone_number"],
}

REQUIRED = ["exporter_name", "hs8", "exported_value_rs"]

@dataclass
class Audit:
    rows: int
    columns: int
    missing_required: list[str]
    duplicate_rows: int
    invalid_hs8: int
    nonpositive_values: int
    unique_exporters: int
    unique_ntns: int
    unique_hs8: int
    chapters: list[str]
    warnings: list[str]


def _clean_text(x):
    if pd.isna(x):
        return pd.NA
    x = html.unescape(str(x))
    x = re.sub(r"<[^>]+>", " ", x)
    x = re.sub(r"\s+", " ", x).strip()
    return x or pd.NA


def _canonicalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    lower = {str(c).strip().lower(): c for c in df.columns}
    rename = {}
    for canonical, aliases in ALIASES.items():
        for alias in aliases:
            hit = lower.get(alias.lower())
            if hit is not None:
                rename[hit] = canonical
                break
    return df.rename(columns=rename)


def load_excel(file_or_path, sheet_name: str | None = None) -> tuple[pd.DataFrame, str]:
    xls = pd.ExcelFile(file_or_path)
    if sheet_name is None:
        candidates = [s for s in xls.sheet_names if s.lower().startswith("hs_")]
        sheet_name = candidates[0] if candidates else xls.sheet_names[0]
    return pd.read_excel(xls, sheet_name=sheet_name), sheet_name


def normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = _canonicalize_columns(df.copy())
    for col in ["exporter_name", "product_name", "product_hierarchy", "address", "email", "telephone", "ntn"]:
        if col in out:
            out[col] = out[col].map(_clean_text)
    for col, width in [("hs2", 2), ("hs4", 4), ("hs8", 8)]:
        if col in out:
            out[col] = out[col].astype("string").str.replace(r"\.0$", "", regex=True).str.replace(r"\D", "", regex=True).str.zfill(width)
    if "hs8" in out:
        out["hs2"] = out.get("hs2", out["hs8"].str[:2])
        out["hs4"] = out.get("hs4", out["hs8"].str[:4])
    for col in ["exported_value_rs", "reported_record_count"]:
        if col in out:
            out[col] = pd.to_numeric(out[col], errors="coerce")
    return out


def audit(df: pd.DataFrame) -> Audit:
    missing = [c for c in REQUIRED if c not in df.columns]
    invalid_hs8 = int((~df["hs8"].fillna("").str.fullmatch(r"\d{8}")).sum()) if "hs8" in df else len(df)
    nonpositive = int((df["exported_value_rs"].fillna(0) <= 0).sum()) if "exported_value_rs" in df else len(df)
    chapters = sorted(df["hs2"].dropna().astype(str).unique().tolist()) if "hs2" in df else []
    warnings = []
    if len(chapters) > 1:
        warnings.append(f"Input contains multiple HS2 chapters: {', '.join(chapters)}")
    if "reported_record_count" in df:
        warnings.append("reported_record_count is an observation/frequency field; it is NOT physical export quantity. Value/count is not a unit price.")
    warnings.append("TDAP export period/year must be treated as unresolved unless a year field is explicitly present in the supplied dataset/source metadata.")
    warnings.append("Shares computed here are shares of the supplied extract, not automatically shares of Pakistan's national exports.")
    if "ntn" in df and df["ntn"].dropna().nunique() == len(df):
        warnings.append("NTN is unique by row. Firm-level product diversification cannot be inferred if the extract retains only one HS8 row per firm.")
    return Audit(
        rows=len(df), columns=len(df.columns), missing_required=missing,
        duplicate_rows=int(df.duplicated().sum()), invalid_hs8=invalid_hs8,
        nonpositive_values=nonpositive,
        unique_exporters=int(df["exporter_name"].nunique()) if "exporter_name" in df else 0,
        unique_ntns=int(df["ntn"].nunique()) if "ntn" in df else 0,
        unique_hs8=int(df["hs8"].nunique()) if "hs8" in df else 0,
        chapters=chapters, warnings=warnings,
    )


def exporter_table(df: pd.DataFrame) -> pd.DataFrame:
    keys = [c for c in ["ntn", "exporter_name"] if c in df]
    g = df.groupby(keys, dropna=False).agg(
        reported_value_rs=("exported_value_rs", "sum"),
        hs8_count=("hs8", "nunique"),
        hs4_count=("hs4", "nunique"),
        record_count=("reported_record_count", "sum") if "reported_record_count" in df else ("hs8", "size"),
    ).reset_index()
    total = g.reported_value_rs.sum()
    g = g.sort_values("reported_value_rs", ascending=False).reset_index(drop=True)
    g["rank"] = np.arange(1, len(g)+1)
    g["share"] = g.reported_value_rs / total if total else 0
    g["cumulative_share"] = g.share.cumsum()
    return g


def hs8_table(df: pd.DataFrame) -> pd.DataFrame:
    aggs = {"reported_value_rs": ("exported_value_rs", "sum"), "exporters": ("exporter_name", "nunique")}
    if "reported_record_count" in df:
        aggs["record_count"] = ("reported_record_count", "sum")
    g = df.groupby(["hs8", "hs4", "product_name"], dropna=False).agg(**aggs).reset_index()
    total = g.reported_value_rs.sum()
    g = g.sort_values("reported_value_rs", ascending=False).reset_index(drop=True)
    g["rank"] = np.arange(1, len(g)+1)
    g["share"] = g.reported_value_rs / total if total else 0
    g["cumulative_share"] = g.share.cumsum()
    return g


def concentration(df: pd.DataFrame) -> dict:
    e = exporter_table(df)
    shares = e.share.to_numpy()
    return {
        "total_value_rs": float(e.reported_value_rs.sum()),
        "top1_share": float(shares[:1].sum()),
        "top5_share": float(shares[:5].sum()),
        "top10_share": float(shares[:10].sum()),
        "hhi": float(np.square(shares).sum() * 10000),
        "exporters_to_60pct": int(np.searchsorted(e.cumulative_share.to_numpy(), 0.60) + 1) if len(e) else 0,
    }


def strategic_screen(df: pd.DataFrame) -> pd.DataFrame:
    """Evidence-based screening using only fields actually present in TDAP extract.

    This deliberately does NOT claim new destinations, growth, unit value, or geopolitical fit;
    those require country/time/quantity or external datasets.
    """
    e = exporter_table(df)
    hs = hs8_table(df)[["hs8", "exporters"]].rename(columns={"exporters": "firms_in_hs8"})
    base = df[[c for c in ["ntn", "exporter_name", "hs8", "hs4", "product_name", "exported_value_rs"] if c in df]].copy()
    base = base.merge(hs, on="hs8", how="left")
    base["scarcity_score"] = 1 / base["firms_in_hs8"].clip(lower=1)
    base["scale_percentile"] = base["exported_value_rs"].rank(pct=True)
    base["capability_score"] = 100 * (0.65 * base["scale_percentile"] + 0.35 * base["scarcity_score"].rank(pct=True))
    base["screening_reason"] = np.where(base.firms_in_hs8 <= 5, "Scale + scarce HS8 capability", "Scale + established HS8 capability")
    return base.sort_values(["capability_score", "exported_value_rs"], ascending=False).reset_index(drop=True)
