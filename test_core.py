#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Kiểm tra nhanh lõi check trên máy bạn (trước khi bật bot).

    python test_core.py user:pass
    python test_core.py acc1:pass1 acc2:pass2

In ra status + toàn bộ field lấy được, để biết lõi chạy được trên máy/mạng của bạn.
"""
import sys
import time

try:
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
except Exception:
    pass

import lqcore  # file lõi của tool


def main() -> None:
    items = [a for a in sys.argv[1:] if ":" in a]
    if not items:
        print("Dùng:")
        print("   python test_core.py user:pass")
        print("   python test_core.py acc1:pass1 acc2:pass2")
        return
    for item in items:
        acc, pw = item.split(":", 1)
        t0 = time.time()
        try:
            r = lqcore.check_login(acc, pw, timeout=7, fetch_info=True)
        except Exception as exc:
            print(f"\n[{acc}] LỖI: {type(exc).__name__}: {exc}")
            continue
        print("=" * 64)
        print(f"ACC: {acc}   status={r.get('status')}   {round(time.time() - t0, 1)}s")
        if r.get("detail"):
            print(f"  detail: {r['detail']}")
        for k, v in r.items():
            if isinstance(v, (dict, list, tuple)):
                continue
            if str(v).strip() in ("", "0", "None", "False", "[]", "{}"):
                continue
            print(f"  {k}: {v}")
        for k, v in r.items():
            if isinstance(v, (dict, list, tuple)) and v:
                print(f"  {k}: <{type(v).__name__} {len(v)} mục> -> xem trong bot bằng nút JSON")
    print("=" * 64)


if __name__ == "__main__":
    main()
