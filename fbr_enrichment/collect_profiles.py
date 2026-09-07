from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime
from pathlib import Path
import json
import re
import time

import pandas as pd
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright, Page

OUTPUT_DIR = Path(r"C:\Users\jamal.nasir_ncgcl\OneDrive\OneDrive - Higher Education Commission\NCGCL\Export Facility")
WORKBOOK = OUTPUT_DIR / "FBR_Exporter_Verification_HS01_24.xlsx"
CHECKPOINT_DIR = OUTPUT_DIR / "fbr_profile_checkpoints"
RAW_DIR = CHECKPOINT_DIR / "raw_html"
PROFILE_DIR = CHECKPOINT_DIR / "profiles"
FBR_URL = "https://iris.fbr.gov.pk/public/txplogin.xhtml"
SOURCE_LABEL = "FBR Taxpayer Profile Inquiry"

MASTER_COLUMNS = [
    "ntn", "legal_name_fbr", "principal_activity_raw", "reference_no",
    "taxpayer_category", "registered_for_sales_tax", "sales_tax_registered_since",
    "registered_on", "tax_office", "income_tax_status", "sales_tax_status",
    "registered_address", "masked_email_fbr", "masked_cell_fbr",
    "verification_date", "source",
]

ACTIVITY_COLUMNS = [
    "ntn", "legal_name_fbr", "business_name", "business_address", "activity_code",
    "activity_level_1", "activity_level_2", "activity_detail", "principal_activity_raw",
]


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def clean(value) -> str | None:
    if value is None or pd.isna(value):
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def digits(value) -> str:
    return re.sub(r"\D", "", str(value or ""))


def normalize_ntn(value) -> str:
    x = digits(value).lstrip("0")
    return x or "0"


def reconcile_identity(queried_ntn: str, registration_no: str | None, reference_no: str | None) -> tuple[bool, str]:
    q = normalize_ntn(queried_ntn)
    reg = normalize_ntn(registration_no) if registration_no else ""
    ref_digits = digits(reference_no)
    # FBR reference numbers commonly begin with the 7-digit NTN followed by a suffix.
    ref_prefix = normalize_ntn(ref_digits[:7]) if len(ref_digits) >= 7 else ""
    if reg == q or ref_prefix == q:
        return True, "NTN reconciled to FBR registration/reference identity"
    return False, f"Queried NTN {q} did not reconcile to registration={registration_no!r}, reference={reference_no!r}"


def split_registered_for_sales_tax(value: str | None) -> tuple[str | None, str | None]:
    value = clean(value)
    if not value:
        return None, None
    yes_no = "Yes" if value.lower().startswith("yes") else ("No" if value.lower().startswith("no") else value)
    m = re.search(r"w\.?\s*e\.?\s*f\.?\s*([^,;]+)$", value, flags=re.I)
    return yes_no, clean(m.group(1)) if m else None


def split_status(value: str | None) -> tuple[str | None, str | None]:
    value = clean(value)
    if not value:
        return None, None
    income = None
    sales = None
    mi = re.search(r"Income\s*Tax\s*:\s*([^,]+)", value, flags=re.I)
    ms = re.search(r"Sales\s*Tax\s*:\s*([^,]+)", value, flags=re.I)
    if mi:
        income = clean(mi.group(1))
    if ms:
        sales = clean(ms.group(1))
    return income, sales


def parse_activity(raw: str | None) -> dict:
    raw = clean(raw)
    if not raw:
        return {
            "activity_code": None,
            "activity_level_1": None,
            "activity_level_2": None,
            "activity_detail": None,
            "principal_activity_raw": None,
        }
    m = re.match(r"^(\d+)\s*-\s*(.*)$", raw)
    code = m.group(1) if m else None
    body = m.group(2) if m else raw
    levels = [clean(x) for x in body.split("/") if clean(x)]
    return {
        "activity_code": code,
        "activity_level_1": levels[0] if len(levels) > 0 else None,
        "activity_level_2": levels[1] if len(levels) > 1 else None,
        "activity_detail": levels[-1] if levels else None,
        "principal_activity_raw": raw,
    }


def table_cells(soup: BeautifulSoup) -> list[str]:
    return [clean(x.get_text(" ", strip=True)) or "" for x in soup.find_all(["td", "th"])]


def parse_master_fields(html: str) -> dict:
    soup = BeautifulSoup(html, "lxml")
    labels = {
        "Registration No": "registration_no",
        "Reference No": "reference_no",
        "Registered for Sales Tax": "registered_for_sales_tax_raw",
        "Name": "legal_name_fbr",
        "Category": "taxpayer_category",
        "PP/REG/INC No.": "pp_reg_inc_no",
        "Email": "masked_email_fbr",
        "Cell": "masked_cell_fbr",
        "Address": "registered_address",
        "Registered On": "registered_on",
        "Tax Office": "tax_office",
        "Registration Status": "registration_status_raw",
    }
    cells = table_cells(soup)
    out: dict[str, str | None] = {v: None for v in labels.values()}
    for i, value in enumerate(cells[:-1]):
        normalized = re.sub(r"\s+", " ", value).strip().rstrip(":")
        for label, key in labels.items():
            if normalized.lower() == label.lower():
                out[key] = clean(cells[i + 1])
                break
    return out


