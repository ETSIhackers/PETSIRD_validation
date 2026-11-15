"""
Validation functions for model/DetectorInformation.yml:
ScannerGeometry, DetectorModule and SolidVolume.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Hong Phuc Vo

import numpy as np
import petsird

# Tolerance (mm) when checking that (0,0,0) lies inside a detecting element.
_INSIDE_TOL_MM = 1e-3


def validate_scanner_geometry(header: petsird.Header) -> None:
    """there is at least one module type

    DetectorInformation.yml: ScannerGeometry ("numberOfModuleTypes > 0")
    """
    if not header.scanner.scanner_geometry.replicated_modules:
        raise ValueError("scannerGeometry.replicatedModules is empty; "
                         "numberOfModuleTypes must be > 0")


def validate_detecting_element(box: petsird.BoxShape) -> None:
    """check constraints on a detecting element

    The box must be along the x-axis, with (0,0,0), the average detection
    position, inside it.
    DetectorInformation.yml: DetectorModule.detectingElements
    """
    corners = np.array([c.c for c in box.corners], dtype=np.float64)
    front, back = corners[:4], corners[4:]
    box_direction = back.mean(axis=0) - front.mean(axis=0)
    norm = np.linalg.norm(box_direction)
    if norm == 0:
        raise ValueError("front and back faces have the same centre")
    box_direction /= norm

    if np.dot(box_direction, (1.0, 0.0, 0.0)) < np.cos(np.pi / 5):
        raise ValueError(
            f"box axis {np.round(box_direction, 3).tolist()} is not along +x "
            "(the front face must be the one closest to the scanner centre)")

    if (np.dot(front.mean(axis=0), box_direction) >= 0
            or np.dot(back.mean(axis=0), box_direction) <= 0):
        raise ValueError("(0,0,0), the average detection position, is not "
                         "between the front and back faces")
    lo = corners.min(axis=0) - _INSIDE_TOL_MM
    hi = corners.max(axis=0) + _INSIDE_TOL_MM
    if np.any(lo > 0) or np.any(hi < 0):
        raise ValueError(
            "(0,0,0), the average detection position, is outside the box; "
            f"corners range from {corners.min(axis=0).tolist()} to "
            f"{corners.max(axis=0).tolist()}")


def validate_detecting_elements(header: petsird.Header) -> None:
    """detecting elements are along +x and contain (0,0,0)

    DetectorInformation.yml: DetectorModule.detectingElements
    """
    geometry = header.scanner.scanner_geometry
    for t, rep_module in enumerate(geometry.replicated_modules):
        try:
            validate_detecting_element(
                rep_module.object.detecting_elements.object.shape)
        except ValueError as e:
            raise ValueError(
                f"detecting element of module type {t}: {e}") from e


def validate_material_ids(header: petsird.Header) -> None:
    """every materialId refers to an entry in ScannerInformation.bulkMaterials

    DetectorInformation.yml: SolidVolume.materialId
    """
    known = {m.id for m in header.scanner.bulk_materials}
    geometry = header.scanner.scanner_geometry
    users = []
    for t, rep_module in enumerate(geometry.replicated_modules):
        where = f"scannerGeometry.replicatedModules[{t}].object"
        users.append((f"{where}.detectingElements.object.materialId",
                      rep_module.object.detecting_elements.object.material_id))
        for k, non_det in enumerate(rep_module.object.non_detecting_elements):
            users.append(
                (f"{where}.nonDetectingElements[{k}].object.materialId",
                 non_det.object.material_id))
    for k, volume in enumerate(geometry.non_detecting_volumes or []):
        users.append((f"scannerGeometry.nonDetectingVolumes[{k}].materialId",
                      volume.material_id))
    for where, material_id in users:
        if material_id not in known:
            raise ValueError(
                f"{where} is {material_id}, but bulkMaterials ids "
                f"are {sorted(known) if known else 'none'}")
