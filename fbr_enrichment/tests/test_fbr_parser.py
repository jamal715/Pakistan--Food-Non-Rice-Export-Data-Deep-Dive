import pytest

# The existing dashboard CI intentionally installs only the root requirements.
# Keep those workflows isolated from this optional FBR module, while the
# dedicated FBR workflow installs lxml and runs these parser tests fully.
pytest.importorskip("lxml")

from fbr_parser import parse_profile
from export_results import MASTER_COLUMNS


def test_master_keeps_principal_activity_as_third_column():
    assert MASTER_COLUMNS[:3] == ["ntn", "legal_name_fbr", "principal_activity_raw"]


def test_profile_parser_extracts_sakhi_style_master_and_branch_activity():
    html = """
    <html><body>
      <table>
        <tr><td>Registration No</td><td>2573554</td></tr>
        <tr><td>Reference No</td><td>2573554-3</td></tr>
        <tr><td>Registered for Sales Tax</td><td>Yes. w.e.f. 16-MAR-06</td></tr>
        <tr><td>Name</td><td>SAKHI INTERNATIONAL</td></tr>
        <tr><td>Category</td><td>Firm</td></tr>
        <tr><td>Email</td><td>dil****sak***gmail.com</td></tr>
        <tr><td>Cell</td><td>00923**822**27</td></tr>
        <tr><td>Address</td><td>Plot No.107-C, DHA, Karachi South</td></tr>
        <tr><td>Registered On</td><td>19-JAN-2006</td></tr>
        <tr><td>Tax Office</td><td>LTO KARACHI</td></tr>
        <tr><td>Registration Status</td><td>Income Tax: Active , Sales Tax: OPERATIVE</td></tr>
      </table>
      <table>
        <tr><th>Sr.</th><th>Business/ Branch Name</th><th>Business/ Branch Address</th><th>Principal Activity</th></tr>
        <tr><td>1</td><td>SAKHI INTERNATIONAL</td><td>Port Qasim, Karachi</td><td>107900-Manufacturing/Manufacture of other food products/Manufacture of other food products n.e.c.</td></tr>
        <tr><td>2</td><td>SAKHI INTERNATIONAL</td><td>Karachi South</td><td>050000-Importer/Exporter/Exporter/Exporter</td></tr>
      </table>
    </body></html>
    """
    body = """Registration No\n2573554\nReference No\n2573554-3\nRegistered On\n19-JAN-2006\nTax Office\nLTO KARACHI\nRegistration Status\nIncome Tax: Active , Sales Tax: OPERATIVE"""
    master, activities = parse_profile(html, body, "2573554")
    assert master["registration_no"] == "2573554"
    assert master["reference_no"] == "2573554-3"
    assert master["legal_name_fbr"] == "SAKHI INTERNATIONAL"
    assert master["registered_for_sales_tax"] == "Yes"
    assert master["sales_tax_registered_since"] == "16-MAR-06"
    assert master["income_tax_status"] == "Active"
    assert master["sales_tax_status"] == "OPERATIVE"
    assert len(activities) == 2
    assert activities.iloc[0]["activity_code"] == "107900"
    assert activities.iloc[0]["activity_level_1"] == "Manufacturing"
    assert activities.iloc[1]["principal_activity_raw"] == "050000-Importer/Exporter/Exporter/Exporter"
