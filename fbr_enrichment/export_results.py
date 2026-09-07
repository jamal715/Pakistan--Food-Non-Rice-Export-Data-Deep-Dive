from __future__ import annotations

import json
import sqlite3
from pathlib import Path

import pandas as pd

from config import FINAL_WORKBOOK, OUTPUT_DIR, STATE_DB

MASTER_COLUMNS = [
    "ntn", "legal_name_fbr", "principal_activity_raw", "reference_no", "taxpayer_category",
    "registered_for_sales_tax", "sales_tax_registered_since", "registered_on", "tax_office",
    "income_tax_status", "sales_tax_status", "registered_address", "masked_email_fbr",
    "masked_cell_fbr", "business_names", "business_addresses", "activity_codes",
    "source_exporter_names", "source_chapters", "identity_status", "name_match_status",
    "name_match_score", "collection_status", "verification_date", "source_url",
]


def _payload_frame(conn: sqlite3.Connection) -> pd.DataFrame:
    source = pd.read_sql_query(
        """
        SELECT ntn,
               GROUP_CONCAT(DISTINCT exporter_name) AS source_exporter_names,
               GROUP_CONCAT(DISTINCT chapter) AS source_chapters
        FROM ntn_source
        GROUP BY ntn
        """, conn, dtype={"ntn": str}
    )
    profiles = pd.read_sql_query("SELECT * FROM profile", conn, dtype={"ntn": str})
    activities = pd.read_sql_query("SELECT * FROM business_activity", conn, dtype={"ntn": str})

    if profiles.empty:
        out = source.copy()
        out["collection_status"] = "pending"
        for col in MASTER_COLUMNS:
            if col not in out:
                out[col] = pd.NA
        return out[MASTER_COLUMNS]

    payload_rows = []
    for _, r in profiles.iterrows():
        payload = json.loads(r.get("payload_json") or "{}")
        payload["ntn"] = r["ntn"]
        payload["identity_status"] = r.get("identity_status")
        payload["name_match_status"] = r.get("name_match_status")
        payload["name_match_score"] = r.get("name_match_score")
        payload["collection_status"] = r.get("status")
        payload["verification_date"] = r.get("verified_at")
        payload_rows.append(payload)
    parsed = pd.DataFrame(payload_rows)

    if not activities.empty:
        summary = activities.groupby("ntn", as_index=False).agg(
            principal_activity_raw=("principal_activity_raw", lambda s: " | ".join(dict.fromkeys(str(x).strip() for x in s.dropna() if str(x).strip()))),
            business_names=("business_name", lambda s: " | ".join(dict.fromkeys(str(x).strip() for x in s.dropna() if str(x).strip()))),
            business_addresses=("business_address", lambda s: " | ".join(dict.fromkeys(str(x).strip() for x in s.dropna() if str(x).strip()))),
            activity_codes=("activity_code", lambda s: " | ".join(dict.fromkeys(str(x).strip() for x in s.dropna() if str(x).strip()))),
        )
        parsed = parsed.merge(summary, on="ntn", how="left")

    out = source.merge(parsed, on="ntn", how="left")
    out["collection_status"] = out["collection_status"].fillna("pending")
    for col in MASTER_COLUMNS:
        if col not in out:
            out[col] = pd.NA
    return out[MASTER_COLUMNS].sort_values("ntn").reset_index(drop=True)


def export_results(state_db: Path = STATE_DB, final_workbook: Path = FINAL_WORKBOOK) -> Path:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(state_db)
    try:
        master = _payload_frame(conn)
        activities = pd.read_sql_query(
            """
            SELECT a.ntn, p.identity_status, json_extract(p.payload_json, '$.legal_name_fbr') AS legal_name_fbr,
                   a.business_sr, a.business_name, a.business_address, a.activity_code,
                   a.activity_level_1, a.activity_level_2, a.activity_detail, a.principal_activity_raw
            FROM business_activity a
            LEFT JOIN profile p ON p.ntn=a.ntn
            ORDER BY a.ntn, CAST(a.business_sr AS INTEGER), a.business_sr
            """, conn, dtype={"ntn": str}
        )
        source_rows = pd.read_sql_query("SELECT * FROM ntn_source", conn, dtype={"ntn": str})
        run_log = pd.read_sql_query("SELECT * FROM run_log ORDER BY id", conn, dtype={"ntn": str})
    finally:
        conn.close()

    all_unique = master[["ntn", "source_exporter_names", "source_chapters", "collection_status", "identity_status"]].copy()

    with pd.ExcelWriter(final_workbook, engine="openpyxl") as writer:
        master.to_excel(writer, sheet_name="Taxpayer_Master", index=False)
        activities.to_excel(writer, sheet_name="Business_Activities", index=False)
        all_unique.to_excel(writer, sheet_name="ALL_UNIQUE_NTN", index=False)
        for chapter in [f"{i:02d}" for i in range(1, 25)]:
            ntns = source_rows.loc[source_rows.chapter == chapter, ["ntn", "exporter_name"]].drop_duplicates()
            view = ntns.merge(master, on="ntn", how="left")
            cols = ["ntn", "exporter_name"] + [c for c in MASTER_COLUMNS if c != "ntn"]
            view[cols].to_excel(writer, sheet_name=f"HS{chapter}", index=False)
        run_log.to_excel(writer, sheet_name="RUN_LOG", index=False)

    print(f"Final workbook written to: {final_workbook}")
    print(master.collection_status.value_counts(dropna=False).to_string())
    return final_workbook


if __name__ == "__main__":
    export_results()
