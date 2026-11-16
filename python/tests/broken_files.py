"""
Build a small valid PETSIRD header, and broken copies of it that each break
one constraint checked by petsird_validation.

BROKEN maps a name to a BrokenCase: the function that breaks a header, the
checks that must fail, and a piece of text the failure message must contain.

Run this file as a script to write the valid file and every broken file to a
folder, for example to try `petsird-validator` on them by hand:

    python tests/broken_files.py OUTDIR
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Claude (Anthropic AI assistant), not yet reviewed by a person

import argparse
import math
import pathlib
from collections.abc import Callable
from dataclasses import dataclass

import numpy as np
import petsird

# A crystal is a 20 x 4 x 4 mm box. Its average detection position (ADP),
# which must be at (0,0,0), is 9 mm behind the front face.
CRYSTAL_SIZE = (20.0, 4.0, 4.0)
AVERAGE_DOI = 9.0
# Each module has 2 crystals along z and a 2 mm tungsten plate behind them.
NUM_CRYSTALS_ALONG_Z = 2
# Two module types: (radius in mm, number of modules)
MODULE_TYPES = ((100.0, 4), (150.0, 3))
LYSO_ID = 1
TUNGSTEN_ID = 2
# (mass number, atomic number, mass fraction) per atom
LYSO = ((175, 71, 0.714), (89, 39, 0.040), (28, 14, 0.064), (16, 8, 0.182))
TUNGSTEN = ((184, 74, 1.0), )


def box_shape(lo: tuple[float, float, float],
              hi: tuple[float, float, float]) -> petsird.BoxShape:
    """axis-aligned box from lo to hi, with the front face at x = lo[0]

    The corners of each face are clockwise, starting at the smallest one.
    """
    (x0, y0, z0), (x1, y1, z1) = lo, hi
    corners = [(x, y, z) for x in (x0, x1)
               for (y, z) in ((y0, z0), (y0, z1), (y1, z1), (y1, z0))]
    return petsird.BoxShape(corners=[
        petsird.Coordinate(c=np.array(c, dtype=np.float32)) for c in corners
    ])


def transform(translation: tuple[float, float, float] = (0.0, 0.0, 0.0),
              angle: float = 0.0) -> petsird.RigidTransformation:
    """rotation by angle around z, then translation"""
    matrix = np.zeros((3, 4), dtype=np.float32)
    matrix[:, :3] = ((math.cos(angle), -math.sin(angle), 0.0),
                     (math.sin(angle), math.cos(angle), 0.0), (0.0, 0.0, 1.0))
    matrix[:, 3] = translation
    return petsird.RigidTransformation(matrix=matrix)


def make_module_type(radius: float,
                     num_modules: int) -> petsird.ReplicatedDetectorModule:
    """modules at the given radius, equally spaced around the z-axis"""
    length, width, height = CRYSTAL_SIZE
    crystal = petsird.SolidVolume(shape=box_shape(
        (-AVERAGE_DOI, -width / 2, -height / 2),
        (length - AVERAGE_DOI, width / 2, height / 2)),
                                  material_id=LYSO_ID)
    crystal_transforms = [
        transform((0.0, 0.0, (k - (NUM_CRYSTALS_ALONG_Z - 1) / 2) * height))
        for k in range(NUM_CRYSTALS_ALONG_Z)
    ]
    back = length - AVERAGE_DOI
    half_z = NUM_CRYSTALS_ALONG_Z * height / 2
    plate = petsird.SolidVolume(shape=petsird.GeometricShape.BoxShape(
        box_shape((back, -width / 2, -half_z),
                  (back + 2.0, width / 2, half_z))),
                                material_id=TUNGSTEN_ID)
    module = petsird.DetectorModule(
        detecting_elements=petsird.ReplicatedBoxSolidVolume(
            object=crystal, transforms=crystal_transforms),
        non_detecting_elements=[
            petsird.ReplicatedGenericSolidVolume(object=plate,
                                                 transforms=[transform()])
        ])
    module_transforms = []
    for m in range(num_modules):
        angle = 2 * math.pi * m / num_modules
        centre = (radius + AVERAGE_DOI) * np.array(
            (math.cos(angle), math.sin(angle), 0.0))
        module_transforms.append(transform(tuple(centre), angle))
    return petsird.ReplicatedDetectorModule(object=module,
                                            transforms=module_transforms)


def bulk_material(material_id: int, name: str, density: float,
                  composition) -> petsird.BulkMaterial:
    """composition: (mass number, atomic number, mass fraction) per atom"""
    return petsird.BulkMaterial(
        id=material_id,
        name=name,
        density=density,
        atoms=[
            petsird.Atom(mass_number=a, atomic_number=z)
            for a, z, _ in composition
        ],
        mass_fractions=[fraction for _, _, fraction in composition])


def make_header() -> petsird.Header:
    """a small scanner that passes every check"""
    num_types = len(MODULE_TYPES)
    scanner = petsird.ScannerInformation(
        model_name="PETSIRD_VALIDATION_TEST",
        scanner_geometry=petsird.ScannerGeometry(replicated_modules=[
            make_module_type(radius, num_modules)
            for radius, num_modules in MODULE_TYPES
        ]),
        bulk_materials=[
            bulk_material(LYSO_ID, "LYSO", 7.1, LYSO),
            bulk_material(TUNGSTEN_ID, "tungsten", 19.3, TUNGSTEN),
        ],
        collimator_type="NONE",
        tof_bin_edges=[[
            petsird.BinEdges(edges=np.linspace(-300, 300, 6, dtype=np.float32))
            for _ in range(i + 1)
        ] for i in range(num_types)],
        tof_resolution=[[60.0] * (i + 1) for i in range(num_types)],
        event_energy_bin_edges=[
            petsird.BinEdges(edges=np.array((450, 650), dtype=np.float32))
            for _ in range(num_types)
        ],
        energy_resolution_at_511=[0.1] * num_types,
    )
    return petsird.Header(exam=petsird.ExamInformation(),
                          scanner=scanner,
                          contains_weighted_event_time_blocks=False)


def write(header: petsird.Header,
          path: pathlib.Path,
          ndjson: bool = False) -> pathlib.Path:
    """write a PETSIRD file with this header and no time blocks"""
    writer_class = (petsird.NDJsonPETSIRDWriter
                    if ndjson else petsird.BinaryPETSIRDWriter)
    with writer_class(str(path)) as writer:
        writer.write_header(header)
        writer.write_time_blocks([])
    return path


# ---------------------------------------------------------------------------
# Broken headers


@dataclass(frozen=True)
class BrokenCase:
    breaks: Callable[[petsird.Header], None]
    fails: tuple[str, ...]  # names of the checks that must fail
    match: str  # text the failure message must contain

    def header(self) -> petsird.Header:
        header = make_header()
        self.breaks(header)
        return header


BROKEN: dict[str, BrokenCase] = {}


def broken(*fails: str, match: str = ""):
    """register a function that breaks a valid header"""

    def register(breaks):
        BROKEN[breaks.__name__] = BrokenCase(breaks, fails, match)
        return breaks

    return register


def _module_type(header, t=0):
    return header.scanner.scanner_geometry.replicated_modules[t]


def _crystals(header, t=0):
    return _module_type(header, t).object.detecting_elements


def _plates(header, t=0):
    return _module_type(header, t).object.non_detecting_elements[0]


def _move_corners(box: petsird.BoxShape, shift) -> None:
    for corner in box.corners:
        corner.c = corner.c + np.asarray(shift, dtype=np.float32)


# --- DetectorInformation.yml


@broken("validate_scanner_geometry", match="replicatedModules is empty")
def no_module_types(header):
    scanner = header.scanner
    scanner.scanner_geometry.replicated_modules = []
    scanner.tof_bin_edges = []
    scanner.tof_resolution = []
    scanner.event_energy_bin_edges = []
    scanner.energy_resolution_at_511 = []


@broken("validate_detecting_elements", match="is not along +x")
def crystal_facing_backwards(header):
    box = _crystals(header).object.shape
    box.corners = box.corners[4:] + box.corners[:4]


@broken("validate_detecting_elements", match="outside the box")
def crystal_shifted_along_z(header):
    # the same mistake as the example generator in the petsird repository
    _move_corners(_crystals(header).object.shape, (0.0, 0.0, -100.0))


@broken("validate_detecting_elements",
        match="not between the front and back faces")
def crystal_in_front_of_adp(header):
    _move_corners(_crystals(header, 1).object.shape, (20.0, 0.0, 0.0))


@broken("validate_material_ids", match="detectingElements.object.materialId")
def unknown_crystal_material(header):
    _crystals(header).object.material_id = 99


@broken("validate_material_ids",
        match="nonDetectingElements[0].object.materialId")
def unknown_plate_material(header):
    _plates(header, 1).object.material_id = 99


@broken("validate_material_ids", match="nonDetectingVolumes[0].materialId")
def unknown_non_detecting_volume_material(header):
    shield = petsird.GeometricShape.BoxShape(
        box_shape((300, -10, -10), (310, 10, 10)))
    header.scanner.scanner_geometry.non_detecting_volumes = [
        petsird.SolidVolume(shape=shield, material_id=99)
    ]


@broken("validate_material_ids", match="bulkMaterials ids are none")
def no_bulk_materials(header):
    header.scanner.bulk_materials = []


# --- GeometryInformation.yml


@broken("validate_box_shapes", match="front face corners are not clockwise")
def crystal_face_counterclockwise(header):
    box = _crystals(header).object.shape
    c = box.corners
    box.corners = [c[0], c[3], c[2], c[1]] + c[4:]


@broken("validate_box_shapes",
        match="first corner of the back face is not the smallest")
def crystal_face_starts_at_wrong_corner(header):
    box = _crystals(header).object.shape
    c = box.corners
    box.corners = c[:4] + [c[5], c[6], c[7], c[4]]


@broken("validate_box_shapes", match="nonDetectingElements[0].object.shape")
def plate_face_counterclockwise(header):
    box = _plates(header).object.shape.value
    c = box.corners
    box.corners = [c[0], c[3], c[2], c[1]] + c[4:]


@broken("validate_replicated_objects",
        match="replicatedModules[1].transforms is empty")
def module_type_without_modules(header):
    _module_type(header, 1).transforms = []


@broken("validate_replicated_objects",
        match="detectingElements.transforms is empty")
def module_without_crystals(header):
    _crystals(header).transforms = []


@broken("validate_replicated_objects",
        match="nonDetectingElements[0].transforms is empty")
def plate_without_transforms(header):
    _plates(header).transforms = []


@broken("validate_transforms", match="replicatedModules[0].transforms[2]")
def scaled_module_transform(header):
    _module_type(header).transforms[2].matrix[:, :3] *= 2


@broken("validate_transforms",
        match="detectingElements.transforms[1] is not a rigid")
def mirrored_crystal_transform(header):
    _crystals(header).transforms[1].matrix[2, 2] = -1


@broken("validate_transforms", match="nonDetectingElements[0].transforms[0]")
def nan_in_plate_transform(header):
    _plates(header, 1).transforms[0].matrix[0, 3] = np.nan


@broken("validate_transforms", match="gantryAlignment[0]")
def sheared_gantry_alignment(header):
    alignment = transform((0.0, 0.0, 500.0))
    alignment.matrix[0, 1] = 0.3
    header.scanner.gantry_alignment = alignment


def write_broken(name: str, folder: pathlib.Path) -> pathlib.Path:
    """write the broken file `name` into folder"""
    return write(BROKEN[name].header(), folder / f"broken_{name}.petsird")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write a valid PETSIRD file and broken copies of it.")
    parser.add_argument("folder", type=pathlib.Path)
    folder = parser.parse_args().folder
    folder.mkdir(parents=True, exist_ok=True)
    print(write(make_header(), folder / "valid.petsird"))
    for name, case in BROKEN.items():
        print(f"{write_broken(name, folder)}  (fails {', '.join(case.fails)})")


if __name__ == "__main__":
    main()
