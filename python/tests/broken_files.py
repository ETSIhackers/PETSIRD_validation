"""
Build a small valid PETSIRD file (a header and time blocks of every type), and
broken copies of it that each break one constraint checked by
petsird_validation.

make_valid() returns a Data: the header and the list of time blocks.
BROKEN maps a name to a BrokenCase: the function that breaks a Data, the
checks that must fail, and a piece of text the failure message must contain.

Run this file as a script to write the valid files and every broken file to a
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
import petsird.helpers

# A crystal is a 20 x 4 x 4 mm box. Its average detection position (ADP),
# which must be at (0,0,0), is 9 mm behind the front face.
CRYSTAL_SIZE = (20.0, 4.0, 4.0)
AVERAGE_DOI = 9.0
# Each module has 2 crystals along z and a 2 mm tungsten plate behind them.
NUM_CRYSTALS_ALONG_Z = 2
# Two module types: (radius in mm, number of modules). With 1 energy bin,
# type 0 has 4 x 2 = 8 detection bins and type 1 has 3 x 2 = 6.
MODULE_TYPES = ((100.0, 4), (150.0, 3))
NUM_TYPES = len(MODULE_TYPES)
LYSO_ID = 1
TUNGSTEN_ID = 2
# (mass number, atomic number, mass fraction) per atom
LYSO = ((175, 71, 0.714), (89, 39, 0.040), (28, 14, 0.064), (16, 8, 0.182))
TUNGSTEN = ((184, 74, 1.0), )
# The external signal declared in the exam and stored in the stream.
SIGNAL_ID = 7
# Event blocks are 1 ms long; there are 2 of them, covering [0, 2) ms.
EVENT_BLOCK_MS = 1
NUM_EVENT_BLOCKS = 2
PS_PER_MS = 10**9
# One singles unit per module: type 0 has units 0-3, type 1 units 4-6.
SINGLES_UNIT_LUTS = ((0, 1, 2, 3), (4, 5, 6))
NUM_SINGLES_UNITS = 7

# ---------------------------------------------------------------- header


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


def bin_edges(*edges: float) -> petsird.BinEdges:
    return petsird.BinEdges(edges=np.array(edges, dtype=np.float32))


def make_detection_efficiencies(
        scanner: petsird.ScannerInformation) -> petsird.DetectionEfficiencies:
    """efficiencies of 1, with one geometric group (SGID 0) per type pair"""
    num_modules = [n for _, n in MODULE_TYPES]
    bins = [
        petsird.helpers.get_num_detection_bins(scanner, t)
        for t in range(NUM_TYPES)
    ]
    bins_per_module = [bins[t] // num_modules[t] for t in range(NUM_TYPES)]
    lut = [[[[0] * num_modules[t2] for _ in range(num_modules[t1])]
            for t2 in range(t1 + 1)] for t1 in range(NUM_TYPES)]
    vectors = [[[
        petsird.ModulePairEfficiencies(
            values=[[1.0] * bins_per_module[t2]
                    for _ in range(bins_per_module[t1])],
            sgid=0)
    ] for t2 in range(t1 + 1)] for t1 in range(NUM_TYPES)]
    return petsird.DetectionEfficiencies(
        calibration_factor=1.0,
        detection_bin_efficiencies=[[1.0] * n for n in bins],
        module_pair_sgidlut=lut,
        module_pair_efficiencies_vectors=vectors)


def make_header() -> petsird.Header:
    """a small scanner that passes every check"""
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
        tof_bin_edges=[[bin_edges(-300, -180, -60, 60, 180, 300)] * (i + 1)
                       for i in range(NUM_TYPES)],
        tof_resolution=[[60.0] * (i + 1) for i in range(NUM_TYPES)],
        event_energy_bin_edges=[bin_edges(450, 650)] * NUM_TYPES,
        energy_resolution_at_511=[0.1] * NUM_TYPES,
        single_event_policy=petsird.SingleEventPolicy.ALL,
        prompt_event_policy=petsird.CoincidencePolicy.REJECT_HIGHER_MULTIPLES,
        delayed_event_policy=petsird.CoincidencePolicy.REJECT_HIGHER_MULTIPLES,
        triple_event_policy=petsird.TripleEventPolicy.NONE,
        quadruple_event_policy=petsird.QuadrupleEventPolicy.NONE,
        singles_histogram_level=petsird.SinglesHistogramLevelType.MODULE,
        module_singles_unit_idx_lu_ts=[list(lut) for lut in SINGLES_UNIT_LUTS],
        singles_histogram_energy_bin_edges=[bin_edges(400, 650)] * NUM_TYPES,
    )
    scanner.detection_efficiencies = make_detection_efficiencies(scanner)
    signal = petsird.ExternalSignal(id=SIGNAL_ID,
                                    description="respiratory trace")
    exam = petsird.ExamInformation(modality="PT", external_signals=[signal])
    return petsird.Header(exam=exam,
                          scanner=scanner,
                          contains_weighted_event_time_blocks=False)


# ---------------------------------------------------------------- time blocks


def interval(start: int, stop: int) -> petsird.TimeInterval:
    return petsird.TimeInterval(start=start, stop=stop)


def coincidence(bin1: int, bin2: int, tof_idx: int = 1):
    return petsird.CoincidenceEvent(detection_bins=[bin1, bin2],
                                    tof_idx=tof_idx)


def make_event_block(start_ms: int) -> petsird.EventTimeBlock:
    """one single per module type, one prompt and one delayed per type pair

    Coincidences between modules of the same type have bin1 >= bin2, as the
    ordering rule requires.
    """
    singles = [[
        petsird.SingleEvent(detection_bin=1, time_offset_in_time_block=1000)
    ] for _ in range(NUM_TYPES)]
    prompts = [[[coincidence(5, 2) if t1 == t2 else coincidence(3, 4)]
                for t2 in range(t1 + 1)] for t1 in range(NUM_TYPES)]
    delayeds = [[[coincidence(4, 4) if t1 == t2 else coincidence(1, 0)]
                 for t2 in range(t1 + 1)] for t1 in range(NUM_TYPES)]
    time_interval = interval(start_ms, start_ms + EVENT_BLOCK_MS)
    return petsird.EventTimeBlock(time_interval=time_interval,
                                  single_events=singles,
                                  prompt_events=prompts,
                                  delayed_events=delayeds)


def make_blocks() -> list[petsird.TimeBlock]:
    """one time block of every type except WeightedEventTimeBlock"""
    TB = petsird.TimeBlock
    end = NUM_EVENT_BLOCKS * EVENT_BLOCK_MS
    return [
        TB.ExternalSignalTimeBlock(
            petsird.ExternalSignalTimeBlock(time_interval=interval(0, end),
                                            signal_id=SIGNAL_ID,
                                            signal_values=[0.0, 1.0])),
        TB.BedMovementTimeBlock(
            petsird.BedMovementTimeBlock(time_interval=interval(0, 1),
                                         transform=transform((0, 0, 10)))),
        TB.GantryMovementTimeBlock(
            petsird.GantryMovementTimeBlock(
                time_interval=interval(0, 1),
                transforms=[transform() for _ in range(NUM_TYPES)])),
        *(TB.EventTimeBlock(make_event_block(k * EVENT_BLOCK_MS))
          for k in range(NUM_EVENT_BLOCKS)),
        TB.DeadTimeTimeBlock(
            petsird.DeadTimeTimeBlock(time_interval=interval(0, end))),
        TB.SinglesHistogramTimeBlock(
            petsird.SinglesHistogramTimeBlock(
                time_interval=interval(0, end),
                singles_per_singles_unit_histogram=[[100]] *
                NUM_SINGLES_UNITS)),
    ]


@dataclass
class Data:
    """A PETSIRD header and its time blocks."""
    header: petsird.Header
    blocks: list[petsird.TimeBlock]

    def blocks_of(self, tag: str) -> list:
        """the time blocks of one type, e.g. "EventTimeBlock" (their values)"""
        return [b.value for b in self.blocks if b.tag == tag]


def make_valid() -> Data:
    return Data(make_header(), make_blocks())


def make_weighted(data: Data) -> Data:
    """Replace the event blocks by WeightedEventTimeBlocks with weights 1.

    Delayeds are not stored: in the model, WeightedEventTimeBlock.delayedEvents
    is a list of floats rather than of events.
    """
    data.header.contains_weighted_event_time_blocks = True
    data.header.scanner.delayed_event_policy = petsird.CoincidencePolicy.NONE
    for k, time_block in enumerate(data.blocks):
        if time_block.tag != "EventTimeBlock":
            continue
        block = time_block.value
        data.blocks[k] = petsird.TimeBlock.WeightedEventTimeBlock(
            petsird.WeightedEventTimeBlock(
                time_interval=block.time_interval,
                single_events=block.single_events,
                single_events_weights=[[1.0] * len(events)
                                       for events in block.single_events],
                prompt_events=block.prompt_events,
                prompt_events_weights=[[[1.0] * len(events) for events in row]
                                       for row in block.prompt_events]))
    return data


def write(data: Data,
          path: pathlib.Path,
          ndjson: bool = False) -> pathlib.Path:
    """write data to a binary (default) or NDJSON PETSIRD file"""
    writer_class = (petsird.NDJsonPETSIRDWriter
                    if ndjson else petsird.BinaryPETSIRDWriter)
    with writer_class(str(path)) as writer:
        writer.write_header(data.header)
        writer.write_time_blocks(data.blocks)
    return path


# ---------------------------------------------------------------- broken cases


@dataclass(frozen=True)
class BrokenCase:
    breaks: Callable[[Data], None]
    fails: tuple[str, ...]  # names of the checks that must fail
    match: str  # text the failure message must contain

    def data(self) -> Data:
        data = make_valid()
        self.breaks(data)
        return data


BROKEN: dict[str, BrokenCase] = {}


def broken(*fails: str, match: str = ""):
    """register a function that breaks a valid Data"""

    def register(breaks):
        BROKEN[breaks.__name__] = BrokenCase(breaks, fails, match)
        return breaks

    return register


def _module_type(data, t=0):
    return data.header.scanner.scanner_geometry.replicated_modules[t]


def _crystals(data, t=0):
    return _module_type(data, t).object.detecting_elements


def _plates(data, t=0):
    return _module_type(data, t).object.non_detecting_elements[0]


def _move_corners(box: petsird.BoxShape, shift) -> None:
    for corner in box.corners:
        corner.c = corner.c + np.asarray(shift, dtype=np.float32)


# --- DetectorInformation.yml


@broken("validate_scanner_geometry", match="replicatedModules is empty")
def no_module_types(data):
    scanner = data.header.scanner
    scanner.scanner_geometry.replicated_modules = []
    scanner.tof_bin_edges = []
    scanner.tof_resolution = []
    scanner.event_energy_bin_edges = []
    scanner.energy_resolution_at_511 = []
    scanner.module_singles_unit_idx_lu_ts = []
    scanner.singles_histogram_energy_bin_edges = []
    scanner.detection_efficiencies = petsird.DetectionEfficiencies()
    data.blocks = []  # every event list has one entry per module type


@broken("validate_detecting_elements", match="is not along +x")
def crystal_facing_backwards(data):
    box = _crystals(data).object.shape
    box.corners = box.corners[4:] + box.corners[:4]


@broken("validate_detecting_elements", match="outside the box")
def crystal_shifted_along_z(data):
    # the same mistake as the example generator in the petsird repository
    _move_corners(_crystals(data).object.shape, (0.0, 0.0, -100.0))


@broken("validate_detecting_elements",
        match="not between the front and back faces")
def crystal_in_front_of_adp(data):
    _move_corners(_crystals(data, 1).object.shape, (20.0, 0.0, 0.0))


@broken("validate_material_ids", match="detectingElements.object.materialId")
def unknown_crystal_material(data):
    _crystals(data).object.material_id = 99


@broken("validate_material_ids",
        match="nonDetectingElements[0].object.materialId")
def unknown_plate_material(data):
    _plates(data, 1).object.material_id = 99


@broken("validate_material_ids", match="nonDetectingVolumes[0].materialId")
def unknown_non_detecting_volume_material(data):
    shield = petsird.GeometricShape.BoxShape(
        box_shape((300, -10, -10), (310, 10, 10)))
    data.header.scanner.scanner_geometry.non_detecting_volumes = [
        petsird.SolidVolume(shape=shield, material_id=99)
    ]


@broken("validate_material_ids", match="bulkMaterials ids are none")
def no_bulk_materials(data):
    data.header.scanner.bulk_materials = []


# --- GeometryInformation.yml


@broken("validate_box_shapes", match="front face corners are not clockwise")
def crystal_face_counterclockwise(data):
    box = _crystals(data).object.shape
    c = box.corners
    box.corners = [c[0], c[3], c[2], c[1]] + c[4:]


@broken("validate_box_shapes",
        match="first corner of the back face is not the smallest")
def crystal_face_starts_at_wrong_corner(data):
    box = _crystals(data).object.shape
    c = box.corners
    box.corners = c[:4] + [c[5], c[6], c[7], c[4]]


@broken("validate_box_shapes", match="nonDetectingElements[0].object.shape")
def plate_face_counterclockwise(data):
    box = _plates(data).object.shape.value
    c = box.corners
    box.corners = [c[0], c[3], c[2], c[1]] + c[4:]


# Without modules, the singles-unit LUT and the events of that type no
# longer fit, so those checks fail too.
@broken("validate_replicated_objects",
        "validate_singles_unit_luts",
        "validate_detection_bins",
        match="replicatedModules[1].transforms is empty")
def module_type_without_modules(data):
    _module_type(data, 1).transforms = []


# Without crystals, type 0 has no detection bins, so its events don't fit.
@broken("validate_replicated_objects",
        "validate_detection_bins",
        match="detectingElements.transforms is empty")
def module_without_crystals(data):
    _crystals(data).transforms = []


@broken("validate_replicated_objects",
        match="nonDetectingElements[0].transforms is empty")
def plate_without_transforms(data):
    _plates(data).transforms = []


@broken("validate_transforms", match="replicatedModules[0].transforms[2]")
def scaled_module_transform(data):
    _module_type(data).transforms[2].matrix[:, :3] *= 2


@broken("validate_transforms",
        match="detectingElements.transforms[1] is not a rigid")
def mirrored_crystal_transform(data):
    _crystals(data).transforms[1].matrix[2, 2] = -1


@broken("validate_transforms", match="nonDetectingElements[0].transforms[0]")
def nan_in_plate_transform(data):
    _plates(data, 1).transforms[0].matrix[0, 3] = np.nan


@broken("validate_transforms", match="gantryAlignment[0]")
def sheared_gantry_alignment(data):
    alignment = transform((0.0, 0.0, 500.0))
    alignment.matrix[0, 1] = 0.3
    data.header.scanner.gantry_alignment = alignment


# --- MaterialInformation.yml


@broken("validate_material_ids_unique", match="duplicate material ID")
def duplicate_material_id(data):
    data.header.scanner.bulk_materials.append(
        bulk_material(LYSO_ID, "LYSO copy", 7.1, LYSO))


@broken("validate_material_fraction_count",
        match="5 atoms but 4 mass fractions")
def atom_without_mass_fraction(data):
    data.header.scanner.bulk_materials[0].atoms.append(
        petsird.Atom(mass_number=12, atomic_number=6))


@broken("validate_material_fraction_sum", match="mass fractions sum to 0.9")
def mass_fractions_not_summing_to_one(data):
    material = data.header.scanner.bulk_materials[0]
    material.mass_fractions = [0.9 * f for f in material.mass_fractions]


# --- ScannerInformation.yml


@broken("validate_bin_edges",
        match="eventEnergyBinEdges[1]: edges must be strictly increasing")
def decreasing_energy_bin_edges(data):
    data.header.scanner.event_energy_bin_edges[1] = bin_edges(650, 450)


@broken("validate_scanner_array_dimensions",
        match="energyResolutionAt511: expected 2 entries, got 1")
def missing_energy_resolution(data):
    data.header.scanner.energy_resolution_at_511 = [0.1]


@broken("validate_scanner_resolutions",
        match="tofResolution[1][0] must be positive")
def zero_tof_resolution(data):
    data.header.scanner.tof_resolution[1][0] = 0.0


# With singlesHistogramLevel NONE, the singles-histogram block is not
# allowed either.
@broken("validate_singles_histogram_dimensions",
        "validate_singles_histogram",
        match="Singles histogram level NONE requires empty LUTs")
def singles_luts_with_level_none(data):
    data.header.scanner.singles_histogram_level = (
        petsird.SinglesHistogramLevelType.NONE)


@broken("validate_collimator_type", match="collimatorType is 'PARALLEL'")
def unknown_collimator_type(data):
    data.header.scanner.collimator_type = "PARALLEL"


# --- DetectionEfficiencies.yml


@broken("validate_detection_bin_efficiency_dimensions",
        "validate_number_module_types_consistency",
        match="detectionBinEfficiencies")
def missing_detection_bin_efficiencies(data):
    efficiencies = data.header.scanner.detection_efficiencies
    efficiencies.detection_bin_efficiencies.pop()


@broken("validate_module_pair_sgid_dimensions",
        match="modulePairSGIDLUT: expected 2 module-type rows, got 1")
def missing_sgid_lut_row(data):
    efficiencies = data.header.scanner.detection_efficiencies
    efficiencies.module_pair_sgidlut.pop()


@broken("validate_sgid_ranges", match="SGID is 5, expected 0")
def wrong_sgid_in_efficiencies(data):
    efficiencies = data.header.scanner.detection_efficiencies
    efficiencies.module_pair_efficiencies_vectors[1][0][0].sgid = 5


@broken("validate_efficiency_values",
        match="detectionBinEfficiencies[0][3] is non-finite")
def nan_detection_bin_efficiency(data):
    efficiencies = data.header.scanner.detection_efficiencies
    efficiencies.detection_bin_efficiencies[0][3] = math.nan


# --- SinglesHistograms.yml


@broken("validate_singles_unit_luts",
        match="moduleSinglesUnitIdxLUTs[0][1] is -2")
def singles_unit_below_minus_one(data):
    data.header.scanner.module_singles_unit_idx_lu_ts[0][1] = -2


# --- ExamInformation.yml


@broken("validate_exam", match="id 7 is used by 2 signals")
def duplicate_external_signal_id(data):
    data.header.exam.external_signals.append(
        petsird.ExternalSignal(id=SIGNAL_ID, description="second trace"))


# --- TimeFrameInformation.yml


@broken("validate_time_interval", match="timeInterval start 5 ms is after")
def bed_movement_ends_before_it_starts(data):
    data.blocks_of("BedMovementTimeBlock")[0].time_interval = interval(5, 1)


# --- Protocol.yml: event blocks


@broken("validate_event_list_shapes",
        match="promptEvents has 3 entries, expected 2")
def prompt_rows_repeated(data):
    # the same mistake as the example generator in the petsird repository
    block = data.blocks_of("EventTimeBlock")[0]
    block.prompt_events.append(block.prompt_events[1])


@broken("validate_event_list_shapes",
        match="delayedEvents has 2 entries but delayedEventPolicy is NONE")
def delayeds_stored_with_policy_none(data):
    data.header.scanner.delayed_event_policy = petsird.CoincidencePolicy.NONE


@broken("validate_event_order", match="promptEvents[0][0]: 1 of 1 events")
def unordered_coincidence(data):
    data.blocks_of("EventTimeBlock")[1].prompt_events[0][0] = [
        coincidence(2, 5)
    ]


@broken("validate_event_block_type",
        match="containsWeightedEventTimeBlocks=True")
def weighted_blocks_declared_but_not_stored(data):
    data.header.contains_weighted_event_time_blocks = True


@broken("validate_weights",
        match="promptEventsWeights[1][0] has 0 weight entries but 1")
def prompt_weight_missing(data):
    make_weighted(data)
    data.blocks_of(
        "WeightedEventTimeBlock")[0].prompt_events_weights[1][0] = []


# --- Events.yml


@broken("validate_detection_bins", match="have a detection bin out of range")
def detection_bin_out_of_range(data):
    data.blocks_of("EventTimeBlock")[0].prompt_events[0][0] = [
        coincidence(99, 2)
    ]


@broken("validate_tof_indices", match="have a TOF index out of range")
def tof_index_out_of_range(data):
    data.blocks_of("EventTimeBlock")[0].prompt_events[1][1] = [
        coincidence(5, 2, tof_idx=99)
    ]


@broken("validate_singles_times", match="beyond the block length")
def single_after_block_end(data):
    single = data.blocks_of("EventTimeBlock")[1].single_events[1][0]
    single.time_offset_in_time_block = 2 * EVENT_BLOCK_MS * PS_PER_MS


# --- Protocol.yml: other blocks


@broken("validate_external_signal",
        match="signalID is 99, but declared ids are [7]")
def undeclared_external_signal(data):
    data.blocks_of("ExternalSignalTimeBlock")[0].signal_id = 99


@broken("validate_bed_movement", match="transform[0] is not a rigid")
def scaled_bed_transform(data):
    data.blocks_of("BedMovementTimeBlock")[0].transform.matrix[:, :3] *= 2


@broken("validate_gantry_movement",
        match="transforms has 1 entries, expected 2")
def gantry_movement_for_one_module_type(data):
    data.blocks_of("GantryMovementTimeBlock")[0].transforms.pop()


@broken(
    "validate_singles_histogram",
    match="singlesPerSinglesUnitHistogram[0] has 2 energy bins, expected 1")
def singles_histogram_with_extra_energy_bin(data):
    histogram = data.blocks_of("SinglesHistogramTimeBlock")[0]
    histogram.singles_per_singles_unit_histogram[0] = [60, 40]


# --- Protocol.yml: whole stream


@broken("validate_dead_time_coverage",
        match="2 ms of event time is not covered by DeadTimeTimeBlocks")
def no_dead_time_blocks(data):
    data.blocks = [b for b in data.blocks if b.tag != "DeadTimeTimeBlock"]


@broken("validate_singles_histogram_coverage", match="gaps in ms: [1, 2)")
def singles_histograms_stop_early(data):
    histogram = data.blocks_of("SinglesHistogramTimeBlock")[0]
    histogram.time_interval = interval(0, 1)


def write_broken(name: str, folder: pathlib.Path) -> pathlib.Path:
    """write the broken file `name` into folder"""
    return write(BROKEN[name].data(), folder / f"broken_{name}.petsird")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Write valid PETSIRD files and broken copies of them.")
    parser.add_argument("folder", type=pathlib.Path)
    folder = parser.parse_args().folder
    folder.mkdir(parents=True, exist_ok=True)
    print(write(make_valid(), folder / "valid.petsird"))
    print(write(make_weighted(make_valid()),
                folder / "valid_weighted.petsird"))
    for name, case in BROKEN.items():
        print(f"{write_broken(name, folder)}  (fails {', '.join(case.fails)})")


if __name__ == "__main__":
    main()
