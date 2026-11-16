"""
Helpers shared by the validation modules.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Hong Phuc Vo

import warnings

import petsird


class PETSIRDWarning(UserWarning):
    """Something unusual that the PETSIRD model does not forbid."""


def warn(message: str) -> None:
    warnings.warn(message, PETSIRDWarning, stacklevel=3)


def num_module_types(header: petsird.Header) -> int:
    return len(header.scanner.scanner_geometry.replicated_modules)


def num_modules(header: petsird.Header, type_of_module: int) -> int:
    return len(header.scanner.scanner_geometry.
               replicated_modules[type_of_module].transforms)


def num_bins_per_module(header: petsird.Header, type_of_module: int) -> int:
    """Number of detection bins in one module: elements x energy bins."""
    scanner = header.scanner
    rep_module = scanner.scanner_geometry.replicated_modules[type_of_module]
    num_elements = len(rep_module.object.detecting_elements.transforms)
    return num_elements * scanner.event_energy_bin_edges[
        type_of_module].number_of_bins()
