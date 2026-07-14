"""SEB config: SEB-JSON serializer, Config Key, .seb builder, header verify (AD-56)."""
import hashlib
import plistlib
from types import SimpleNamespace

from app.core import seb_config as sc


# --- SEB-JSON serializer rules ----------------------------------------------

def test_seb_json_sorts_keys_case_insensitive_no_whitespace():
    out = sc.seb_json({"Banana": 1, "apple": 2})
    assert out == '{"apple":2,"Banana":1}'


def test_seb_json_booleans_lowercase():
    assert sc.seb_json({"a": True, "b": False}) == '{"a":true,"b":false}'


def test_seb_json_removes_originator_version_top_level():
    assert sc.seb_json({"originatorVersion": "SEB_3", "a": 1}) == '{"a":1}'


def test_seb_json_removes_empty_dicts_but_keeps_empty_arrays():
    assert sc.seb_json({"x": {}, "y": [], "z": 1}) == '{"y":[],"z":1}'


def test_seb_json_nested_dicts_sorted_recursively():
    assert sc.seb_json({"a": {"d": 1, "b": 2}}) == '{"a":{"b":2,"d":1}}'


def test_config_key_is_sha256_hex_of_seb_json():
    settings = {"startURL": "http://x/thisinh/", "a": True}
    expected = hashlib.sha256(sc.seb_json(settings).encode("utf-8")).hexdigest()
    assert sc.config_key(settings) == expected
    assert len(sc.config_key(settings)) == 64


# --- .seb file + template ---------------------------------------------------

def test_build_seb_is_valid_plist_with_start_url():
    data = sc.build_seb("http://host/thisinh/")
    parsed = plistlib.loads(data)
    assert parsed["startURL"] == "http://host/thisinh/"
    # Quit allowed (Ctrl+Q) but gated by the quit password + hidden taskbar.
    assert parsed["allowQuit"] is True
    assert parsed["showTaskBar"] is False
    assert parsed["URLFilterEnable"] is True


def test_template_disables_windows_hotkeys():
    s = sc.seb_settings("http://host/thisinh/")
    for k in ("enableAltTab", "enableAltF4", "enableStartMenu", "enableEsc", "enableF1"):
        assert s[k] is False


def test_template_fullscreen_kiosk_blocks_minimize():
    s = sc.seb_settings("http://host/thisinh/")
    assert s["browserViewMode"] == 1            # fullscreen -> no minimize button
    # Kiosk = "Create new desktop" (SEB 2.4.1 default; AD-63) — isolated desktop,
    # no taskbar/other apps to switch to.
    assert s["createNewDesktop"] is True
    assert s["killExplorerShell"] is False
    assert s["allowSwitchToApplications"] is False
    assert s["showTaskBar"] is False


def test_build_exam_seb_embeds_fixed_passwords():
    data = sc.build_exam_seb("http://host/thisinh/")
    parsed = plistlib.loads(data)
    assert parsed["startURL"] == "http://host/thisinh/"
    assert parsed["allowQuit"] is True
    # Quit + admin passwords default to the fixed constants, hashed.
    assert parsed["hashedQuitPassword"] == hashlib.sha256(sc.QUIT_PASSWORD.encode()).hexdigest()
    assert parsed["hashedAdminPassword"] == hashlib.sha256(sc.ADMIN_PASSWORD.encode()).hexdigest()


def test_build_seb_embeds_password_hashes():
    data = sc.build_seb("http://host/thisinh/", quit_password="thoat123", admin_password="admin123")
    parsed = plistlib.loads(data)
    assert parsed["hashedQuitPassword"] == hashlib.sha256(b"thoat123").hexdigest()
    assert parsed["hashedAdminPassword"] == hashlib.sha256(b"admin123").hexdigest()
    assert len(parsed["hashedQuitPassword"]) == 64
    # No password args -> hashes absent.
    assert "hashedQuitPassword" not in plistlib.loads(sc.build_seb("http://h/t/"))


# --- header verification ----------------------------------------------------

def _fake_request(headers: dict, path: str = "/api/exam/state", query: str = ""):
    lower = {k.lower(): v for k, v in headers.items()}
    return SimpleNamespace(
        headers=SimpleNamespace(get=lambda k, d=None: lower.get(k.lower(), d)),
        url=SimpleNamespace(path=path, query=query),
    )


def test_absolute_url_from_forwarded_headers():
    req = _fake_request({"X-Forwarded-Proto": "http", "X-Forwarded-Host": "exam-server.local"})
    assert sc.absolute_url(req) == "http://exam-server.local/api/exam/state"


def test_verify_seb_header_accepts_correct_hash():
    url = "http://exam-server.local/api/exam/state"
    ck = "abc123"
    good = hashlib.sha256((url + ck).encode()).hexdigest()
    req = _fake_request({
        "X-Forwarded-Proto": "http", "X-Forwarded-Host": "exam-server.local",
        "X-SafeExamBrowser-ConfigKeyHash": good,
    })
    assert sc.verify_seb_header(req, ck) is True


def test_verify_seb_header_rejects_missing_or_wrong():
    req_missing = _fake_request({"X-Forwarded-Proto": "http", "X-Forwarded-Host": "exam-server.local"})
    assert sc.verify_seb_header(req_missing, "abc123") is False
    req_wrong = _fake_request({
        "X-Forwarded-Proto": "http", "X-Forwarded-Host": "exam-server.local",
        "X-SafeExamBrowser-ConfigKeyHash": "deadbeef",
    })
    assert sc.verify_seb_header(req_wrong, "abc123") is False


def test_presence_mode_accepts_any_seb_header_rejects_plain_browser():
    # ck="" -> presence mode (universal .seb, AD-59).
    plain = _fake_request({"X-Forwarded-Host": "exam-server.local"})
    assert sc.verify_seb_header(plain, "") is False
    by_config_key = _fake_request({"X-SafeExamBrowser-ConfigKeyHash": "whatever"})
    assert sc.verify_seb_header(by_config_key, "") is True
    by_request_hash = _fake_request({"X-SafeExamBrowser-RequestHash": "whatever"})
    assert sc.verify_seb_header(by_request_hash, "") is True


def test_is_seb_request_detects_either_header():
    assert sc.is_seb_request(_fake_request({"X-SafeExamBrowser-RequestHash": "x"})) is True
    assert sc.is_seb_request(_fake_request({"User-Agent": "Chrome"})) is False
