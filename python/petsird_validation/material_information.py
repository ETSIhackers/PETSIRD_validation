"""
Validation functions for model/MaterialInformation.yml:
Atom and BulkMaterial.
"""
# Copyright (C) 2026 ETSI hackathon contributors
#  Author: Kathiresan Chandrasekaran

import math

import petsird

# Absolute tolerance for floating-point mass fractions.
_MASS_FRACTION_TOL = 1e-6


def validate_material_ids_unique(header: petsird.Header) -> None:
    """Check that every BulkMaterial has a unique ID.

    MaterialInformation.yml: BulkMaterial.id
    """
    seen = set()

    for k, material in enumerate(header.scanner.bulk_materials):
        if material.id in seen:
            raise ValueError(f"bulkMaterials[{k}].id is {material.id}, "
                             "which is a duplicate material ID")
        seen.add(material.id)


def validate_material_fraction_count(header: petsird.Header) -> None:
    """Check that the number of atoms equals the number of mass fractions.

    MaterialInformation.yml: BulkMaterial
    Constraint: size(atoms) == size(massFractions)
    """
    for k, material in enumerate(header.scanner.bulk_materials):
        n_atoms = len(material.atoms)
        n_fractions = len(material.mass_fractions)

        if n_atoms != n_fractions:
            raise ValueError(
                f"bulkMaterials[{k}] ({material.name}): "
                f"{n_atoms} atoms but {n_fractions} mass fractions")


def validate_material_fraction_sum(header: petsird.Header) -> None:
    """Check that mass fractions sum to 1.

    MaterialInformation.yml: BulkMaterial
    Constraint: sum(massFractions) == 1
    """
    for k, material in enumerate(header.scanner.bulk_materials):
        fractions = material.mass_fractions

        if not all(math.isfinite(float(f)) for f in fractions):
            raise ValueError(f"bulkMaterials[{k}] ({material.name}): "
                             "mass fractions contain non-finite values")

        total = sum(float(f) for f in fractions)

        if not math.isclose(
                total, 1.0, rel_tol=0.0, abs_tol=_MASS_FRACTION_TOL):
            raise ValueError(
                f"bulkMaterials[{k}] ({material.name}): "
                f"mass fractions sum to {total:.8f}, expected 1.0")
