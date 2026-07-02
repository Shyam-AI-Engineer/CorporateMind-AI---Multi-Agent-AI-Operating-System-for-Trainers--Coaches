"""Append 3 more tests to hit 110+."""
import pathlib

path = pathlib.Path(__file__).parent / "test_customers_service.py"

extra = r"""

# ── Service key helpers ───────────────────────────────────────────────────────

class TestCacheKeyHelpers:
    def test_list_key_format(self):
        from corpmind.modules.customers.service import _list_key
        k = _list_key(_ORG, _WS)
        assert k.startswith(f"t:{_ORG}:")
        assert "customers:list" in k

    def test_detail_key_format(self):
        from corpmind.modules.customers.service import _detail_key
        k = _detail_key(_ORG, _CID)
        assert f"customers:detail:{_CID}" in k

    def test_list_and_detail_keys_differ(self):
        from corpmind.modules.customers.service import _list_key, _detail_key
        assert _list_key(_ORG, _WS) != _detail_key(_ORG, _CID)
"""

with open(path, "a", encoding="utf-8") as f:
    f.write(extra)
print("ok")
