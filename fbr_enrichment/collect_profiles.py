from __future__ import annotations

import argparse
import re
import time
from datetime import datetime

from playwright.sync_api import Page, TimeoutError as PlaywrightTimeoutError, sync_playwright

from build_ntn_universe import build_ntn_universe
from config import EXPORT_EVERY_N_SUCCESSFUL, FBR_PROFILE_URL, RAW_DIR, SAVE_RAW_HTML, SAVE_SCREENSHOTS, SOURCE_WORKBOOK, STATE_DB
from export_results import export_results
from fbr_parser import parse_profile
from identity import identity_status
from storage import connect, log, pending_ntns, replace_activities, source_names, upsert_profile


def _visible_options(select_locator) -> list[str]:
    try:
        return [x.strip() for x in select_locator.locator("option").all_text_contents()]
    except Exception:
        return []


def open_taxpayer_profile(page: Page) -> None:
    page.goto(FBR_PROFILE_URL, wait_until="domcontentloaded", timeout=60000)
    page.wait_for_timeout(1500)
    candidates = page.get_by_text("Taxpayer Profile Inquiry", exact=True)
    try:
        count = candidates.count()
        if count:
            candidates.nth(count - 1).click(timeout=5000)
            page.wait_for_timeout(1000)
    except Exception:
        pass


def select_ntn_mode(page: Page) -> None:
    selects = page.locator("select:visible")
    for i in range(selects.count()):
        sel = selects.nth(i)
        options = _visible_options(sel)
        if any(x.strip().upper() == "NTN" for x in options):
            try:
                sel.select_option(label="NTN")
                page.wait_for_timeout(500)
                return
            except Exception:
                continue
    raise RuntimeError("Could not locate the visible Parameter Type dropdown containing NTN.")


def fill_query(page: Page, ntn: str, captcha_text: str) -> None:
    select_ntn_mode(page)
    reg = page.locator('input[placeholder="NTN"]:visible')
    if not reg.count():
        reg = page.get_by_text(re.compile(r"^Registration\s*No\.?$", re.I), exact=True).last.locator("xpath=following::input[not(@type='hidden')][1]")
    reg.last.fill(ntn)

    cap = page.locator('input[placeholder="Enter"]:visible')
    if not cap.count():
        cap = page.get_by_text(re.compile(r"^Captcha$", re.I), exact=True).last.locator("xpath=following::input[not(@type='hidden')][1]")
    cap.last.fill(captcha_text)


def click_verify(page: Page) -> None:
    buttons = page.get_by_role("button", name=re.compile(r"verify", re.I))
    if buttons.count():
        buttons.last.click()
        return
    page.get_by_text(re.compile(r"^VERIFY$", re.I), exact=True).last.click()


def wait_for_result(page: Page) -> None:
    page.wait_for_function(
        """() => {
            const t = document.body ? document.body.innerText : '';
            return t.includes('Reference No') && t.includes('Registered On') && t.includes('Registration Status');
        }""",
        timeout=20000,
    )


def save_raw(page: Page, ntn: str) -> tuple[str | None, str | None]:
    RAW_DIR.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    html_path = None
    png_path = None
    if SAVE_RAW_HTML:
        p = RAW_DIR / f"{ntn}_{stamp}.html"
        p.write_text(page.content(), encoding="utf-8")
        html_path = str(p)
    if SAVE_SCREENSHOTS:
        p = RAW_DIR / f"{ntn}_{stamp}.png"
        page.screenshot(path=str(p), full_page=True)
        png_path = str(p)
    return html_path, png_path


def collect_one(page: Page, ntn: str):
    open_taxpayer_profile(page)
    try:
        select_ntn_mode(page)
        reg = page.locator('input[placeholder="NTN"]:visible')
        if reg.count():
            reg.last.fill(ntn)
    except Exception:
        print("Automatic form selection did not complete. In the browser, open 'Taxpayer Profile Inquiry', choose NTN and paste the NTN shown below.")

    print("\n" + "=" * 72)
    print(f"NTN: {ntn}")
    print("Read the CAPTCHA shown in the browser and type it here. The script will submit the query.")
    captcha = input("CAPTCHA (or type SKIP / QUIT): ").strip()
    if captcha.upper() == "QUIT":
        raise KeyboardInterrupt
    if captcha.upper() == "SKIP" or not captcha:
        raise RuntimeError("Skipped by user")

    fill_query(page, ntn, captcha)
    click_verify(page)
    wait_for_result(page)

    html = page.content()
    body_text = page.locator("body").inner_text()
    master, activities = parse_profile(html, body_text, ntn)
    if not master.get("registration_no") and not master.get("reference_no"):
        raise RuntimeError("FBR result was visible but the parser could not extract Registration/Reference No.")
    html_path, png_path = save_raw(page, ntn)
    return master, activities, html_path, png_path


