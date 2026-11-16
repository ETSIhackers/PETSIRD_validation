"""
Validation functions and helpers for model/GeometryInformation.yml:
RigidTransformation, ReplicatedObject and BoxShape.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Hong Phuc Vo

from collections.abc import Iterator, Sequence

import numpy as np
import numpy.typing as npt
import petsird


def is_clockwise_2D(
        points: Sequence[tuple[float, float] | npt.NDArray]) -> bool:
    """
    Determine if a polygon's vertices are ordered clockwise.

    Args:
        points: List of (x, y) tuples representing polygon vertices.
                Must contain at least 3 points.

    Returns:
        True if vertices are clockwise, False if counterclockwise.

    Raises:
        ValueError: If fewer than 3 points are provided.
    """
    if len(points) < 3:
        raise ValueError("A polygon must have at least 3 vertices.")

    # Calculate signed area using the shoelace formula
    # see e.g. https://mathworld.wolfram.com/PolygonArea.html
    signed_area = 0.0
    n = len(points)
    for i in range(n):
        x1, y1 = points[i]
        x2, y2 = points[(i + 1) % n]  # wrap around to first point
        signed_area += (x2 - x1) * (y2 + y1)

    # Clockwise if signed_area > 0 (based on this variant of shoelace method)
    return signed_area > 0


def is_clockwise_3D(points: Sequence[npt.NDArray], direction1: npt.NDArray,
                    direction2: npt.NDArray) -> bool:
    """check if projections of points on plane are in clockwise order

    The plane is specified by 2 direction vectors.
    """
    return is_clockwise_2D([(np.dot(p, direction1), np.dot(p, direction2))
                            for p in points])


def check_rigid(transforms: Sequence[petsird.RigidTransformation],
                name: str,
                tol: float = 1e-4) -> None:
    """The 3x3 rotation part of every transform is orthonormal with det +1.

    GeometryInformation.yml: RigidTransformation
    """
    if not transforms:
        return
    matrices = np.stack(
        [np.asarray(t.matrix, dtype=np.float64) for t in transforms])
    rotations = matrices[:, :, :3]
    gram = np.einsum("nji,njk->nik", rotations, rotations)
    off = np.abs(gram - np.eye(3)).max(axis=(1, 2))
    finite = np.all(np.isfinite(matrices.reshape(len(matrices), -1)), axis=1)
    bad = np.nonzero((off > tol) | (np.linalg.det(rotations) <= 0)
                     | ~finite)[0]
    if bad.size:
        first = int(bad[0])
        raise ValueError(
            f"{name}[{first}] is not a rigid transformation (rotation part "
            f"must be orthonormal with det +1): {matrices[first].tolist()}; "
            f"{bad.size} of {len(transforms)} transforms are affected")


def is_lex_less(a: npt.NDArray, b: npt.NDArray) -> bool:
    """check if a < b in lexicographic order (last dimension first, i.e. z, y, x)"""
    return tuple(a[::-1]) < tuple(b[::-1])


def validate_box_shape(box: petsird.BoxShape) -> None:
    """check the corner order of a BoxShape

    GeometryInformation.yml: BoxShape
    """
    corners = np.array([c.c for c in box.corners], dtype=np.float64)
    for name, face in (("front", corners[:4]), ("back", corners[4:])):
        if not is_clockwise_2D(face[:, 1:3]):
            raise ValueError(f"{name} face corners are not clockwise")
        if not all(is_lex_less(face[0], c) for c in face[1:]):
            raise ValueError(
                f"first corner of the {name} face is not the smallest "
                "(lexicographic order z, y, x)")


def _box_shapes(
        header: petsird.Header) -> Iterator[tuple[str, petsird.BoxShape]]:
    geometry = header.scanner.scanner_geometry
    for t, rep_module in enumerate(geometry.replicated_modules):
        where = f"scannerGeometry.replicatedModules[{t}].object"
        yield (f"{where}.detectingElements.object.shape",
               rep_module.object.detecting_elements.object.shape)
        for k, non_det in enumerate(rep_module.object.non_detecting_elements):
            shape = non_det.object.shape
            if isinstance(shape, petsird.GeometricShape.BoxShape):
                yield (f"{where}.nonDetectingElements[{k}].object.shape",
                       shape.value)


def validate_box_shapes(header: petsird.Header) -> None:
    """every BoxShape has clockwise faces whose first corner is the smallest

    GeometryInformation.yml: BoxShape
    """
    for where, box in _box_shapes(header):
        try:
            validate_box_shape(box)
        except ValueError as e:
            raise ValueError(f"{where}: {e}") from e


def validate_replicated_objects(header: petsird.Header) -> None:
    """every replicated object has at least one transform

    GeometryInformation.yml: ReplicatedObject.transforms ("length >= 1")
    """
    geometry = header.scanner.scanner_geometry
    for t, rep_module in enumerate(geometry.replicated_modules):
        where = f"scannerGeometry.replicatedModules[{t}]"
        if not rep_module.transforms:
            raise ValueError(f"{where}.transforms is empty (no modules)")
        if not rep_module.object.detecting_elements.transforms:
            raise ValueError(f"{where}.object.detectingElements.transforms is "
                             "empty (no detecting elements)")
        for k, non_det in enumerate(rep_module.object.non_detecting_elements):
            if not non_det.transforms:
                raise ValueError(f"{where}.object.nonDetectingElements[{k}]."
                                 "transforms is empty")


def validate_transforms(header: petsird.Header) -> None:
    """every RigidTransformation in the geometry is rigid

    GeometryInformation.yml: RigidTransformation
    """
    geometry = header.scanner.scanner_geometry
    for t, rep_module in enumerate(geometry.replicated_modules):
        where = f"scannerGeometry.replicatedModules[{t}]"
        check_rigid(rep_module.transforms, f"{where}.transforms")
        check_rigid(rep_module.object.detecting_elements.transforms,
                    f"{where}.object.detectingElements.transforms")
        for k, non_det in enumerate(rep_module.object.non_detecting_elements):
            check_rigid(
                non_det.transforms,
                f"{where}.object.nonDetectingElements[{k}].transforms")
    if header.scanner.gantry_alignment is not None:
        check_rigid([header.scanner.gantry_alignment], "gantryAlignment")


geometry_information_tests_suite = {
    "box shapes": {
        "func": validate_box_shapes,
        "level": "header",
    },
    "replicated objects": {
        "func": validate_replicated_objects,
        "level": "header",
    },
    "rigid transformations": {
        "func": validate_transforms,
        "level": "header",
    },
}
