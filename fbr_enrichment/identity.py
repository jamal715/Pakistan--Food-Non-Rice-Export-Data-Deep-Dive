from __future__ import annotations

import re
from difflib import SequenceMatcher


def normalize_ntn(value) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text or text.lower() in {"nan", "none", "<na>"}:
        return None
    text = re.sub(r"\.0$", "", text)
    digits = re.sub(r"\D", "", text)
    return digits or None


def normalize_name(value) -> str:
    if value is None:
        return ""
    text = str(value).upper().strip()
    replacements = {
        "PRIVATE LIMITED": "PVT LTD",
        "(PRIVATE) LIMITED": "PVT LTD",
        "(PVT.) LTD.": "PVT LTD",
        "(PVT) LTD": "PVT LTD",
        "LIMITED": "LTD",
        "M/S ": "",
        "M/S. ": "",
    }
    for old, new in replacements.items():
        text = text.replace(old, new)
    text = re.sub(r"[^A-Z0-9]+", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def ntn_matches_profile(queried_ntn: str, registration_no: str | None, reference_no: str | None) -> bool:
    q = normalize_ntn(queried_ntn)
    reg = normalize_ntn(registration_no)
    ref = normalize_ntn(str(reference_no).split("-")[0]) if reference_no else None
    return bool(q and (q == reg or q == ref))


def best_name_match(source_names: list[str], legal_name: str | None, business_names: list[str]) -> tuple[str, float]:
    candidates = [legal_name or "", *business_names]
    best_label = "no_name_match"
    best_score = 0.0
    for source in source_names:
        s = normalize_name(source)
        if not s:
            continue
        for candidate in candidates:
            c = normalize_name(candidate)
            if not c:
                continue
            if s == c:
                return "exact", 1.0
            if s in c or c in s:
                score = min(len(s), len(c)) / max(len(s), len(c))
                if score > best_score:
                    best_label, best_score = "contained", score
            score = SequenceMatcher(None, s, c).ratio()
            if score > best_score:
                best_label, best_score = "fuzzy", score
    return best_label, best_score


def identity_status(
    queried_ntn: str,
    registration_no: str | None,
    reference_no: str | None,
    source_names: list[str],
    legal_name: str | None,
    business_names: list[str],
) -> tuple[str, str, float]:
    if not ntn_matches_profile(queried_ntn, registration_no, reference_no):
        return "manual_review", "ntn_mismatch", 0.0
    label, score = best_name_match(source_names, legal_name, business_names)
    if label == "exact" or score >= 0.82:
        return "verified", label, score
    return "manual_review", label, score
