from __future__ import annotations

import html
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

ALIASES = {
    "hs_chapter_query": ["hs_chapter_query", "hs_chapter", "chapter", "hs2"],
    "source_record_id": ["source_record_id", "id", "record_id"],
    "company_id": ["company_id"],
    "exporter_name": ["exporter_name", "master_name", "company_name_detail", "company_name"],
    "hs2": ["hs2", "hs_chapter"], "hs4": ["hs4"], "hs8": ["hs8", "ptc_code", "pct_code"],
    "product_name": ["product_name", "commodity_description"],
    "product_hierarchy": ["product_hierarchy", "product"],
    "reported_record_count": ["reported_record_count", "Count(*)", "count"],
    "exported_value_rs": ["exported_value_rs", "ExpSum", "exported_value", "export_value"],
    "ntn": ["ntn", "detail_NTN", "NTN"], "address": ["address", "detail_address"],
    "email": ["master_email_search_result", "master_email", "email", "detail_master_email"],
    "telephone": ["telephone", "detail_telephone_number"],
}
REQUIRED = ["exporter_name", "hs8", "exported_value_rs"]

@dataclass
class Audit:
    rows: int; columns: int; missing_required: list[str]; duplicate_rows: int; invalid_hs8: int
    nonpositive_values: int; unique_exporters: int; unique_ntns: int; unique_hs8: int
    chapters: list[str]; warnings: list[str]

def _clean_text(x):
    if pd.isna(x): return pd.NA
    x = html.unescape(str(x)); x = re.sub(r"<[^>]+>", " ", x); x = re.sub(r"\s+", " ", x).strip()
    return x or pd.NA

def _first_nonnull(s: pd.Series):
    s = s.dropna(); return s.iloc[0] if len(s) else pd.NA

def _canonicalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    lower = {str(c).strip().lower(): c for c in df.columns}; rename = {}
    for canonical, aliases in ALIASES.items():
        for alias in aliases:
            hit = lower.get(alias.lower())
            if hit is not None: rename[hit] = canonical; break
    return df.rename(columns=rename)

def load_excel(file_or_path, sheet_name: str | None = None) -> tuple[pd.DataFrame, str]:
    xls = pd.ExcelFile(file_or_path)
    if sheet_name is None:
        scored = []
        for s in xls.sheet_names:
            preview = pd.read_excel(xls, sheet_name=s, nrows=5); cols = {str(c).strip().lower() for c in preview.columns}
            score = sum(any(alias.lower() in cols for alias in aliases) for aliases in ALIASES.values()); scored.append((score, s))
        sheet_name = max(scored)[1] if scored else xls.sheet_names[0]
    return pd.read_excel(xls, sheet_name=sheet_name), sheet_name

def normalize(df: pd.DataFrame) -> pd.DataFrame:
    out = _canonicalize_columns(df.copy())
    for col in ["exporter_name", "product_name", "product_hierarchy", "address", "email", "telephone", "ntn"]:
        if col in out: out[col] = out[col].map(_clean_text)
    for col, width in [("hs2", 2), ("hs4", 4), ("hs8", 8)]:
        if col in out: out[col] = out[col].astype("string").str.replace(r"\.0$", "", regex=True).str.replace(r"\D", "", regex=True).str.zfill(width)
    if "hs8" in out:
        out["hs2"] = out.get("hs2", out["hs8"].str[:2]); out["hs4"] = out.get("hs4", out["hs8"].str[:4])
    for col in ["exported_value_rs", "reported_record_count"]:
        if col in out: out[col] = pd.to_numeric(out[col], errors="coerce")
    return out

