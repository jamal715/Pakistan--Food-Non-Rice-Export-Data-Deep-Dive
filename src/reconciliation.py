from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .analysis import concentration, exporter_table, hs8_table, strategic_screen


@dataclass
class ReconciliationResult:
    passed: bool
    checks: pd.DataFrame
    summary: dict


def _close(a: float, b: float, atol: float = 1e-6, rtol: float = 1e-9) -> bool:
    if pd.isna(a) and pd.isna(b):
        return True
    return math.isclose(float(a), float(b), abs_tol=atol, rel_tol=rtol)


def _row(name: str, expected, actual, passed: bool, detail: str = "") -> dict:
    diff = np.nan
    try:
        diff = float(actual) - float(expected)
    except Exception:
        pass
    return {
        "check": name,
        "status": "PASS" if passed else "FAIL",
        "expected": expected,
        "actual": actual,
        "difference": diff,
        "detail": detail,
    }


def reconcile_chapter(df: pd.DataFrame) -> ReconciliationResult:
    """Independently reconcile dashboard calculations to the normalized source dataframe.

    The independent side uses direct pandas aggregations from source fields. It then compares
    those results with the production analysis functions used by the dashboard.
    """
    required = {"exporter_name", "hs8", "exported_value_rs"}
    missing = sorted(required - set(df.columns))
    if missing:
        checks = pd.DataFrame([_row("required analytical fields", required, set(df.columns), False, f"Missing: {', '.join(missing)}")])
        return ReconciliationResult(False, checks, {"failed_checks": 1, "passed_checks": 0})

    identity = [c for c in ["ntn", "exporter_name"] if c in df.columns]
    if not identity:
        identity = ["exporter_name"]

    source_total = float(pd.to_numeric(df["exported_value_rs"], errors="coerce").sum())
    direct_firms = df.groupby(identity, dropna=False)["exported_value_rs"].sum().sort_values(ascending=False)
    direct_hs8 = df.groupby("hs8", dropna=False)["exported_value_rs"].sum().sort_values(ascending=False)
    direct_firm_shares = direct_firms / source_total if source_total else direct_firms * 0

    prod_exporters = exporter_table(df)
    prod_hs8 = hs8_table(df)
    prod_conc = concentration(df)
    prod_screen = strategic_screen(df)

    checks: list[dict] = []
    checks.append(_row("source total = exporter aggregation", source_total, float(prod_exporters["reported_value_rs"].sum()), _close(source_total, prod_exporters["reported_value_rs"].sum(), atol=0.01)))
    checks.append(_row("source total = HS8 aggregation", source_total, float(prod_hs8["reported_value_rs"].sum()), _close(source_total, prod_hs8["reported_value_rs"].sum(), atol=0.01)))
    checks.append(_row("concentration total = source total", source_total, prod_conc["total_value_rs"], _close(source_total, prod_conc["total_value_rs"], atol=0.01)))

    direct_unique_firms = int(direct_firms.shape[0])
    direct_unique_hs8 = int(df["hs8"].nunique(dropna=True))
    checks.append(_row("unique exporter identities", direct_unique_firms, int(len(prod_exporters)), direct_unique_firms == len(prod_exporters)))
    checks.append(_row("distinct HS8 products", direct_unique_hs8, int(prod_hs8["hs8"].nunique()), direct_unique_hs8 == prod_hs8["hs8"].nunique()))

    firm_share_sum = float(prod_exporters["share"].sum())
    checks.append(_row("company chapter shares sum to 100%", 1.0 if source_total else 0.0, firm_share_sum, _close(1.0 if source_total else 0.0, firm_share_sum, atol=1e-10)))

    direct_top10 = float(direct_firm_shares.iloc[:10].sum()) if len(direct_firm_shares) else 0.0
    checks.append(_row("top 10 share", direct_top10, prod_conc["top10_share"], _close(direct_top10, prod_conc["top10_share"], atol=1e-12)))
    direct_hhi = float(np.square(direct_firm_shares.to_numpy()).sum() * 10000) if source_total else 0.0
    checks.append(_row("HHI", direct_hhi, prod_conc["hhi"], _close(direct_hhi, prod_conc["hhi"], atol=1e-8)))

    direct_cum = direct_firm_shares.cumsum().to_numpy()
    direct_to60 = int(np.searchsorted(direct_cum, 0.60) + 1) if len(direct_cum) else 0
    checks.append(_row("exporters needed for 60%", direct_to60, prod_conc["exporters_to_60pct"], direct_to60 == prod_conc["exporters_to_60pct"]))

    # Independent exporter × HS8 aggregation and within-HS8 position.
    pair_keys = identity + ["hs8"]
    direct_pairs = df.groupby(pair_keys, dropna=False)["exported_value_rs"].sum().rename("direct_hs8_value_rs").reset_index()
    totals = direct_pairs.groupby("hs8", dropna=False)["direct_hs8_value_rs"].sum().rename("direct_hs8_total_rs").reset_index()
    direct_pairs = direct_pairs.merge(totals, on="hs8", how="left")
    direct_pairs["direct_share_within_hs8"] = np.where(direct_pairs["direct_hs8_total_rs"] > 0, direct_pairs["direct_hs8_value_rs"] / direct_pairs["direct_hs8_total_rs"], np.nan)
    direct_pairs["direct_rank_within_hs8"] = direct_pairs.groupby("hs8")["direct_hs8_value_rs"].rank(method="min", ascending=False).astype("Int64")

    screen_pair = prod_screen.groupby(pair_keys, dropna=False).agg(
        screen_hs8_value_rs=("hs8_value_rs", "sum"),
        screen_share_within_hs8=("share_within_hs8", "sum"),
        screen_rank_within_hs8=("rank_within_hs8", "min"),
    ).reset_index()
    merged = direct_pairs.merge(screen_pair, on=pair_keys, how="outer", indicator=True)
    pairs_complete = bool((merged["_merge"] == "both").all())
    checks.append(_row("exporter × HS8 key coverage", len(direct_pairs), len(screen_pair), pairs_complete and len(direct_pairs) == len(screen_pair), "Every source exporter-HS8 relationship must appear once in the screen."))

    if len(merged):
        value_diff = (merged["direct_hs8_value_rs"] - merged["screen_hs8_value_rs"]).abs()
        share_diff = (merged["direct_share_within_hs8"] - merged["screen_share_within_hs8"]).abs()
        rank_equal = merged["direct_rank_within_hs8"].astype("Int64").eq(merged["screen_rank_within_hs8"].astype("Int64"))
        checks.append(_row("exporter × HS8 values reconcile", 0.0, float(value_diff.max(skipna=True) if value_diff.notna().any() else 0.0), bool((value_diff.fillna(np.inf) <= 0.01).all())))
        checks.append(_row("within-HS8 shares reconcile", 0.0, float(share_diff.max(skipna=True) if share_diff.notna().any() else 0.0), bool((share_diff.fillna(np.inf) <= 1e-12).all())))
        checks.append(_row("within-HS8 ranks reconcile", True, bool(rank_equal.fillna(False).all()), bool(rank_equal.fillna(False).all())))

    hs8_share_sums = prod_screen.groupby("hs8", dropna=False)["share_within_hs8"].sum()
    max_hs8_share_error = float((hs8_share_sums - 1.0).abs().max()) if len(hs8_share_sums) else 0.0
    checks.append(_row("shares within every HS8 sum to 100%", 0.0, max_hs8_share_error, max_hs8_share_error <= 1e-10))

    check_df = pd.DataFrame(checks)
    failed = int((check_df["status"] == "FAIL").sum())
    summary = {
        "passed_checks": int((check_df["status"] == "PASS").sum()),
        "failed_checks": failed,
        "source_total_value_rs": source_total,
        "exporter_identities": direct_unique_firms,
        "hs8_products": direct_unique_hs8,
    }
    return ReconciliationResult(failed == 0, check_df, summary)
