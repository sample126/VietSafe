"""Explicit offline CLI: python -m vietsafe.data_pipeline --help."""

import argparse
import json

from .config import DataPaths
from .exceptions import DataValidationError, ReleaseExistsError
from .pipeline import run_pipeline


def main():
    parser = argparse.ArgumentParser(description="VietSafe Data-02 offline demo (no downloads)")
    for name in ("dataset-version", "timestamp", "as-of", "created-at", "code-commit"):
        parser.add_argument("--" + name, required=True)
    parser.add_argument("--data-root")
    parser.add_argument("--write", action="store_true", help="Publish immutable local release")
    args = parser.parse_args()
    try:
        result = run_pipeline(
            dataset_version=args.dataset_version,
            timestamp=args.timestamp,
            as_of=args.as_of,
            created_at=args.created_at,
            code_commit=args.code_commit,
            paths=DataPaths(args.data_root) if args.data_root else None,
            write=args.write,
        )
    except DataValidationError as error:
        print(json.dumps(error.to_dict(), ensure_ascii=False))
        return 2
    except (ReleaseExistsError, ValueError, OSError) as error:
        print(json.dumps({"error": str(error)}, ensure_ascii=False))
        return 2
    print(json.dumps(result.summary(), ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