def audit(df: pd.DataFrame) -> Audit:
    missing = [c for c in REQUIRED if c not in df.columns]
    invalid_hs8 = int((~df["hs8"].fillna("").str.fullmatch(r"\d{8}")).sum()) if "hs8" in df else len(df)
    nonpositive = int((df["exported_value_rs"].fillna(0) <= 0).sum()) if "exported_value_rs" in df else len(df)
    chapters = sorted(df["hs2"].dropna().astype(str).unique().tolist()) if "hs2" in df else []; warnings = []
    if len(chapters) > 1: warnings.append(f"Input contains multiple HS2 chapters: {', '.join(chapters)}")
    if "reported_record_count" in df: warnings.append("reported_record_count is a TDAP observation/frequency field; it is NOT physical export quantity. Value/count is not a unit price.")
    warnings.append("TDAP export period/year must be treated as unresolved unless a year field is explicitly present in the supplied dataset/source metadata.")
    warnings.append("Shares computed here are shares of the supplied TDAP extract, not automatically shares of Pakistan's national exports.")
    if "ntn" in df and df["ntn"].dropna().nunique() == len(df): warnings.append("NTN is unique by row. Firm-level product diversification cannot be inferred if the extract retains only one HS8 row per firm.")
    return Audit(len(df), len(df.columns), missing, int(df.duplicated().sum()), invalid_hs8, nonpositive,
                 int(df["exporter_name"].nunique()) if "exporter_name" in df else 0,
                 int(df["ntn"].nunique()) if "ntn" in df else 0,
                 int(df["hs8"].nunique()) if "hs8" in df else 0, chapters, warnings)

def exporter_table(df: pd.DataFrame) -> pd.DataFrame:
    keys = [c for c in ["ntn", "exporter_name"] if c in df]
    agg = {"reported_value_rs": ("exported_value_rs", "sum"), "hs8_count": ("hs8", "nunique"), "hs4_count": ("hs4", "nunique"),
           "record_count": ("reported_record_count", "sum") if "reported_record_count" in df else ("hs8", "size"),
           "largest_hs8": ("hs8", lambda s: s.loc[df.loc[s.index, "exported_value_rs"].idxmax()] if len(s) else pd.NA)}
    for c in ["email", "telephone", "address"]:
        if c in df: agg[c] = (c, _first_nonnull)
    g = df.groupby(keys, dropna=False).agg(**agg).reset_index(); total = g.reported_value_rs.sum()
    g = g.sort_values("reported_value_rs", ascending=False).reset_index(drop=True); g["rank"] = np.arange(1, len(g)+1)
    g["share"] = g.reported_value_rs / total if total else 0; g["cumulative_share"] = g.share.cumsum()
    g["avg_value_per_reported_record_rs"] = np.where(g["record_count"] > 0, g["reported_value_rs"] / g["record_count"], np.nan)
    cols = ["rank"] + keys + ["reported_value_rs", "share", "cumulative_share", "record_count", "avg_value_per_reported_record_rs", "hs8_count", "hs4_count", "largest_hs8"]
    cols += [c for c in ["email", "telephone", "address"] if c in g]; return g[cols]

def hs8_table(df: pd.DataFrame) -> pd.DataFrame:
    aggs = {"reported_value_rs": ("exported_value_rs", "sum"), "exporters": ("exporter_name", "nunique")}
    if "reported_record_count" in df: aggs["record_count"] = ("reported_record_count", "sum")
    g = df.groupby(["hs8", "hs4", "product_name"], dropna=False).agg(**aggs).reset_index(); total = g.reported_value_rs.sum()
    g = g.sort_values("reported_value_rs", ascending=False).reset_index(drop=True); g["rank"] = np.arange(1, len(g)+1)
    g["share"] = g.reported_value_rs / total if total else 0; g["cumulative_share"] = g.share.cumsum(); return g

def concentration(df: pd.DataFrame) -> dict:
    e = exporter_table(df); shares = e.share.to_numpy(); cum = e.cumulative_share.to_numpy()
    def n_to(threshold: float) -> int: return int(np.searchsorted(cum, threshold)+1) if len(cum) else 0
    return {"total_value_rs": float(e.reported_value_rs.sum()), "top1_share": float(shares[:1].sum()), "top5_share": float(shares[:5].sum()),
            "top10_share": float(shares[:10].sum()), "top20_share": float(shares[:20].sum()), "hhi": float(np.square(shares).sum()*10000),
            "exporters_to_25pct": n_to(.25), "exporters_to_50pct": n_to(.50), "exporters_to_60pct": n_to(.60), "exporters_to_80pct": n_to(.80), "exporters_to_90pct": n_to(.90)}

