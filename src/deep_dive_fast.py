from __future__ import annotations

import hashlib
import json
import re
from pathlib import Path

import numpy as np
import pandas as pd

from .deep_dive import (
    CrossChapterAudit,
    DeepDiveResult,
    _canonical_name,
    _clean_name,
    _clean_ntn,
    _clean_phone,
    _join_unique,
    build_verified_contact_directory,
    exporter_index,
    load_cross_chapter_universe,
)


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024, b""), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_cross_chapter_cache(source_path: Path, cache_path: Path, manifest_path: Path) -> dict:
    """Materialize the already-normalized cross-chapter universe as a fast, derived cache.

    The source workbook remains authoritative. A SHA-256 fingerprint is stored in the manifest;
    runtime code refuses to use this cache when the workbook fingerprint no longer matches.
    """
    universe, audit = load_cross_chapter_universe(source_path)
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    universe.to_csv(cache_path, index=False, compression="gzip")
    manifest = {
        "source_file": source_path.name,
        "source_sha256": sha256_file(source_path),
        "cache_rows": int(len(universe)),
        "chapters": audit.chapters,
        "sheets": audit.sheets,
        "total_value_rs": float(audit.total_value_rs),
        "unique_ntns": int(audit.unique_ntns),
        "unique_hs8": int(audit.unique_hs8),
        "missing_ntn_rows": int(audit.missing_ntn_rows),
        "inconsistent_hs2_rows": int(audit.inconsistent_hs2_rows),
    }
    manifest_path.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_cross_chapter_cache(source_path: Path, cache_path: Path, manifest_path: Path) -> tuple[pd.DataFrame, CrossChapterAudit] | None:
    """Load the derived cache only when it is provably synchronized to the source workbook."""
    if not source_path.exists() or not cache_path.exists() or not manifest_path.exists():
        return None
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    if manifest.get("source_sha256") != sha256_file(source_path):
        return None

    universe = pd.read_csv(cache_path, compression="gzip", dtype="string")
    for col in ["exported_value_rs", "reported_record_count"]:
        if col in universe:
            universe[col] = pd.to_numeric(universe[col], errors="coerce")
    # CSV round-tripping represents blank text as NA by default. Restore the same empty-string
    # identity semantics used by the authoritative workbook loader, especially for missing NTNs.
    for col in universe.columns:
        if col not in {"exported_value_rs", "reported_record_count"}:
            universe[col] = universe[col].fillna("")

    if len(universe) != int(manifest.get("cache_rows", -1)):
        return None
    if "chapter" not in universe or "hs8" not in universe or "_ntn_key" not in universe or "_exporter_key" not in universe:
        return None

    total = float(universe["exported_value_rs"].sum())
    if not np.isclose(total, float(manifest.get("total_value_rs", np.nan)), atol=0.01):
        return None

    audit = CrossChapterAudit(
        chapters=list(manifest["chapters"]),
        sheets=list(manifest["sheets"]),
        rows=int(manifest["cache_rows"]),
        total_value_rs=total,
        unique_ntns=int(manifest["unique_ntns"]),
        unique_hs8=int(manifest["unique_hs8"]),
        missing_ntn_rows=int(manifest["missing_ntn_rows"]),
        inconsistent_hs2_rows=int(manifest["inconsistent_hs2_rows"]),
    )
    return universe, audit


