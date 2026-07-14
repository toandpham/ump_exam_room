"""Safe Exam Browser config: build the .seb file + compute the Config Key.

The Config Key is a SHA-256 over a canonical "SEB-JSON" serialization of the
settings dict, per https://safeexambrowser.org/developer/seb-config-key.html:
keys sorted case-insensitively & recursively, no whitespace, no escaping,
booleans lowercase, <data>->base64, <date>->ISO8601, empty <dict> removed, and
the top-level key ``originatorVersion`` removed. Per request SEB sends
``X-SafeExamBrowser-ConfigKeyHash = SHA256(absoluteURL_without_fragment + ConfigKey)``.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import plistlib
from datetime import datetime
from functools import lru_cache

from app.config import settings as _app_settings

CONFIG_KEY_HEADER = "X-SafeExamBrowser-ConfigKeyHash"
REQUEST_HASH_HEADER = "X-SafeExamBrowser-RequestHash"


# --- SEB-JSON serialization -------------------------------------------------

def _fmt_float(f: float) -> str:
    # JSON-style shortest round-trip; our template avoids floats but be safe.
    return repr(float(f))


def _val(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, int):
        return str(v)
    if isinstance(v, float):
        return _fmt_float(v)
    if isinstance(v, str):
        return f'"{v}"'  # SEB: no character escaping
    if isinstance(v, bytes):
        return f'"{base64.b64encode(v).decode()}"'
    if isinstance(v, datetime):
        return f'"{v.isoformat()}"'
    if isinstance(v, list):
        return "[" + ",".join(_val(x) for x in v) + "]"
    if isinstance(v, dict):
        return _obj(v)
    raise TypeError(f"Unsupported SEB-JSON type: {type(v)}")


def _obj(d: dict) -> str:
    parts = []
    for k in sorted(d.keys(), key=str.lower):
        v = d[k]
        if isinstance(v, dict):
            if not v:
                continue  # remove empty dicts
            parts.append(f'"{k}":{_obj(v)}')
        else:
            parts.append(f'"{k}":{_val(v)}')
    return "{" + ",".join(parts) + "}"


def seb_json(settings: dict) -> str:
    """Canonical SEB-JSON string used as the Config Key hash input."""
    d = {k: v for k, v in settings.items() if k != "originatorVersion"}
    return _obj(d)


def config_key(settings: dict) -> str:
    return hashlib.sha256(seb_json(settings).encode("utf-8")).hexdigest()


# --- Settings template + .seb file ------------------------------------------

# Lockdown template. NOTE (AD-56): for the Config Key to match SEB's own, this
# dict must equal the full settings set SEB serializes. This curated set is the
# starting point; the Windows acceptance step (docs/seb-acceptance.md) compares
# SEB's verbose "JSON for Config Key:" string with ``seb_json(seb_settings(url))``
# and any missing keys get added here until they match exactly. Keep keys
# readable for diffing (the serializer sorts anyway).
_LOCKDOWN: dict = {
    "allowAudioCapture": False,
    "allowBrowsingBackForward": False,
    "allowDownUploads": False,
    "allowPreferencesWindow": False,
    # Quitting is allowed ONLY via the Ctrl+Q shortcut (the taskbar quit button is
    # gone because showTaskBar=False). With hashedQuitPassword set, Ctrl+Q pops a
    # confirm dialog that requires the quit password — there is no other way out.
    "allowQuit": True,
    "allowReload": True,
    "allowSpellCheck": False,
    "allowUserSwitchKeyboardLayout": False,
    "allowVideoCapture": False,
    "allowWlan": False,
    # Fullscreen kiosk: no minimize/maximize/close buttons on the SEB window.
    "browserViewMode": 1,
    # Kiosk mode "Create new desktop": SEB runs on its own isolated Windows
    # desktop (only SEB visible). This is SEB 2.4.1's DEFAULT kiosk mode, so the
    # loaded exam settings match the local client config — otherwise SEB 2.4.1
    # errors "Loaded exam settings require the standard desktop, but currently SEB
    # is running on a new desktop" and quits. (AD-63: exam machines run SEB 2.4.1
    # on Win7.) killExplorerShell=false is its pair.
    "createNewDesktop": True,
    "killExplorerShell": False,
    "allowSwitchToApplications": False,
    "allowWindowCapture": False,
    "monitorProcesses": True,
    "browserWindowAllowReload": True,
    "enableF1": False,
    "enableF3": False,
    "enablePrintScreen": False,
    "enableRightMouse": False,
    "newBrowserWindowByLinkPolicy": 0,
    "newBrowserWindowByScriptPolicy": 0,
    "quitURL": "",
    "restartExamUseStartURL": True,
    "sendBrowserExamKey": True,
    "showMenuBar": False,
    "showTaskBar": False,
    "URLFilterEnable": True,
    "URLFilterEnableContentFilter": False,
    # --- Windows hotkeys: disable every OS shortcut that could break lockdown ---
    "enableEsc": False,
    "enableCtrlEsc": False,
    "enableAltEsc": False,
    "enableAltTab": False,
    "enableAltF4": False,
    "enableStartMenu": False,
    "enableAltMouseWheel": False,
    "enableF1": False, "enableF2": False, "enableF3": False, "enableF4": False,
    "enableF5": False, "enableF6": False, "enableF7": False, "enableF8": False,
    "enableF9": False, "enableF10": False, "enableF11": False, "enableF12": False,
    # Don't let the exam run inside a VM (anti-cheat).
    "allowVirtualMachine": False,
}


def _hash_password(pw: str) -> str:
    """SEB stores passwords as a Base16 (hex) SHA-256 of the plaintext."""
    return hashlib.sha256(pw.encode("utf-8")).hexdigest()


def seb_settings(start_url: str, quit_password: str = "", admin_password: str = "") -> dict:
    """Full settings dict that seeds the .seb file (and the computed Config Key).

    Passwords are optional and injected as SHA-256 hashes. NOTE: passing a
    password changes the Config Key, so when you protect a file you must verify
    with the key from the SEB Config Tool (SEB_CONFIG_KEY), not the computed
    fallback (which is password-free). See AD-57 / docs/seb-acceptance.md.
    """
    s = {**_LOCKDOWN, "startURL": start_url}
    if quit_password:
        s["hashedQuitPassword"] = _hash_password(quit_password)
    if admin_password:
        s["hashedAdminPassword"] = _hash_password(admin_password)
    return s


def build_seb(start_url: str, quit_password: str = "", admin_password: str = "") -> bytes:
    """Unencrypted .seb (plist XML) -- config + optional password hashes."""
    return plistlib.dumps(
        seb_settings(start_url, quit_password, admin_password), fmt=plistlib.FMT_XML
    )


# Fixed SEB passwords (AD-60). There is no quit button (taskbar hidden), so the
# only way out is Ctrl+Q -> type QUIT_PASSWORD. ADMIN_PASSWORD protects the SEB
# settings/admin functions. Both stable, so one .seb works forever. Change before
# production if you want different secrets.
QUIT_PASSWORD = "ump@2026"
ADMIN_PASSWORD = "ump@250626"


def build_exam_seb(start_url: str | None = None, admin_password: str | None = None) -> bytes:
    """The distributable exam .seb: universal start URL + fixed passwords.

    This is the official builder used to produce the file copied to exam PCs. The
    quit password is QUIT_PASSWORD; admin_password defaults to ADMIN_PASSWORD.
    """
    return build_seb(
        start_url or _app_settings.seb_start_url,
        quit_password=QUIT_PASSWORD,
        admin_password=ADMIN_PASSWORD if admin_password is None else admin_password,
    )


@lru_cache
def current_config_key() -> str:
    """Config Key used to STRICT-verify SEB requests, or "" for presence mode (AD-59).

    When the operator pastes the key from the SEB Config Tool (``SEB_CONFIG_KEY``)
    we bind each request cryptographically to that exact .seb. When it is empty
    (the default), enforcement falls back to presence mode — we only require that
    the request comes from SEB at all — so a single universal .seb works on any
    LAN/IP and never 403s on template drift (the user accepted this trade-off).
    """
    return (_app_settings.seb_config_key or "").strip().lower()


# --- Per-request verification -----------------------------------------------

def absolute_url(request) -> str:
    """Rebuild the URL as SEB saw it (behind Caddy), without the fragment.

    SEB hashes the absolute request URL. Caddy forwards the original scheme/host
    in X-Forwarded-Proto / X-Forwarded-Host; fall back to the request's own host.
    """
    proto = request.headers.get("x-forwarded-proto") or "http"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or ""
    path = request.url.path
    query = request.url.query
    url = f"{proto}://{host}{path}"
    if query:
        url += f"?{query}"
    return url


def request_hash(url: str, ck: str) -> str:
    return hashlib.sha256((url + ck).encode("utf-8")).hexdigest()


def is_seb_request(request) -> bool:
    """True if the request carries any SEB integrity header (i.e. comes from SEB).

    A normal browser sends neither header; SEB always sends them when a Browser
    Exam Key / Config Key is configured (our template sets ``sendBrowserExamKey``).
    """
    return bool(
        request.headers.get(CONFIG_KEY_HEADER)
        or request.headers.get(REQUEST_HASH_HEADER)
    )


def verify_seb_header(request, ck: str) -> bool:
    """Accept the request as coming from a locked-down SEB.

    Strict mode (``ck`` set, from SEB_CONFIG_KEY): bind the request to the exact
    .seb via SHA256(absoluteURL + ConfigKey). Presence mode (``ck`` empty): only
    require that the request is from SEB at all — universal, IP-independent (AD-59).
    """
    if not ck:
        return is_seb_request(request)
    sent = request.headers.get(CONFIG_KEY_HEADER)
    if not sent:
        return False
    expected = request_hash(absolute_url(request), ck)
    return hmac.compare_digest(sent.strip().lower(), expected.lower())