def strategic_screen(df: pd.DataFrame) -> pd.DataFrame:
    """Transparent exporter × HS8 evidence screen.

    One row is one exporter-HS8 capability after aggregation. No composite score is
    used as the primary ranking. Observed value, within-HS8 position, company-level
    chapter scale and participation are shown separately so every conclusion can be
    reconstructed from the source extract.
    """
    identity = [c for c in ["ntn", "exporter_name"] if c in df]
    group_keys = identity + ["hs8", "hs4", "product_name"]
    aggs = {"hs8_value_rs": ("exported_value_rs", "sum")}
    if "reported_record_count" in df: aggs["reported_records"] = ("reported_record_count", "sum")
    for c in ["email", "telephone"]:
        if c in df: aggs[c] = (c, _first_nonnull)
    base = df.groupby(group_keys, dropna=False).agg(**aggs).reset_index()

    firm = exporter_table(df)[identity + ["rank", "reported_value_rs", "share", "hs8_count", "hs4_count"]].rename(columns={
        "rank": "chapter_rank", "reported_value_rs": "firm_chapter_value_rs", "share": "firm_chapter_share",
        "hs8_count": "firm_hs8_breadth", "hs4_count": "firm_hs4_breadth"})
    base = base.merge(firm, on=identity, how="left")

    hs = base.groupby("hs8", dropna=False).agg(hs8_total_value_rs=("hs8_value_rs", "sum"), firms_in_hs8=("exporter_name", "nunique")).reset_index()
    base = base.merge(hs, on="hs8", how="left")
    base["share_within_hs8"] = np.where(base.hs8_total_value_rs > 0, base.hs8_value_rs / base.hs8_total_value_rs, np.nan)
    base["rank_within_hs8"] = base.groupby("hs8")["hs8_value_rs"].rank(method="min", ascending=False).astype("Int64")
    base["scarcity_indicator"] = 1 / base["firms_in_hs8"].clip(lower=1)
    base["firm_scale_percentile"] = base["firm_chapter_value_rs"].rank(pct=True)

    def classify(r):
        top_product = r["rank_within_hs8"] <= 3
        material_share = r["share_within_hs8"] >= .10
        large_firm = r["firm_scale_percentile"] >= .90
        scarce = r["firms_in_hs8"] <= 5
        if large_firm and top_product and material_share: return "A — high-priority evidence"
        if (top_product and material_share) or (large_firm and scarce): return "B — priority review"
        return "C — broader pipeline"
    base["evidence_tier"] = base.apply(classify, axis=1)

    def reason(r):
        facts = [f"chapter rank {int(r.chapter_rank)}", f"HS8 rank {int(r.rank_within_hs8)} of {int(r.firms_in_hs8)}", f"{r.share_within_hs8:.1%} of observed HS8 value"]
        if int(r.firms_in_hs8) <= 5: facts.append(f"only {int(r.firms_in_hs8)} observed firms in HS8")
        if int(r.firm_hs8_breadth) > 1: facts.append(f"{int(r.firm_hs8_breadth)} observed HS8 capabilities")
        return "; ".join(facts)
    base["screening_reason"] = base.apply(reason, axis=1)
    tier_order = {"A — high-priority evidence": 1, "B — priority review": 2, "C — broader pipeline": 3}
    base["_tier"] = base.evidence_tier.map(tier_order)
    return base.sort_values(["_tier", "chapter_rank", "rank_within_hs8", "hs8_value_rs"], ascending=[True, True, True, False]).drop(columns="_tier").reset_index(drop=True)