def run(limit: int | None = None, only_ntn: str | None = None) -> None:
    if not SOURCE_WORKBOOK.exists():
        raise FileNotFoundError(f"Missing source workbook: {SOURCE_WORKBOOK}")
    build_ntn_universe(SOURCE_WORKBOOK)

    successful = 0
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(viewport={"width": 1500, "height": 950})
        page = context.new_page()
        try:
            with connect(STATE_DB) as conn:
                queue = pending_ntns(conn)
            if only_ntn:
                queue = [n for n in queue if n == str(only_ntn)]
            if limit is not None:
                queue = queue[:limit]

            total = len(queue)
            for idx, ntn in enumerate(queue, 1):
                print(f"\n[{idx:,}/{total:,}] Processing NTN {ntn}")
                try:
                    master, activities, html_path, png_path = collect_one(page, ntn)
                    with connect(STATE_DB) as conn:
                        names = source_names(conn, ntn)
                        business_names = activities.business_name.dropna().astype(str).tolist() if not activities.empty else []
                        status, name_status, name_score = identity_status(
                            ntn, master.get("registration_no"), master.get("reference_no"), names,
                            master.get("legal_name_fbr"), business_names,
                        )
                        master["source_url"] = FBR_PROFILE_URL
                        upsert_profile(
                            conn, ntn, "complete", payload=master, identity_status=status,
                            name_match_status=name_status, name_match_score=name_score,
                            raw_html_path=html_path, screenshot_path=png_path,
                        )
                        replace_activities(conn, ntn, activities)
                        log(conn, ntn, "complete", f"identity={status}; name={name_status}; score={name_score:.3f}")
                    successful += 1
                    print(f"Saved: {master.get('legal_name_fbr')} | identity={status} | activities={len(activities)}")
                    if successful % EXPORT_EVERY_N_SUCCESSFUL == 0:
                        export_results()
                except PlaywrightTimeoutError:
                    with connect(STATE_DB) as conn:
                        upsert_profile(conn, ntn, "failed", error="Timed out waiting for FBR result; CAPTCHA may be wrong or portal slow.")
                        log(conn, ntn, "failed", "timeout")
                    print("Timed out. Record marked failed; rerun later to retry.")
                except RuntimeError as exc:
                    if "Skipped by user" in str(exc):
                        with connect(STATE_DB) as conn:
                            log(conn, ntn, "skipped", str(exc))
                        print("Skipped; it remains in the pending queue.")
                    else:
                        with connect(STATE_DB) as conn:
                            upsert_profile(conn, ntn, "failed", error=str(exc))
                            log(conn, ntn, "failed", str(exc))
                        print(f"Failed: {exc}")
                except KeyboardInterrupt:
                    raise
                except Exception as exc:
                    with connect(STATE_DB) as conn:
                        upsert_profile(conn, ntn, "failed", error=repr(exc))
                        log(conn, ntn, "failed", repr(exc))
                    print(f"Unexpected failure: {exc!r}")
                time.sleep(0.5)
        finally:
            export_results()
            browser.close()


def main():
    parser = argparse.ArgumentParser(description="Human-in-the-loop FBR Taxpayer Profile collector. CAPTCHA is solved by the user; all extraction/checkpointing is automated.")
    parser.add_argument("--limit", type=int, default=None, help="Process at most N pending NTNs.")
    parser.add_argument("--ntn", type=str, default=None, help="Process one specific pending NTN.")
    args = parser.parse_args()
    run(limit=args.limit, only_ntn=args.ntn)


if __name__ == "__main__":
    main()
