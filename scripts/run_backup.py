#!/usr/bin/env python3
"""
CLI de backup para CI / cron.

Uso:
  python scripts/run_backup.py
  python scripts/run_backup.py --tag nightly --outdir ./artifacts

Lee TURSO_URL / TURSO_TOKEN del entorno (o .env / Streamlit secrets).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))


def main() -> int:
    parser = argparse.ArgumentParser(description="Exporta backup JSON de Mission Dashboard")
    parser.add_argument("--tag", default="nightly", help="Sufijo del archivo")
    parser.add_argument(
        "--outdir",
        default="",
        help="Directorio de salida (default: data/backups)",
    )
    args = parser.parse_args()

    from app import backup as bak

    if args.outdir:
        bak.BACKUP_DIR = Path(args.outdir)
    path = bak.exportar_backup_json(tag=args.tag)
    if not path:
        print("ERROR: no se pudo crear el backup", file=sys.stderr)
        return 1
    print(f"OK {path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