def build_fast_indexes(universe: pd.DataFrame, contacts: pd.DataFrame | None = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Build exporter-search and verified-contact indexes once, not once per query."""
    return exporter_index(universe), build_verified_contact_directory(universe, contacts)


def find_exporters_fast(index: pd.DataFrame, query: str, limit: int = 100) -> pd.DataFrame:
    q_name = _clean_name(query)
    q_ntn = _clean_ntn(query)
    if not q_name and not q_ntn:
        return index.iloc[0:0].copy()
    name_hit = index["name_aliases"].map(_clean_name).str.contains(re.escape(q_name), na=False) if q_name else False
    ntn_hit = index["ntn"].astype("string").str.contains(re.escape(q_ntn), na=False) if q_ntn else False
    return index[name_hit | ntn_hit].head(limit).reset_index(drop=True)


def exporter_portfolio_fast(universe: pd.DataFrame, ntn: str, contact_directory: pd.DataFrame) -> DeepDiveResult:
    """Same exporter math as exporter_portfolio, using a prebuilt contact directory."""
    ntn_key = _clean_ntn(ntn)
    rows = universe[universe["_ntn_key"].eq(ntn_key)].copy()
    if rows.empty:
        raise KeyError(f"NTN {ntn_key or ntn} was not found in the loaded cross-chapter universe.")

    total = float(rows["exported_value_rs"].sum())
    portfolio_rows: list[dict] = []
    for hs8, group in rows.groupby("hs8", dropna=False, sort=False):
        portfolio_rows.append({
            "chapter": str(group["chapter"].iloc[0]),
            "hs8": hs8,
            "product_name": _join_unique(group["product_name"]) if "product_name" in group.columns else "",
            "reported_value_rs": float(group["exported_value_rs"].sum()),
            "source_rows": int(len(group)),
        })
    table = pd.DataFrame(portfolio_rows).sort_values("reported_value_rs", ascending=False).reset_index(drop=True)
    table["rank"] = np.arange(1, len(table) + 1)
    table["share_of_exporter"] = table["reported_value_rs"] / total if total else 0.0
    table = table[["rank", "chapter", "hs8", "product_name", "reported_value_rs", "share_of_exporter", "source_rows"]]

    contact = contact_directory[contact_directory["ntn"].eq(ntn_key)] if len(contact_directory) else pd.DataFrame()
    phones = str(contact.iloc[0]["phones"]) if len(contact) else ""
    emails = str(contact.iloc[0]["emails"]) if len(contact) else (_join_unique(rows["email"]) if "email" in rows.columns else "")
    aliases = _join_unique(rows["exporter_name"])
    canonical = _canonical_name(rows)

    checks = pd.DataFrame([
        {"check": "portfolio HS8 values sum to exporter total", "status": "PASS" if np.isclose(table["reported_value_rs"].sum(), total, atol=0.01) else "FAIL", "expected": total, "actual": float(table["reported_value_rs"].sum())},
        {"check": "portfolio shares sum to 100%", "status": "PASS" if (np.isclose(table["share_of_exporter"].sum(), 1.0, atol=1e-12) if total else True) else "FAIL", "expected": 1.0 if total else 0.0, "actual": float(table["share_of_exporter"].sum())},
        {"check": "all source rows resolve to one NTN", "status": "PASS" if rows["_ntn_key"].nunique() == 1 else "FAIL", "expected": 1, "actual": int(rows["_ntn_key"].nunique())},
    ])
    summary = {
        "ntn": ntn_key,
        "exporter_name": canonical,
        "name_aliases": aliases,
        "total_reported_value_rs": total,
        "hs8_products": int(rows["hs8"].nunique(dropna=True)),
        "chapters": int(rows["chapter"].nunique(dropna=True)),
        "phones": phones,
        "emails": emails,
    }
    return DeepDiveResult(summary=summary, table=table, checks=checks)


def hs8_exporters_fast(universe: pd.DataFrame, hs8_code: str, contact_directory: pd.DataFrame) -> DeepDiveResult:
    """Same HS8 math as hs8_exporters, using a prebuilt contact directory."""
    code = re.sub(r"\D", "", str(hs8_code))
    if not re.fullmatch(r"\d{8}", code):
        raise ValueError("HS8 search requires an exact 8-digit code.")
    rows = universe[universe["hs8"].astype("string").eq(code)].copy()
    if rows.empty:
        raise KeyError(f"HS8 {code} was not found in the loaded cross-chapter universe.")

    rows["_entity_key"] = np.where(rows["_ntn_key"].ne(""), "NTN:" + rows["_ntn_key"], "NAME:" + rows["_exporter_key"])
    total = float(rows["exported_value_rs"].sum())
    directory = contact_directory.set_index("ntn") if len(contact_directory) else pd.DataFrame()

    company_rows: list[dict] = []
    for _, group in rows.groupby("_entity_key", dropna=False, sort=False):
        ntn_key = str(group["_ntn_key"].iloc[0]) if group["_ntn_key"].iloc[0] else ""
        email = _join_unique(group["email"]) if "email" in group.columns else ""
        source_phone = _join_unique(group["telephone"].map(_clean_phone)) if "telephone" in group.columns else ""
        if ntn_key and not directory.empty and ntn_key in directory.index:
            phone = str(directory.loc[ntn_key, "phones"])
            email = _join_unique([email, directory.loc[ntn_key, "emails"]])
        else:
            phone = source_phone
        company_rows.append({
            "exporter_name": _canonical_name(group),
            "ntn": ntn_key,
            "phone": phone,
            "email": email,
            "identity_status": "NTN verified" if ntn_key else "NTN unavailable — grouped by observed exporter name",
            "reported_value_rs": float(group["exported_value_rs"].sum()),
            "source_rows": int(len(group)),
        })

    table = pd.DataFrame(company_rows).sort_values("reported_value_rs", ascending=False).reset_index(drop=True)
    table["rank"] = table["reported_value_rs"].rank(method="min", ascending=False).astype("Int64")
    table["share_of_hs8"] = table["reported_value_rs"] / total if total else 0.0
    table = table[["rank", "exporter_name", "ntn", "phone", "email", "reported_value_rs", "share_of_hs8", "identity_status", "source_rows"]]

    checks = pd.DataFrame([
        {"check": "exporter values sum to HS8 total", "status": "PASS" if np.isclose(table["reported_value_rs"].sum(), total, atol=0.01) else "FAIL", "expected": total, "actual": float(table["reported_value_rs"].sum())},
        {"check": "exporter shares sum to 100%", "status": "PASS" if (np.isclose(table["share_of_hs8"].sum(), 1.0, atol=1e-12) if total else True) else "FAIL", "expected": 1.0 if total else 0.0, "actual": float(table["share_of_hs8"].sum())},
        {"check": "HS8 belongs to one HS2 chapter", "status": "PASS" if rows["chapter"].nunique() == 1 else "FAIL", "expected": 1, "actual": int(rows["chapter"].nunique())},
    ])
    summary = {
        "hs8": code,
        "chapter": str(rows["chapter"].iloc[0]),
        "product_name": _join_unique(rows["product_name"]) if "product_name" in rows.columns else "",
        "total_reported_value_rs": total,
        "exporters": int(len(table)),
        "verified_ntn_exporters": int(table["ntn"].astype("string").ne("").sum()),
        "missing_ntn_exporters": int(table["ntn"].astype("string").eq("").sum()),
    }
    return DeepDiveResult(summary=summary, table=table, checks=checks)
