from identity import identity_status, normalize_name, normalize_ntn, ntn_matches_profile


def test_normalize_ntn_preserves_old_short_ntn_without_zero_padding():
    assert normalize_ntn("2573554.0") == "2573554"
    assert normalize_ntn(232421) == "232421"


def test_ntn_identity_accepts_registration_or_reference_base():
    assert ntn_matches_profile("2573554", "2573554", "2573554-3")
    assert ntn_matches_profile("0101280", "4230109543263", "0101280-7")
    assert not ntn_matches_profile("2573554", "3415702", "3415702-3")


def test_name_normalization_handles_common_legal_suffixes():
    assert normalize_name("M/S ABC TRADERS (PRIVATE) LIMITED") == normalize_name("ABC TRADERS PVT LTD")


def test_identity_requires_name_support_before_auto_join():
    result = identity_status(
        "2573554", "2573554", "2573554-3", ["SAKHI INTERNATIONAL"],
        "SAKHI INTERNATIONAL", ["SAKHI INTERNATIONAL"],
    )
    assert result[0] == "verified"

    mismatch = identity_status(
        "2573554", "2573554", "2573554-3", ["COMPLETELY DIFFERENT EXPORTER"],
        "SAKHI INTERNATIONAL", ["SAKHI INTERNATIONAL"],
    )
    assert mismatch[0] == "manual_review"
