#!/usr/bin/env python3
"""Verifica que un deploy FastAPI responde /health correctamente.

Uso:
  python scripts/verify_deploy.py https://tu-app.up.railway.app
  python scripts/verify_deploy.py http://127.0.0.1:8000
"""
from __future__ import annotations

import json
import sys
import urllib.error
import urllib.request


def main() -> int:
    base = (sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000").rstrip("/")
    url = f"{base}/health"
    try:
        with urllib.request.urlopen(url, timeout=15) as resp:
            body = resp.read().decode("utf-8", errors="replace")
            data = json.loads(body)
    except urllib.error.HTTPError as e:
        print(f"FAIL HTTP {e.code} {url}", file=sys.stderr)
        return 1
    except Exception as e:
        print(f"FAIL {url}: {e}", file=sys.stderr)
        return 1

    ok = bool(data.get("ok"))
    fw = data.get("framework")
    print(json.dumps(data, ensure_ascii=False, indent=2))
    if not ok:
        print("FAIL: ok != true", file=sys.stderr)
        return 1
    if fw and fw != "fastapi+htmx":
        print(f"WARN: framework inesperado: {fw}", file=sys.stderr)
    print(f"OK {url}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
