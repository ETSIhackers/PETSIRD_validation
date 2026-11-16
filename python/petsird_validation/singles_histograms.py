"""
Validation functions for model/SinglesHistograms.yml: ModuleSinglesUnitIdxLUT.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Hong Phuc Vo

import petsird

from ._common import num_module_types, num_modules, warn


def validate_singles_unit_luts(header: petsird.Header) -> None:
    """each singles-unit LUT has one entry per module, with values >= -1

    SinglesHistograms.yml: ModuleSinglesUnitIdxLUT, SinglesUnitIdx
    """
    s = header.scanner
    if s.singles_histogram_level != petsird.SinglesHistogramLevelType.MODULE:
        return
    luts = s.module_singles_unit_idx_lu_ts[:num_module_types(header)]
    for t, lut in enumerate(luts):
        if len(lut) != num_modules(header, t):
            raise ValueError(
                f"moduleSinglesUnitIdxLUTs[{t}] has {len(lut)} entries, "
                f"expected {num_modules(header, t)} (one per module)")
        for m, unit in enumerate(lut):
            if unit < -1:
                raise ValueError(
                    f"moduleSinglesUnitIdxLUTs[{t}][{m}] is {unit}; "
                    "values must be >= -1")
    if luts and all(unit < 0 for lut in luts for unit in lut):
        warn(
            "moduleSinglesUnitIdxLUTs: no module is assigned to a singles unit"
        )


singles_histograms_tests_suite = {
    "singles unit LUTs": {
        "func": validate_singles_unit_luts,
        "level": "header",
    },
}
