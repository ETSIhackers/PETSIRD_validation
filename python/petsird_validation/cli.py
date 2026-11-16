"""
Command-line interface: ``petsird-validator FILE``.

Reads the header of a PETSIRD file and runs every validate function on it.
Exit code: 0 = all checks pass, 1 = a check failed, 2 = the file can't be read.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Hong Phuc Vo

import argparse
import sys

import petsird

from .detector_information import (validate_detecting_elements,
                                   validate_material_ids,
                                   validate_scanner_geometry)
from .geometry_information import (validate_box_shapes,
                                   validate_replicated_objects,
                                   validate_transforms)

HEADER_CHECKS = (
    validate_scanner_geometry,
    validate_detecting_elements,
    validate_material_ids,
    validate_box_shapes,
    validate_replicated_objects,
    validate_transforms,
)


def read_header(path: str) -> petsird.Header:
    """Read the header of a binary or NDJSON PETSIRD file."""
    with open(path, "rb") as f:
        magic = f.read(8)
    if magic.startswith(b"yardl"):
        reader = petsird.BinaryPETSIRDReader(path, skip_completed_check=True)
    elif magic.lstrip().startswith(b"{"):
        reader = petsird.NDJsonPETSIRDReader(path, skip_completed_check=True)
    else:
        raise ValueError("not a PETSIRD binary or NDJSON file")
    with reader:
        return reader.read_header()


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="petsird-validator",
        description="Check a PETSIRD file against the constraints in the "
        "PETSIRD model.")
    parser.add_argument("file", help="PETSIRD binary or NDJSON file")
    args = parser.parse_args(argv)

    try:
        header = read_header(args.file)
    except Exception as e:  # noqa: BLE001 - any read error means exit code 2
        print(f"petsird-validator: error: could not read {args.file}: {e}",
              file=sys.stderr)
        return 2

    failed = 0
    for check in HEADER_CHECKS:
        try:
            check(header)
            print(f"PASS {check.__name__}")
        except ValueError as e:
            print(f"FAIL {check.__name__}: {e}")
            failed += 1
    print(f"{failed} of {len(HEADER_CHECKS)} checks failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