def parse_business_activities(html: str, ntn: str, legal_name: str | None) -> list[dict]:
    records: list[dict] = []
    try:
        tables = pd.read_html(html)
    except ValueError:
        return records

    for table in tables:
        cols = [clean(c) or "" for c in table.columns]
        joined = " | ".join(cols).lower()
        if "principal activity" not in joined or "business" not in joined:
            continue

        table.columns = cols
        for _, row in table.iterrows():
            as_text = {str(k): clean(v) for k, v in row.items()}
            activity = next((v for k, v in as_text.items() if "principal activity" in k.lower()), None)
            business_name = next((v for k, v in as_text.items() if "business" in k.lower() and "address" not in k.lower()), None)
            business_address = next((v for k, v in as_text.items() if "address" in k.lower()), None)
            if not any([activity, business_name, business_address]):
                continue
            parsed = parse_activity(activity)
            records.append({
                "ntn": normalize_ntn(ntn),
                "legal_name_fbr": legal_name,
                "business_name": business_name,
                "business_address": business_address,
                **parsed,
            })
    return records


def parse_profile(html: str, queried_ntn: str) -> tuple[dict, list[dict], tuple[bool, str]]:
    raw = parse_master_fields(html)
    st_registered, st_since = split_registered_for_sales_tax(raw.get("registered_for_sales_tax_raw"))
    income_status, sales_status = split_status(raw.get("registration_status_raw"))
    activities = parse_business_activities(html, queried_ntn, raw.get("legal_name_fbr"))
    distinct_raw = []
    seen = set()
    for row in activities:
        value = row.get("principal_activity_raw")
        if value and value not in seen:
            seen.add(value)
            distinct_raw.append(value)

    identity = reconcile_identity(queried_ntn, raw.get("registration_no"), raw.get("reference_no"))
    master = {
        "ntn": normalize_ntn(queried_ntn),
        "legal_name_fbr": raw.get("legal_name_fbr"),
        "principal_activity_raw": " | ".join(distinct_raw) if distinct_raw else None,
        "reference_no": raw.get("reference_no"),
        "taxpayer_category": raw.get("taxpayer_category"),
        "registered_for_sales_tax": st_registered,
        "sales_tax_registered_since": st_since,
        "registered_on": raw.get("registered_on"),
        "tax_office": raw.get("tax_office"),
        "income_tax_status": income_status,
        "sales_tax_status": sales_status,
        "registered_address": raw.get("registered_address"),
        "masked_email_fbr": raw.get("masked_email_fbr"),
        "masked_cell_fbr": raw.get("masked_cell_fbr"),
        "verification_date": now_iso(),
        "source": SOURCE_LABEL,
        "_registration_no": raw.get("registration_no"),
        "_identity_ok": identity[0],
        "_identity_message": identity[1],
    }
    return master, activities, identity


