from __future__ import annotations

import html
import re
from dataclasses import dataclass

import numpy as np
import pandas as pd

from .analysis import REQUIRED, normalize


@dataclass
class CrossChapterAudit:
    chapters: list[str]
    sheets: list[str]
    rows: int
    total_value_rs: float
    unique_ntns: int
    unique_hs8: int
    missing_ntn_rows: int
    inconsistent_hs2_rows: int


@dataclass
class DeepDiveResult:
    summary: dict
    table: pd.DataFrame
    checks: pd.DataFrame


def _clean_name(value) -> str:
    if pd.isna(value):
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip().upper()
    return text


def _clean_ntn(value) -> str:
    if pd.isna(value):
        return ""
    text = str(value).strip()
    text = re.sub(r"\.0$", "", text)
    text = re.sub(r"\s+", "", text)
    return text.upper()


def _clean_phone(value) -> str:
    if pd.isna(value):
        return ""
    text = re.sub(r"\s+", " ", str(value)).strip()
    return "" if text.lower() in {"", "nan", "none", "null"} else text


def _sheet_chapter(sheet_name: str) -> str | None:
    m = re.search(r"(?:^|\b)HS[_\s-]?(\d{1,2})(?:\b|\s)", str(sheet_name), flags=re.I)
    return m.group(1).zfill(2) if m else None


def _join_unique(values, sep: str = " | ") -> str:
    seen: list[str] = []
    for value in values:
        if pd.isna(value):
            continue
        text = str(value).strip()
        if not text or text.lower() in {"nan", "none", "null"}:
            continue
        if text not in seen:
            seen.append(text)
    return sep.join(seen)


def _canonical_name(group: pd.DataFrame) -> str:
    named = group.dropna(subset=["exporter_name"]).copy()
    if named.empty:
        return ""
    totals = named.groupby("exporter_name", dropna=False)["exported_value_rs"].sum().sort_values(ascending=False)
    return str(totals.index[0])


def load_cross_chapter_universe(file_or_path) -> tuple[pd.DataFrame, CrossChapterAudit]:
    """Load every valid HS chapter sheet into a separate cross-chapter research universe.

    This function never feeds the existing chapter-specific calculations. It exists only for
    the exporter/product deep-dive tab. Every sheet must contain the canonical analytical
    fields and its observed HS2 values must agree with the HS chapter encoded in the sheet name.
    """
    if hasattr(file_or_path, "seek"):
        file_or_path.seek(0)
    xls = pd.ExcelFile(file_or_path)
    frames: list[pd.DataFrame] = []
    loaded_sheets: list[str] = []
    inconsistent_rows = 0

    for sheet_name in xls.sheet_names:
        chapter = _sheet_chapter(sheet_name)
        if chapter is None:
            continue
        raw = pd.read_excel(xls, sheet_name=sheet_name)
        df = normalize(raw)
        missing = [c for c in REQUIRED if c not in df.columns]
        if missing:
            continue
        observed = df["hs8"].dropna().astype("string").str[:2]
        bad = int(observed.ne(chapter).sum())
        inconsistent_rows += bad
        if bad:
            raise ValueError(f"Cross-chapter deep dive stopped: sheet {sheet_name} is labelled HS {chapter} but contains {bad} rows from another HS2 chapter.")
        df = df.copy()
        df["chapter"] = chapter
        df["source_sheet"] = sheet_name
        df["_ntn_key"] = df["ntn"].map(_clean_ntn) if "ntn" in df.columns else ""
        df["_exporter_key"] = df["exporter_name"].map(_clean_name)
        frames.append(df)
        loaded_sheets.append(sheet_name)

    if hasattr(file_or_path, "seek"):
        file_or_path.seek(0)
    if not frames:
        raise ValueError("No valid HS chapter sheets were found for the cross-chapter deep dive.")

    universe = pd.concat(frames, ignore_index=True, sort=False)
    universe["exported_value_rs"] = pd.to_numeric(universe["exported_value_rs"], errors="coerce")
    chapters = sorted(universe["chapter"].dropna().astype(str).unique().tolist())
    audit = CrossChapterAudit(
        chapters=chapters,
        sheets=loaded_sheets,
        rows=int(len(universe)),
        total_value_rs=float(universe["exported_value_rs"].sum()),
        unique_ntns=int(universe.loc[universe["_ntn_key"].ne(""), "_ntn_key"].nunique()),
        unique_hs8=int(universe["hs8"].nunique(dropna=True)),
        missing_ntn_rows=int(universe["_ntn_key"].eq("").sum()),
        inconsistent_hs2_rows=inconsistent_rows,
    )
    return universe, audit


def exporter_index(universe: pd.DataFrame) -> pd.DataFrame:
    """One row per verified NTN. Names remain searchable aliases; NTN is the primary identity."""
    rows: list[dict] = []
    verified = universe[universe["_ntn_key"].ne("")].copy()
    for ntn, group in verified.groupby("_ntn_key", sort=False):
        rows.append({
            "ntn": ntn,
            "exporter_name": _canonical_name(group),
            "name_aliases": _join_unique(group["exporter_name"]),
            "reported_value_rs": float(group["exported_value_rs"].sum()),
            "hs8_products": int(group["hs8"].nunique(dropna=True)),
            "chapters": int(group["chapter"].nunique(dropna=True)),
        })
    if not rows:
        return pd.DataFrame(columns=["ntn", "exporter_name", "name_aliases", "reported_value_rs", "hs8_products", "chapters"])
    return pd.DataFrame(rows).sort_values("reported_value_rs", ascending=False).reset_index(drop=True)


