"""Create the SQLite database and seed the sample evaluation criteria.

    python scripts/seed_db.py            # create tables, seed criteria only if the table is empty
    python scripts/seed_db.py --reset    # delete the database file first (starts from scratch)
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from rfp_eval import config, db  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--reset", action="store_true", help="delete the existing database first")
    args = parser.parse_args()
    if args.reset and config.DB_PATH.exists():
        config.DB_PATH.unlink()
        print(f"Deleted {config.DB_PATH}")
    db.init_db(seed=True)
    print(f"Database ready at {config.DB_PATH}")
    for c in db.get_active_criteria():
        print(f"  [{c['criterion_id']}] {c['name']:<24} weight={c['weight']:g}%  max={c['max_score']:g}")


if __name__ == "__main__":
    main()
