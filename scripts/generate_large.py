#!/usr/bin/env python
"""Create a 100,000-row database for the A6 export scenario.

The default quick-start dataset is never touched: this writes a separate file
(``data/large.db`` by default) and the app is pointed at it with DB_PATH.

    .venv/bin/python scripts/generate_large.py --tenant east --count 100000
    DB_PATH=data/large.db ./start.sh
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from app.bulkdata import insert_bulk_certificates  # noqa: E402
from app.config import BASE_DIR  # noqa: E402
from app.db import Database  # noqa: E402
from app.seed import seed_demo  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate a large certificate dataset (A6)")
    parser.add_argument(
        "--db",
        default=str(BASE_DIR / "data" / "large.db"),
        help="target database file (default: data/large.db)",
    )
    parser.add_argument("--tenant", default="east", help="tenant slug: east or west")
    parser.add_argument("--count", type=int, default=100_000, help="certificates to add")
    parser.add_argument("--force", action="store_true", help="overwrite the target database")
    args = parser.parse_args()

    path = Path(args.db).expanduser().resolve()
    if path.exists() and not args.force:
        raise SystemExit(
            f"{path} already exists; pass --force to rebuild it (the demo database is untouched)"
        )
    if args.force:
        for suffix in ("", "-wal", "-shm"):
            Path(str(path) + suffix).unlink(missing_ok=True)

    tenant_id = f"tenant_{args.tenant}"
    database = Database(path)
    database.init_schema()
    seed_demo(database)
    with database.write() as conn:
        summary = insert_bulk_certificates(conn, tenant_id=tenant_id, count=args.count)

    print(
        f"Seeded {summary['certificates']:,} certificates for {args.tenant} into {path}\n"
        f"Run the app against it:\n"
        f"  DB_PATH={path} ./start.sh\n"
        f"Then export from the UI or:\n"
        f"  curl -H 'X-Actor-Email: alice@east.test' \\\n"
        f"       -o /tmp/certificates.csv \\\n"
        f"       'http://127.0.0.1:8000/api/certificates/export.csv?sort=learner_name&dir=asc'"
    )


if __name__ == "__main__":
    main()
