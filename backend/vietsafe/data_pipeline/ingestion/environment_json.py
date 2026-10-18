"""Offline normalized interchange input, NOT a NASA binary granule decoder."""

import argparse
import hashlib
import json
from pathlib import Path

from ..environment import EnvironmentalGrid, EnvironmentInputError, PROCESSING_VERSION, require

MAX_JSON_BYTES = 8 * 1024 * 1024


def _unique(pairs):
    result = {}
    for key, value in pairs:
        require(key not in result, "Duplicate JSON key")
        result[key] = value
    return result


def _constant(value):
    raise EnvironmentInputError("Non-finite JSON constant")


def read_grid(path, source_type):
    """Hash actual input bytes; input omits derived raw_checksum to avoid self-reference."""
    with Path(path).open("rb") as stream:
        raw = stream.read(MAX_JSON_BYTES + 1)
    require(len(raw) <= MAX_JSON_BYTES, "Interchange JSON exceeds size limit")
    try:
        payload = json.loads(raw.decode("utf-8"), object_pairs_hook=_unique, parse_constant=_constant)
    except (UnicodeError, json.JSONDecodeError, RecursionError) as error:
        raise EnvironmentInputError("Invalid UTF-8 JSON interchange") from error
    require(isinstance(payload, dict), "Expected interchange object")
    require("raw_checksum" not in payload, "Input must omit derived raw_checksum")
    require(payload.get("source_type") == source_type, "Unexpected source_type")
    require(isinstance(payload.get("metadata"), dict), "metadata must be an object")
    # The conversion boundary must explicitly describe the upstream values and units.
    require(payload["metadata"].get("original_units") == payload.get("units") and
            payload["metadata"].get("original_variable") == payload.get("variable"),
            "This loader performs no unit/variable conversion")
    require(payload["metadata"].get("processing_version") == PROCESSING_VERSION,
            "Unsupported processing version")
    payload["raw_checksum"] = hashlib.sha256(raw).hexdigest()
    return EnvironmentalGrid.from_dict(payload)


def emit(grid, output):
    if output:
        # Explicit output only; exclusive create protects existing releases/files.
        with Path(output).open("x", encoding="utf-8", newline="\n") as stream:
            stream.write(grid.to_json())
    print(json.dumps({"source_type": grid.source_type, "rows": grid.rows, "cols": grid.cols,
                      "variable": grid.variable, "units": grid.units, "checksum": grid.checksum()},
                     sort_keys=True))


def grid_cli(loader, description, argv=None):
    parser = argparse.ArgumentParser(description=description)
    parser.add_argument("--input", required=True, help="Offline normalized interchange JSON")
    parser.add_argument("--output", help="New JSON output file; never overwrite")
    args = parser.parse_args(argv)
    try:
        emit(loader(args.input), args.output)
    except (EnvironmentInputError, OSError) as error:
        parser.exit(2, f"{error}\n")
