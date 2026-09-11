"""Move junk staging formulas into _quarantine (dry-run by default).

Usage:
    uv run python scripts/prune_staging.py            # dry-run report
    uv run python scripts/prune_staging.py --apply    # actually move files
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

from symkit.domain.paths import user_derived_dir  # noqa: E402
from symkit.infrastructure.staging_prune import execute_prune, plan_prune  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply", action="store_true", help="actually move files")
    parser.add_argument("--derived-dir", type=Path, default=None,
                        help="staging directory (default: per-user derived dir)")
    args = parser.parse_args()

    staging = args.derived_dir or user_derived_dir()
    plan = plan_prune(staging)
    for src, dst in plan.moves:
        verb = "MOVE" if args.apply else "WOULD MOVE"
        print(f"{verb} {src} -> {dst}")
    print(f"{len(plan.moves)} junk, {len(plan.kept)} kept under {staging}")
    if args.apply:
        print(f"applied: moved {execute_prune(plan)} files")
    else:
        print("dry-run; pass --apply to move files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