def find_exporters(universe: pd.DataFrame, query: str, limit: int = 100) -> pd.DataFrame:
    index = exporter_index(universe)
    q_name = _clean_name(query)
    q_ntn = _clean_ntn(query)
    if not q_name and not q_ntn:
        return index.iloc[0:0].copy()
    name_hit = index["name_aliases"].map(_clean_name).str.contains(re.escape(q_name), na=False) if q_name else False
    ntn_hit = index["ntn"].astype("string").str.contains(re.escape(q_ntn), na=False) if q_ntn else False
    return index[name_hit | ntn_hit].head(limit).reset_index(drop=True)


def build_verified_contact_directory(universe: pd.DataFrame, contacts: pd.DataFrame | None = None) -> pd.DataFrame:
    """Build an NTN-keyed contact directory with conservative sidecar verification.

    A sidecar phone enters the directory only if chapter + normalized exporter name maps to
    exactly one nonblank NTN in the analytical universe and exactly one nonblank phone in the
    sidecar. Multiple verified phone numbers across chapters are displayed together rather than
    arbitrarily selecting one.
    """
    verified = universe[universe["_ntn_key"].ne("")].copy()
    base_rows: list[dict] = []
    for ntn, group in verified.groupby("_ntn_key", sort=False):
        source_phones = _join_unique(group["telephone"].map(_clean_phone)) if "telephone" in group.columns else ""
        emails = _join_unique(group["email"]) if "email" in group.columns else ""
        base_rows.append({"ntn": ntn, "source_phones": source_phones, "emails": emails})
    directory = pd.DataFrame(base_rows)
    if directory.empty:
        directory = pd.DataFrame(columns=["ntn", "source_phones", "emails"])

    safe_rows: list[dict] = []
    if contacts is not None and len(contacts):
        required = {"HS_Chapter", "exporter_name", "telephone"}
        missing = sorted(required - set(contacts.columns))
        if missing:
            raise ValueError("Contact workbook is missing required columns: " + ", ".join(missing))
        c = contacts.copy()
        c["_chapter"] = c["HS_Chapter"].astype("string").str.replace(r"\D", "", regex=True).str.zfill(2)
        c["_exporter_key"] = c["exporter_name"].map(_clean_name)
        c["_phone"] = c["telephone"].map(_clean_phone)

        identity_map: dict[tuple[str, str], set[str]] = {}
        for key, group in universe.groupby(["chapter", "_exporter_key"], dropna=False):
            identity_map[(str(key[0]), str(key[1]))] = {x for x in group["_ntn_key"].tolist() if x}

        for (chapter, exporter_key), group in c.groupby(["_chapter", "_exporter_key"], dropna=False):
            phones = {x for x in group["_phone"].tolist() if x}
            ntns = identity_map.get((str(chapter), str(exporter_key)), set())
            if len(phones) == 1 and len(ntns) == 1:
                safe_rows.append({"ntn": next(iter(ntns)), "verified_phone": next(iter(phones))})

    if safe_rows:
        safe = pd.DataFrame(safe_rows).groupby("ntn", dropna=False)["verified_phone"].agg(_join_unique).reset_index()
        directory = directory.merge(safe, on="ntn", how="outer")
    else:
        directory["verified_phone"] = ""

    directory["source_phones"] = directory.get("source_phones", "").fillna("")
    directory["verified_phone"] = directory.get("verified_phone", "").fillna("")
    directory["emails"] = directory.get("emails", "").fillna("")
    directory["phones"] = directory.apply(lambda r: _join_unique([r["source_phones"], r["verified_phone"]]), axis=1)
    return directory[["ntn", "phones", "emails"]].drop_duplicates("ntn")


def exporter_portfolio(universe: pd.DataFrame, ntn: str, contacts: pd.DataFrame | None = None) -> DeepDiveResult:
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

    directory = build_verified_contact_directory(universe, contacts)
    contact = directory[directory["ntn"].eq(ntn_key)]
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


def hs8_exporters(universe: pd.DataFrame, hs8_code: str, contacts: pd.DataFrame | None = None) -> DeepDiveResult:
    code = re.sub(r"\D", "", str(hs8_code))
    if not re.fullmatch(r"\d{8}", code):
        raise ValueError("HS8 search requires an exact 8-digit code.")
    rows = universe[universe["hs8"].astype("string").eq(code)].copy()
    if rows.empty:
        raise KeyError(f"HS8 {code} was not found in the loaded cross-chapter universe.")

    rows["_entity_key"] = np.where(rows["_ntn_key"].ne(""), "NTN:" + rows["_ntn_key"], "NAME:" + rows["_exporter_key"])
    total = float(rows["exported_value_rs"].sum())
    directory = build_verified_contact_directory(universe, contacts).set_index("ntn") if len(universe) else pd.DataFrame()

    company_rows: list[dict] = []
    for entity_key, group in rows.groupby("_entity_key", dropna=False, sort=False):
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
