from __future__ import annotations

import html
import re
from dataclasses import dataclass

import pandas as pd


@dataclass
class ContactEnrichmentAudit:
    contact_rows_for_chapter: int
    contact_keys_for_chapter: int
    safe_phone_keys: int
    no_phone_keys: int
    ambiguous_contact_keys: int
    ambiguous_identity_keys: int
    target_rows: int
    rows_with_source_phone: int
    rows_with_verified_sidecar_phone: int
    rows_without_phone: int


def _clean_name(value) -> str:
    if pd.isna(value):
        return ""
    text = html.unescape(str(value))
    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text).strip().upper()
    return text


def _clean_chapter(value) -> str:
    if pd.isna(value):
        return ""
    digits = re.sub(r"\D", "", str(value))
    return digits.zfill(2) if digits else ""


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


def load_contact_workbook(file_or_path) -> pd.DataFrame:
    """Load the user-maintained contact sidecar without coercing phone numbers to numeric values."""
    if str(file_or_path).lower().endswith(".csv"):
        contacts = pd.read_csv(file_or_path, dtype="string")
    else:
        contacts = pd.read_excel(file_or_path, dtype="string")
    required = {"HS_Chapter", "exporter_name", "telephone"}
    missing = sorted(required - set(contacts.columns))
    if missing:
        raise ValueError("Contact workbook is missing required columns: " + ", ".join(missing))
    return contacts[["HS_Chapter", "exporter_name", "telephone"]].copy()


def _safe_identity_phone_map(contacts: pd.DataFrame, raw_df: pd.DataFrame, chapter: str) -> tuple[pd.DataFrame, dict]:
    """Create a conservative phone lookup keyed by chapter + exporter + unique NTN.

    The sidecar itself has no NTN. We therefore allow a phone to enter the app only when:
      1) the chapter + normalized exporter name resolves to at most one nonblank phone in the sidecar; and
      2) the same chapter + normalized exporter name resolves to exactly one nonblank NTN in the analytical source.

    This deliberately withholds ambiguous matches rather than guessing.
    """
    ch = _clean_chapter(chapter)

    c = contacts.copy()
    c["_chapter"] = c["HS_Chapter"].map(_clean_chapter)
    c["_exporter_key"] = c["exporter_name"].map(_clean_name)
    c["_phone"] = c["telephone"].map(_clean_phone)
    c = c[c["_chapter"] == ch].copy()

    def contact_group(g: pd.DataFrame) -> pd.Series:
        phones = sorted({x for x in g["_phone"].tolist() if x})
        return pd.Series({
            "contact_rows": int(len(g)),
            "phone_count": int(len(phones)),
            "candidate_phone": phones[0] if len(phones) == 1 else pd.NA,
        })

    contact_keys = c.groupby(["_chapter", "_exporter_key"], dropna=False).apply(contact_group, include_groups=False).reset_index() if len(c) else pd.DataFrame(columns=["_chapter", "_exporter_key", "contact_rows", "phone_count", "candidate_phone"])

    r = raw_df.copy()
    r["_chapter"] = ch
    r["_exporter_key"] = r["exporter_name"].map(_clean_name)
    r["_ntn_key"] = r["ntn"].map(_clean_ntn) if "ntn" in r.columns else ""

    def identity_group(g: pd.DataFrame) -> pd.Series:
        ntns = sorted({x for x in g["_ntn_key"].tolist() if x})
        return pd.Series({
            "ntn_count": int(len(ntns)),
            "verified_ntn": ntns[0] if len(ntns) == 1 else pd.NA,
        })

    identity_keys = r.groupby(["_chapter", "_exporter_key"], dropna=False).apply(identity_group, include_groups=False).reset_index()
    joined = contact_keys.merge(identity_keys, on=["_chapter", "_exporter_key"], how="outer")
    joined["phone_count"] = joined["phone_count"].fillna(0).astype(int)
    joined["ntn_count"] = joined["ntn_count"].fillna(0).astype(int)
    joined["safe"] = joined["phone_count"].eq(1) & joined["ntn_count"].eq(1)

    safe = joined[joined["safe"]].copy()
    safe["_ntn_key"] = safe["verified_ntn"].astype("string")
    safe = safe[["_chapter", "_exporter_key", "_ntn_key", "candidate_phone"]].rename(columns={"candidate_phone": "verified_contact_phone"})

    stats = {
        "contact_rows_for_chapter": int(len(c)),
        "contact_keys_for_chapter": int(len(contact_keys)),
        "safe_phone_keys": int(joined["safe"].sum()),
        "no_phone_keys": int((joined["phone_count"] == 0).sum()),
        "ambiguous_contact_keys": int((joined["phone_count"] > 1).sum()),
        "ambiguous_identity_keys": int((joined["ntn_count"] != 1).sum()),
    }
    return safe, stats


def enrich_contact_display(target: pd.DataFrame, raw_df: pd.DataFrame, contacts: pd.DataFrame, chapter: str) -> tuple[pd.DataFrame, ContactEnrichmentAudit]:
    """Add display-only phone metadata without mutating analytical columns or row counts."""
    original = target.reset_index(drop=True).copy()
    out = original.copy()
    ch = _clean_chapter(chapter)

    safe_map, stats = _safe_identity_phone_map(contacts, raw_df, ch)

    out["_chapter"] = ch
    out["_exporter_key"] = out["exporter_name"].map(_clean_name)
    out["_ntn_key"] = out["ntn"].map(_clean_ntn) if "ntn" in out.columns else ""
    out = out.merge(safe_map, on=["_chapter", "_exporter_key", "_ntn_key"], how="left", validate="many_to_one")

    if len(out) != len(original):
        raise RuntimeError("Contact enrichment changed analytical row count; enrichment aborted.")

    source_phone = original["telephone"].map(_clean_phone) if "telephone" in original.columns else pd.Series([""] * len(original))
    sidecar_phone = out["verified_contact_phone"].map(_clean_phone)
    out["contact_phone"] = source_phone.where(source_phone.ne(""), sidecar_phone)
    out["contact_phone_source"] = ""
    out.loc[source_phone.ne(""), "contact_phone_source"] = "source workbook"
    out.loc[source_phone.eq("") & sidecar_phone.ne(""), "contact_phone_source"] = "verified contact sidecar"

    # Prove that all pre-existing columns are byte-for-byte/value-for-value unchanged.
    for col in original.columns:
        if not original[col].reset_index(drop=True).equals(out[col].reset_index(drop=True)):
            raise RuntimeError(f"Contact enrichment modified existing analytical column: {col}")

    out = out.drop(columns=["_chapter", "_exporter_key", "_ntn_key", "verified_contact_phone"])
    audit = ContactEnrichmentAudit(
        contact_rows_for_chapter=stats["contact_rows_for_chapter"],
        contact_keys_for_chapter=stats["contact_keys_for_chapter"],
        safe_phone_keys=stats["safe_phone_keys"],
        no_phone_keys=stats["no_phone_keys"],
        ambiguous_contact_keys=stats["ambiguous_contact_keys"],
        ambiguous_identity_keys=stats["ambiguous_identity_keys"],
        target_rows=int(len(original)),
        rows_with_source_phone=int((source_phone != "").sum()),
        rows_with_verified_sidecar_phone=int(((source_phone == "") & (sidecar_phone != "")).sum()),
        rows_without_phone=int((out["contact_phone"].map(_clean_phone) == "").sum()),
    )
    return out, audit
