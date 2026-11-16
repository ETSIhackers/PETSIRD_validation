"""
Validation functions for model/ScannerInformation.yml.
"""
# Copyright (C) 2026 ETSI hackathon contributors
# Author: Kathiresan Chandrasekaran

import math

import numpy as np
import petsird


def validate_bin_edges(header: petsird.Header) -> None:
    """Check that TOF and energy bin edges are finite and increasing."""
    scanner = header.scanner

    def check(edges, where):
        values = np.asarray(edges.edges, dtype=float)
        if values.size < 2:
            raise ValueError(f"{where}: at least two edges required")
        if not np.all(np.isfinite(values)):
            raise ValueError(f"{where}: non-finite edges")
        if not np.all(np.diff(values) > 0):
            raise ValueError(f"{where}: edges must be strictly increasing")

    for i, row in enumerate(scanner.tof_bin_edges):
        for j, edges in enumerate(row[:i + 1]):
            check(edges, f"tofBinEdges[{i}][{j}]")

    for i, edges in enumerate(scanner.event_energy_bin_edges):
        check(edges, f"eventEnergyBinEdges[{i}]")

    for i, edges in enumerate(scanner.singles_histogram_energy_bin_edges):
        check(edges, f"singlesHistogramEnergyBinEdges[{i}]")


def validate_scanner_array_dimensions(header: petsird.Header) -> None:
    """Check array dimensions against the number of module types."""
    scanner = header.scanner
    n = len(scanner.scanner_geometry.replicated_modules)

    def check_vector(values, name):
        if len(values) != n:
            raise ValueError(
                f"{name}: expected {n} entries, got {len(values)}")

    def check_triangular(values, name):
        check_vector(values, name)
        for i, row in enumerate(values):
            if len(row) not in (i + 1, n):
                raise ValueError(
                    f"{name}[{i}]: expected {i + 1} or {n} entries, got {len(row)}"
                )

    check_triangular(scanner.tof_bin_edges, "tofBinEdges")
    check_triangular(scanner.tof_resolution, "tofResolution")
    check_vector(scanner.event_energy_bin_edges, "eventEnergyBinEdges")
    check_vector(scanner.energy_resolution_at_511, "energyResolutionAt511")


def validate_scanner_resolutions(header: petsird.Header) -> None:
    """Check that timing and energy resolutions are finite and positive."""
    scanner = header.scanner

    for i, row in enumerate(scanner.tof_resolution):
        for j, value in enumerate(row[:i + 1]):
            if not math.isfinite(float(value)) or value <= 0:
                raise ValueError(f"tofResolution[{i}][{j}] must be positive")

    for i, value in enumerate(scanner.energy_resolution_at_511):
        if not math.isfinite(float(value)) or value <= 0:
            raise ValueError(f"energyResolutionAt511[{i}] must be positive")


def validate_singles_histogram_dimensions(header: petsird.Header) -> None:
    """Check singles histogram constraints."""
    scanner = header.scanner
    n = len(scanner.scanner_geometry.replicated_modules)
    level = scanner.singles_histogram_level
    lut_count = len(scanner.module_singles_unit_idx_lu_ts)
    edge_count = len(scanner.singles_histogram_energy_bin_edges)

    if level == petsird.SinglesHistogramLevelType.NONE:
        if lut_count != 0 or edge_count != 0:
            raise ValueError(
                "Singles histogram level NONE requires empty LUTs and edges")
    elif level == petsird.SinglesHistogramLevelType.ALL:
        if lut_count != 0:
            raise ValueError("Singles histogram level ALL requires empty LUTs")
        if edge_count < n:
            raise ValueError(
                f"Expected at least {n} singles energy-bin entries")
    elif level == petsird.SinglesHistogramLevelType.MODULE:
        if lut_count != n:
            raise ValueError(
                f"Expected {n} module singles LUTs, got {lut_count}")
        if edge_count < n:
            raise ValueError(
                f"Expected at least {n} singles energy-bin entries")
    else:
        if edge_count < n:
            raise ValueError(
                f"Expected at least {n} singles energy-bin entries")


def validate_collimator_type(header: petsird.Header) -> None:
    """Check the allowed 2026 collimator types."""
    value = header.scanner.collimator_type

    if value not in ("NONE", "RING"):
        raise ValueError(
            f"collimatorType is {value!r}; expected 'NONE' or 'RING'")
