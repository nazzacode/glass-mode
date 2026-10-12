"""scaffold bookkeeping (no browser): registry order — the first match wins, so a new style must precede old entries"""
import json

from tools.glasslab import discover

REG = '{\r\n\t"supportedWebsites": [\r\n\t\t{\r\n\t\t\t"name": "Old",\r\n\t\t\t"matches": ["[^ ]*://[^ ]*.?example.com/[^ ]*"],\r\n\t\t\t"css": ["./styles/websites/example.css"]\r\n\t\t}\r\n\t]\r\n}\r\n'


def test_new_site_precedes_old_entries_and_keeps_crlf(tmp_path):
    p = tmp_path / "ContentScripts.json"
    p.write_bytes(REG.encode())
    assert discover.add_registry("Example", "example.com", "example.com.css", False, path=p)
    raw = p.read_bytes().decode()
    sites = json.loads(raw)["supportedWebsites"]
    assert [s["name"] for s in sites] == ["Example", "Old"]
    assert sites[0]["matches"] == ["^https?://(www\\.)?example\\.com/"]
    assert "\n" not in raw.replace("\r\n", "")


def test_registering_twice_is_a_no_op(tmp_path):
    p = tmp_path / "ContentScripts.json"
    p.write_bytes(REG.encode())
    discover.add_registry("Example", "example.com", "example.com.css", False, path=p)
    assert not discover.add_registry("Example", "example.com", "example.com.css", False, path=p)