def save_checkpoint(ntn: str, html: str, master: dict, activities: list[dict]) -> None:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    key = normalize_ntn(ntn)
    (RAW_DIR / f"{key}.html").write_text(html, encoding="utf-8")
    payload = {"master": master, "activities": activities}
    (PROFILE_DIR / f"{key}.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def load_checkpoints() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    masters: list[dict] = []
    activities: list[dict] = []
    reviews: list[dict] = []
    if not PROFILE_DIR.exists():
        return pd.DataFrame(columns=MASTER_COLUMNS), pd.DataFrame(columns=ACTIVITY_COLUMNS), pd.DataFrame(columns=["ntn", "reason", "details", "timestamp"])

    for path in sorted(PROFILE_DIR.glob("*.json")):
        payload = json.loads(path.read_text(encoding="utf-8"))
        master = payload.get("master", {})
        if master.get("_identity_ok"):
            masters.append({k: master.get(k) for k in MASTER_COLUMNS})
            activities.extend(payload.get("activities", []))
        else:
            reviews.append({
                "ntn": master.get("ntn"),
                "reason": "identity_mismatch",
                "details": master.get("_identity_message"),
                "timestamp": master.get("verification_date"),
            })
    return (
        pd.DataFrame(masters, columns=MASTER_COLUMNS),
        pd.DataFrame(activities, columns=ACTIVITY_COLUMNS),
        pd.DataFrame(reviews, columns=["ntn", "reason", "details", "timestamp"]),
    )


def rebuild_workbook() -> None:
    if not WORKBOOK.exists():
        raise FileNotFoundError(f"Run extract_ntns.py first: {WORKBOOK}")

    # Preserve the chapter sheets and global queue created by extract_ntns.py.
    existing = pd.read_excel(WORKBOOK, sheet_name=None, dtype={"ntn": "string"})
    master, activities, reviews = load_checkpoints()

    queue = existing.get("ALL_UNIQUE_NTN", pd.DataFrame()).copy()
    completed = set(master.get("ntn", pd.Series(dtype=str)).astype(str))
    manual = set(reviews.get("ntn", pd.Series(dtype=str)).astype(str))
    if not queue.empty:
        queue["ntn"] = queue["ntn"].astype(str).map(normalize_ntn)
        queue["status"] = queue["ntn"].map(lambda x: "completed" if x in completed else ("manual_review" if x in manual else "pending"))

    with pd.ExcelWriter(WORKBOOK, engine="openpyxl", mode="w") as writer:
        master.to_excel(writer, sheet_name="Taxpayer_Master", index=False)
        activities.to_excel(writer, sheet_name="Business_Activities", index=False)
        queue.to_excel(writer, sheet_name="ALL_UNIQUE_NTN", index=False)
        for i in range(1, 25):
            name = f"HS{i:02d}"
            frame = existing.get(name, pd.DataFrame())
            if not frame.empty and "ntn" in frame:
                frame["ntn"] = frame["ntn"].astype(str).map(normalize_ntn)
                if not master.empty:
                    enrich = master[["ntn", "legal_name_fbr", "principal_activity_raw", "registered_address", "masked_email_fbr", "masked_cell_fbr", "income_tax_status", "sales_tax_status"]]
                    frame = frame.drop(columns=[c for c in enrich.columns if c != "ntn" and c in frame.columns], errors="ignore").merge(enrich, on="ntn", how="left", validate="many_to_one")
            frame.to_excel(writer, sheet_name=name, index=False)
        reviews.to_excel(writer, sheet_name="Manual_Review", index=False)
        existing.get("Run_Log", pd.DataFrame(columns=["timestamp", "ntn", "event", "details"])).to_excel(writer, sheet_name="Run_Log", index=False)


def open_taxpayer_profile(page: Page, ntn: str) -> None:
    if "iris.fbr.gov.pk" not in page.url:
        page.goto(FBR_URL, wait_until="domcontentloaded", timeout=120_000)

    # Navigate to Taxpayer Profile Inquiry if the menu item is visible.
    try:
        page.get_by_text("Taxpayer Profile Inquiry", exact=True).first.click(timeout=10_000)
    except Exception:
        pass

    # The FBR frontend changes its component IDs periodically. Use label/text-based candidates.
    filled = False
    for selector in [
        'input[placeholder="NTN"]',
        'input[placeholder="Select"]',
        'input[type="text"]',
    ]:
        try:
            candidates = page.locator(selector)
            for i in range(candidates.count()):
                el = candidates.nth(i)
                if el.is_visible():
                    value = (el.get_attribute("placeholder") or "").lower()
                    if "captcha" in value or "enter" == value:
                        continue
                    el.fill(str(ntn))
                    filled = True
                    break
            if filled:
                break
        except Exception:
            continue

    print(f"\nNTN {ntn}")
    if not filled:
        print("Could not safely identify the Registration No input; enter the NTN manually in the browser.")
    print("Complete FBR's CAPTCHA normally and click VERIFY. When the taxpayer profile is visible, return here and press ENTER.")


def run() -> None:
    if not WORKBOOK.exists():
        raise FileNotFoundError("Run `python fbr_enrichment/extract_ntns.py` first.")

    queue = pd.read_excel(WORKBOOK, sheet_name="ALL_UNIQUE_NTN", dtype={"ntn": "string"})
    PROFILE_DIR.mkdir(parents=True, exist_ok=True)
    already = {p.stem for p in PROFILE_DIR.glob("*.json")}
    pending = [normalize_ntn(x) for x in queue["ntn"].dropna().astype(str) if normalize_ntn(x) not in already]

    print(f"Total NTN universe: {len(queue):,}")
    print(f"Already checkpointed: {len(already):,}")
    print(f"Pending: {len(pending):,}")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page(viewport={"width": 1600, "height": 1000})
        page.goto(FBR_URL, wait_until="domcontentloaded", timeout=120_000)

        for idx, ntn in enumerate(pending, start=1):
            print(f"\n[{idx}/{len(pending)}]")
            open_taxpayer_profile(page, ntn)
            command = input("ENTER=result visible | s=skip | q=quit: ").strip().lower()
            if command == "q":
                break
            if command == "s":
                continue

            html = page.content()
            master, activities, identity = parse_profile(html, ntn)
            if not master.get("legal_name_fbr"):
                print("No taxpayer result was parsed. Nothing saved; retry this NTN later.")
                continue

            save_checkpoint(ntn, html, master, activities)
            print(f"Saved {ntn}: {master.get('legal_name_fbr')} | identity_ok={identity[0]} | activities={len(activities)}")
            if not identity[0]:
                print(f"MANUAL REVIEW: {identity[1]}")

            # Checkpoint is already durable. Rebuild the user-facing workbook every 10 successful profiles.
            if idx % 10 == 0:
                rebuild_workbook()
                print("Workbook refreshed from durable checkpoints.")

        browser.close()

    rebuild_workbook()
    print(f"\nFinal workbook refreshed: {WORKBOOK}")


if __name__ == "__main__":
    run()
