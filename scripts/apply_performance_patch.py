from pathlib import Path


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    return text.replace(old, new, 1)


path = Path("app.py")
text = path.read_text(encoding="utf-8")

text = replace_once(
    text,
    "from src.deep_dive import exporter_portfolio, find_exporters, hs8_exporters, load_cross_chapter_universe\n",
    "from src.deep_dive import load_cross_chapter_universe\nfrom src.deep_dive_fast import build_fast_indexes, exporter_portfolio_fast, find_exporters_fast, hs8_exporters_fast, load_cross_chapter_cache\n",
    "deep-dive imports",
)
text = replace_once(
    text,
    'LOGO_FILE = Path("assets/ncgcl_logo.png")\n',
    'LOGO_FILE = Path("assets/ncgcl_logo.png")\nDEEP_CACHE_FILE = Path("data/cross_chapter_universe.csv.gz")\nDEEP_CACHE_MANIFEST = Path("data/cross_chapter_universe.manifest.json")\n',
    "cache constants",
)

old_cache = '''@st.cache_data(show_spinner=False)\ndef _cross_chapter_from_path(path_string: str):\n    return load_cross_chapter_universe(Path(path_string))\n\n\n@st.cache_data(show_spinner=False)\ndef _cross_chapter_from_bytes(payload: bytes):\n    return load_cross_chapter_universe(BytesIO(payload))\n'''
new_cache = '''@st.cache_data(show_spinner=False)\ndef _chapter_sheets_from_path(path_string: str, mtime_ns: int):\n    return _chapter_sheets(Path(path_string))\n\n\n@st.cache_data(show_spinner=False)\ndef _chapter_sheets_from_bytes(payload: bytes):\n    return _chapter_sheets(BytesIO(payload))\n\n\n@st.cache_data(show_spinner=False)\ndef _selected_sheet_from_path(path_string: str, mtime_ns: int, sheet_name: str | None):\n    return load_excel(Path(path_string), sheet_name=sheet_name)\n\n\n@st.cache_data(show_spinner=False)\ndef _selected_sheet_from_bytes(payload: bytes, sheet_name: str | None):\n    return load_excel(BytesIO(payload), sheet_name=sheet_name)\n\n\n@st.cache_data(show_spinner=False)\ndef _contacts_from_path(path_string: str, mtime_ns: int):\n    return load_contact_workbook(Path(path_string))\n\n\n@st.cache_data(show_spinner=False)\ndef _contacts_from_bytes(payload: bytes):\n    return load_contact_workbook(BytesIO(payload))\n\n\n@st.cache_data(show_spinner=False)\ndef _cross_chapter_from_path(path_string: str, mtime_ns: int):\n    return load_cross_chapter_universe(Path(path_string))\n\n\n@st.cache_data(show_spinner=False)\ndef _cross_chapter_from_bytes(payload: bytes):\n    return load_cross_chapter_universe(BytesIO(payload))\n\n\n@st.cache_data(show_spinner=False)\ndef _cross_chapter_repo_cache(source_path: str, source_mtime_ns: int, cache_path: str, cache_mtime_ns: int, manifest_path: str, manifest_mtime_ns: int):\n    return load_cross_chapter_cache(Path(source_path), Path(cache_path), Path(manifest_path))\n\n\n@st.cache_data(show_spinner=False)\ndef _deep_indexes_cached(universe: pd.DataFrame, contacts: pd.DataFrame | None):\n    return build_fast_indexes(universe, contacts)\n'''
text = replace_once(text, old_cache, new_cache, "cache wrappers")

text = replace_once(
    text,
    "    valid_sheets = _chapter_sheets(source)\n",
    '''    source_payload = source.getvalue() if hasattr(source, "getvalue") else None\n    source_mtime_ns = None if source_payload is not None else source.stat().st_mtime_ns\n    if source_payload is not None:\n        valid_sheets = _chapter_sheets_from_bytes(source_payload)\n    else:\n        valid_sheets = _chapter_sheets_from_path(str(source), source_mtime_ns)\n''',
    "cached chapter discovery",
)

text = replace_once(
    text,
    "raw, sheet = load_excel(source, sheet_name=selected_sheet)\n",
    '''if source_payload is not None:\n    raw, sheet = _selected_sheet_from_bytes(source_payload, selected_sheet)\nelse:\n    raw, sheet = _selected_sheet_from_path(str(source), source_mtime_ns, selected_sheet)\n''',
    "cached selected sheet",
)

text = replace_once(
    text,
    "        contacts = load_contact_workbook(contact_source)\n",
    '''        if hasattr(contact_source, "getvalue"):\n            contacts = _contacts_from_bytes(contact_source.getvalue())\n        else:\n            contacts = _contacts_from_path(str(contact_source), contact_source.stat().st_mtime_ns)\n''',
    "cached contacts",
)

