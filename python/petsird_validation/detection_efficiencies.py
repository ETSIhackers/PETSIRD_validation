"""
Validation functions for model/DetectionEfficiencies.yml:
DetectionBinEfficiencies, ModulePairEfficiencies, and DetectionEfficiencies.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Authors: MAX TOUSS, Kathiresan Chandrasekaran

import math

import petsird


def _lower_entries(matrix):
    """Iterate over meaningful lower-triangular entries."""
    for i, row in enumerate(matrix):
        if len(row) < i + 1:
            raise ValueError(
                f"Matrix row {i}: expected at least {i + 1} entries")
        for j in range(i + 1):
            yield i, j, row[j]


def _matrix_values(matrix):
    """Support Yardl matrix objects and nested arrays."""
    return matrix.values if hasattr(matrix, "values") else matrix


def _matrix_rows(matrix):
    values = _matrix_values(matrix)
    if hasattr(values, "tolist"):
        values = values.tolist()
    return values


def validate_detection_bin_efficiency_dimensions(header: petsird.Header):
    """Validate detectionBinEfficiencies dimensions."""
    scanner = header.scanner
    efficiencies = scanner.detection_efficiencies
    n = len(scanner.scanner_geometry.replicated_modules)

    if len(efficiencies.detection_bin_efficiencies) != n:
        raise ValueError(
            "detectionBinEfficiencies: number of module types does not match "
            f"scanner geometry ({n})")


def validate_module_pair_sgid_dimensions(header: petsird.Header):
    """Validate the outer dimensions of SGID LUTs and efficiency vectors."""
    scanner = header.scanner
    efficiencies = scanner.detection_efficiencies
    n = len(scanner.scanner_geometry.replicated_modules)

    for name, matrix in (
        ("modulePairSGIDLUT", efficiencies.module_pair_sgidlut),
        ("modulePairEfficienciesVectors",
         efficiencies.module_pair_efficiencies_vectors),
    ):
        # To check: need to understand, validate that when n != 1
        if n != 1 and len(matrix) != n:
            raise ValueError(
                f"{name}: expected {n} module-type rows, got {len(matrix)}")

        for i, row in enumerate(matrix):
            if len(row) != i + 1:
                raise ValueError(f"{name}[{i}]: expected {i + 1} entries, "
                                 f"got {len(row)}")


def validate_sgid_ranges(header: petsird.Header):
    """Check SGID ranges and their corresponding efficiency vectors."""
    efficiencies = header.scanner.detection_efficiencies

    for i, j, lut in _lower_entries(efficiencies.module_pair_sgidlut):
        vectors = efficiencies.module_pair_efficiencies_vectors[i][j]
        values = _matrix_rows(lut)

        sgids = [int(v) for row in values for v in row]

        if not sgids:
            expected = 0
        else:
            if min(sgids) < -1:
                raise ValueError(f"modulePairSGIDLUT[{i}][{j}]: SGID below -1")
            expected = max(sgids) + 1

        if len(vectors) != expected:
            raise ValueError(
                f"modulePairEfficienciesVectors[{i}][{j}]: "
                f"expected {expected} entries, got {len(vectors)}")

        for k, vector in enumerate(vectors):
            if vector.sgid != k:
                raise ValueError(
                    f"modulePairEfficienciesVectors[{i}][{j}][{k}]: "
                    f"SGID is {vector.sgid}, expected {k}")


def validate_efficiency_values(header: petsird.Header):
    """Check explicitly supplied efficiency values are finite."""
    efficiencies = header.scanner.detection_efficiencies

    if not math.isfinite(float(efficiencies.calibration_factor)):
        raise ValueError("calibrationFactor must be finite")

    for i, values in enumerate(efficiencies.detection_bin_efficiencies):
        for j, value in enumerate(values):
            if not math.isfinite(float(value)):
                raise ValueError(
                    f"detectionBinEfficiencies[{i}][{j}] is non-finite")

    for i, j, vectors in _lower_entries(
            efficiencies.module_pair_efficiencies_vectors):
        for k, vector in enumerate(vectors):
            for r, row in enumerate(_matrix_rows(vector.values)):
                for c, value in enumerate(row):
                    if not math.isfinite(float(value)):
                        raise ValueError(f"modulePairEfficienciesVectors"
                                         f"[{i}][{j}][{k}].values[{r}][{c}] "
                                         "is non-finite")


def validate_number_module_types_consistency(header: petsird.Header) -> None:
    """DetectionBinEfficiencies length should fit with the number of module types

    """

    num_module_type = len(header.scanner.scanner_geometry.replicated_modules)

    detection_bin_eff_size = len(
        header.scanner.detection_efficiencies.detection_bin_efficiencies)
    if num_module_type != detection_bin_eff_size:
        raise ValueError(
            f"The number of detection bin efficiencies ({detection_bin_eff_size}) "
            f"does not correspond to the number of module types ({num_module_type})."
        )


detection_efficiencies_tests_suite = {
    "Detection bin efficiency dimensions": {
        "func": validate_detection_bin_efficiency_dimensions,
        "level": "header"
    },
    "Efficiency values": {
        "func": validate_efficiency_values,
        "level": "header"
    },
    "Module pair sgid dimensions": {
        "func": validate_module_pair_sgid_dimensions,
        "level": "header"
    },
    "Number module types consistency": {
        "func": validate_number_module_types_consistency,
        "level": "header"
    },
    "Sgid ranges": {
        "func": validate_sgid_ranges,
        "level": "header"
    },
}