old_deep = '''    if hasattr(deep_source, "getvalue"):\n        deep_universe, deep_audit = _cross_chapter_from_bytes(deep_source.getvalue())\n    else:\n        deep_universe, deep_audit = _cross_chapter_from_path(str(deep_source))\nexcept Exception as exc:\n    deep_dive_error = str(exc)\n'''
new_deep = '''    if hasattr(deep_source, "getvalue"):\n        deep_universe, deep_audit = _cross_chapter_from_bytes(deep_source.getvalue())\n    else:\n        deep_stamp = deep_source.stat().st_mtime_ns\n        cached_pair = None\n        if Path(deep_source) == MASTER_FILE and DEEP_CACHE_FILE.exists() and DEEP_CACHE_MANIFEST.exists():\n            cached_pair = _cross_chapter_repo_cache(\n                str(MASTER_FILE), deep_stamp,\n                str(DEEP_CACHE_FILE), DEEP_CACHE_FILE.stat().st_mtime_ns,\n                str(DEEP_CACHE_MANIFEST), DEEP_CACHE_MANIFEST.stat().st_mtime_ns,\n            )\n        if cached_pair is not None:\n            deep_universe, deep_audit = cached_pair\n            deep_source_mode += " · validated fast cache"\n        else:\n            deep_universe, deep_audit = _cross_chapter_from_path(str(deep_source), deep_stamp)\nexcept Exception as exc:\n    deep_dive_error = str(exc)\n\ndeep_exporter_index = pd.DataFrame()\ndeep_contact_directory = pd.DataFrame()\nif deep_universe is not None:\n    deep_exporter_index, deep_contact_directory = _deep_indexes_cached(deep_universe, contacts)\n'''
text = replace_once(text, old_deep, new_deep, "validated deep cache")

old_exporter_input = '''            exporter_query = st.text_input("Search exporter", placeholder="Type company name or NTN", key="deep_exporter_query")\n            if exporter_query.strip():\n                matches = find_exporters(deep_universe, exporter_query)\n'''
new_exporter_input = '''            with st.form("deep_exporter_search_form", clear_on_submit=False):\n                exporter_input = st.text_input("Search exporter", placeholder="Type company name or NTN", key="deep_exporter_query_input")\n                exporter_submit = st.form_submit_button("Search exporter")\n            if exporter_submit:\n                st.session_state["deep_exporter_committed_query"] = exporter_input.strip()\n            exporter_query = st.session_state.get("deep_exporter_committed_query", "")\n            if exporter_query:\n                matches = find_exporters_fast(deep_exporter_index, exporter_query)\n'''
text = replace_once(text, old_exporter_input, new_exporter_input, "exporter search form")
text = text.replace('key="deep_exporter_select")', 'key=f"deep_exporter_select_{exporter_query}")')
text = replace_once(
    text,
    "                    profile = exporter_portfolio(deep_universe, option_map[selected_exporter], contacts)\n",
    "                    profile = exporter_portfolio_fast(deep_universe, option_map[selected_exporter], deep_contact_directory)\n",
    "fast exporter profile",
)

old_hs8_input = '''            hs8_query = st.text_input("Enter exact HS8 code", placeholder="e.g. 12074000", key="deep_hs8_query")\n            if hs8_query.strip():\n                digits = re.sub(r"\\D", "", hs8_query)\n'''
new_hs8_input = '''            with st.form("deep_hs8_search_form", clear_on_submit=False):\n                hs8_input = st.text_input("Enter exact HS8 code", placeholder="e.g. 12074000", key="deep_hs8_query_input")\n                hs8_submit = st.form_submit_button("Search HS8")\n            if hs8_submit:\n                st.session_state["deep_hs8_committed_query"] = hs8_input.strip()\n            hs8_query = st.session_state.get("deep_hs8_committed_query", "")\n            if hs8_query:\n                digits = re.sub(r"\\D", "", hs8_query)\n'''
text = replace_once(text, old_hs8_input, new_hs8_input, "HS8 search form")
text = replace_once(
    text,
    "                        profile = hs8_exporters(deep_universe, digits, contacts)\n",
    "                        profile = hs8_exporters_fast(deep_universe, digits, deep_contact_directory)\n",
    "fast HS8 profile",
)

# Consistent two-decimal percentage presentation. Calculations remain full precision.
text = text.replace("{c['top10_share']*100:.0f}%", "{c['top10_share']*100:.2f}%")
text = text.replace('tickformat=".0%"', 'tickformat=".2%"')
text = text.replace('format="%.1%%"', 'format="%.2%%"')
text = text.replace(
    'hover_data=[x for x in ["product_name", "exporters", "share"] if x in hs8]',
    'hover_data={"product_name": True, "exporters": True, "share": ":.2%"}',
)

path.write_text(text, encoding="utf-8")

# Extend smoke guards without changing analytical tests.
test_path = Path("tests/test_app_smoke.py")
test_text = test_path.read_text(encoding="utf-8")
append = '''\n\ndef test_performance_cache_forms_and_percentage_precision():\n    source = Path("app.py").read_text(encoding="utf-8")\n    assert "_chapter_sheets_from_path" in source\n    assert "_selected_sheet_from_path" in source\n    assert "_contacts_from_path" in source\n    assert "_cross_chapter_repo_cache" in source\n    assert "validated fast cache" in source\n    assert 'st.form("deep_exporter_search_form"' in source\n    assert 'st.form("deep_hs8_search_form"' in source\n    assert "find_exporters_fast" in source\n    assert "exporter_portfolio_fast" in source\n    assert "hs8_exporters_fast" in source\n    assert "{c['top10_share']*100:.2f}%" in source\n    assert 'tickformat=".2%"' in source\n    assert 'format="%.1%%"' not in source\n'''
if "test_performance_cache_forms_and_percentage_precision" not in test_text:
    test_path.write_text(test_text.rstrip() + append + "\n", encoding="utf-8")

print("Performance patch applied successfully")
