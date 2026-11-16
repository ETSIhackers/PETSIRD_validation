"""
Validation functions for model/Protocol.yml:
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Hong Phuc Vo

from collections import Counter
from collections.abc import Iterator, Sequence
from dataclasses import dataclass, field

import petsird
import petsird.helpers

from ._common import num_module_types, num_modules
from .geometry_information import check_rigid

LEVEL = petsird.SinglesHistogramLevelType
EventBlock = petsird.EventTimeBlock | petsird.WeightedEventTimeBlock
Interval = tuple[int, int]


def _is_weighted(block: EventBlock) -> bool:
    return isinstance(block, petsird.WeightedEventTimeBlock)


def event_bins(event) -> list[int]:
    """The detection bins of a single, coincidence, triple or quadruple."""
    if isinstance(event, petsird.SingleEvent):
        return [int(event.detection_bin)]
    return [int(b) for b in event.detection_bins]


def event_lists(
    header: petsird.Header,
    block: EventBlock,
    include_singles: bool = True
) -> Iterator[tuple[str, tuple[int, ...], Sequence]]:
    """Yield (name, module types, events) for every event list in the block.

    Lists at indices that break the shape rules are skipped
    (validate_event_list_shapes reports those).
    """
    T = num_module_types(header)
    if include_singles:
        for t, events in enumerate(block.single_events[:T]):
            yield f"singleEvents[{t}]", (t, ), events
    matrices = [("promptEvents", block.prompt_events)]
    if not _is_weighted(block):
        matrices.append(("delayedEvents", block.delayed_events))
    for name, matrix in matrices:
        for t1, row in enumerate(matrix[:T]):
            for t2, events in enumerate(row[:t1 + 1]):
                yield f"{name}[{t1}][{t2}]", (t1, t2), events
    for t1, a in enumerate(block.triple_events[:T]):
        for t2, b in enumerate(a[:t1 + 1]):
            for t3, events in enumerate(b[:t2 + 1]):
                yield f"tripleEvents[{t1}][{t2}][{t3}]", (t1, t2, t3), events
    for t1, a in enumerate(block.quadruple_events[:T]):
        for t2, b in enumerate(a[:t1 + 1]):
            for t3, c in enumerate(b[:t2 + 1]):
                for t4, events in enumerate(c[:t3 + 1]):
                    yield (f"quadrupleEvents[{t1}][{t2}][{t3}][{t4}]",
                           (t1, t2, t3, t4), events)


def raise_for_events(bad: list[int], events: Sequence, name: str, problem: str,
                     detail: str) -> None:
    """Raise one ValueError summarising the bad events of a list."""
    if bad:
        raise ValueError(
            f"{name}: {len(bad)} of {len(events)} events {problem}; first is "
            f"event {bad[0]} {detail}")


# ---------------------------------------------------------------- event blocks


def validate_event_block_type(header: petsird.Header,
                              block: EventBlock) -> None:
    """event blocks are weighted exactly when the header says so

    Protocol.yml: Header.containsWeightedEventTimeBlocks, WeightedEventTimeBlock
    """
    weighted = _is_weighted(block)
    declared = header.contains_weighted_event_time_blocks
    if weighted != declared:
        raise ValueError(
            f"header says containsWeightedEventTimeBlocks={declared}, but this "
            f"is a{' weighted' if weighted else 'n unweighted'} event block")


def _check_nested(node: Sequence,
                  num_types: int,
                  depth: int,
                  name: str,
                  level: int = 0,
                  last_index: int = 0) -> None:
    """Level 0 has one entry per module type; entry [.., i] has i+1 children."""
    expected = num_types if level == 0 else last_index + 1
    if len(node) != expected:
        raise ValueError(
            f"{name} has {len(node)} entries, expected {expected}")
    if level + 1 < depth:
        for i, child in enumerate(node):
            _check_nested(child, num_types, depth, f"{name}[{i}]", level + 1,
                          i)


def validate_event_list_shapes(header: petsird.Header,
                               block: EventBlock) -> None:
    """event lists are empty when their policy is NONE, otherwise nested by module type

    Protocol.yml: EventTimeBlock.singleEvents, promptEvents, delayedEvents,
    tripleEvents, quadrupleEvents
    """
    s = header.scanner
    T = num_module_types(header)
    lists = (
        ("singleEvents", block.single_events, s.single_event_policy
         != petsird.SingleEventPolicy.NONE, "singleEventPolicy", 1),
        ("promptEvents", block.prompt_events, s.prompt_event_policy
         != petsird.CoincidencePolicy.NONE, "promptEventPolicy", 2),
        ("delayedEvents", block.delayed_events, s.delayed_event_policy
         != petsird.CoincidencePolicy.NONE, "delayedEventPolicy", 2),
        ("tripleEvents", block.triple_events, s.triple_event_policy
         != petsird.TripleEventPolicy.NONE, "tripleEventPolicy", 3),
        ("quadrupleEvents", block.quadruple_events, s.quadruple_event_policy
         != petsird.QuadrupleEventPolicy.NONE, "quadrupleEventPolicy", 4),
    )
    for name, nested, stored, policy, depth in lists:
        if not stored:
            if len(nested):
                raise ValueError(f"{name} has {len(nested)} entries but "
                                 f"{policy} is NONE; expected 0")
        elif not len(nested):
            raise ValueError(f"{name} is empty but {policy} is not NONE; "
                             "expected one entry per module type")
        else:
            _check_nested(nested, T, depth, name)


def validate_event_order(header: petsird.Header, block: EventBlock) -> None:
    """events are ordered: t1 > t2 or bin1 >= bin2; multiples by (type, bin)

    Protocol.yml: EventTimeBlock.promptEvents, tripleEvents (ordering notes)
    """
    for name, types, events in event_lists(header,
                                           block,
                                           include_singles=False):
        if len(types) == 2:
            bad = [
                k for k, ev in enumerate(events)
                if not petsird.helpers.are_detections_ordered(
                    types, ev.detection_bins[0], ev.detection_bins[1])
            ]
        else:
            bad = []
            for k, ev in enumerate(events):
                pairs = list(zip(types, event_bins(ev)))
                if any(a < b for a, b in zip(pairs, pairs[1:])):
                    bad.append(k)
        raise_for_events(
            bad, events, name, "are not ordered",
            f"with bins {event_bins(events[bad[0]])}" if bad else "")


def _check_same_shape(events: Sequence, weights: Sequence, depth: int,
                      name: str) -> None:
    if len(events) != len(weights):
        raise ValueError(f"{name} has {len(weights)} weight entries but "
                         f"{len(events)} event entries")
    if depth > 1:
        for k, (e, w) in enumerate(zip(events, weights)):
            _check_same_shape(e, w, depth - 1, f"{name}[{k}]")


def validate_weights(header: petsird.Header,
                     block: petsird.WeightedEventTimeBlock) -> None:
    """every list of weights has the same nested sizes as its list of events

    Protocol.yml: WeightedEventTimeBlock
    """
    _check_same_shape(block.single_events, block.single_events_weights, 2,
                      "singleEventsWeights")
    _check_same_shape(block.prompt_events, block.prompt_events_weights, 3,
                      "promptEventsWeights")
    _check_same_shape(block.delayed_events, block.delayed_events_weights, 3,
                      "delayedEventsWeights")
    _check_same_shape(block.triple_events, block.triple_events_weights, 4,
                      "tripleEventsWeights")
    _check_same_shape(block.quadruple_events, block.quadruple_events_weights,
                      5, "quadrupleEventsWeights")


# ---------------------------------------------------------------- other blocks


def validate_external_signal(header: petsird.Header,
                             block: petsird.ExternalSignalTimeBlock) -> None:
    """signalID is listed in exam.externalSignals

    Protocol.yml: ExternalSignalTimeBlock.signalID
    """
    if header.exam is None:
        raise ValueError(f"signalID is {block.signal_id}, but the header has "
                         "no exam information declaring external signals")
    declared = {s.id for s in header.exam.external_signals}
    if block.signal_id not in declared:
        raise ValueError(
            f"signalID is {block.signal_id}, but declared ids are "
            f"{sorted(declared)}")


def validate_gantry_movement(header: petsird.Header,
                             block: petsird.GantryMovementTimeBlock) -> None:
    """one rigid transform per module type

    Protocol.yml: GantryMovementTimeBlock.transforms
    """
    T = num_module_types(header)
    if len(block.transforms) != T:
        raise ValueError(f"transforms has {len(block.transforms)} entries, "
                         f"expected {T} (one per module type)")
    check_rigid(block.transforms, "transforms")


def validate_bed_movement(header: petsird.Header,
                          block: petsird.BedMovementTimeBlock) -> None:
    """bed transform is rigid

    Protocol.yml: BedMovementTimeBlock.transform
    """
    check_rigid([block.transform], "transform")


def validate_singles_histogram(
        header: petsird.Header,
        block: petsird.SinglesHistogramTimeBlock) -> None:
    """singles histograms are allowed by singlesHistogramLevel and have the right shape

    Protocol.yml: SinglesHistogramTimeBlock
    """
    s = header.scanner
    level = s.singles_histogram_level
    per_unit = block.singles_per_singles_unit_histogram
    per_bin = block.singles_per_detection_bin_histogram
    if level == LEVEL.NONE:
        raise ValueError("singlesHistogramLevel is NONE, so there must be no "
                         "SinglesHistogramTimeBlock in the stream")

    if level == LEVEL.MODULE:
        if per_bin:
            raise ValueError("singlesPerDetectionBinHistogram must be empty "
                             "when singlesHistogramLevel is MODULE")
        num_units = petsird.helpers.get_num_singles_units(s)
        if len(per_unit) != num_units:
            raise ValueError(
                f"singlesPerSinglesUnitHistogram has "
                f"{len(per_unit)} singles units, expected "
                f"{num_units} (max of moduleSinglesUnitIdxLUTs + 1)")
        energy_bins: dict[int, set[int]] = {}
        for t, lut in enumerate(s.module_singles_unit_idx_lu_ts):
            n = s.singles_histogram_energy_bin_edges[t].number_of_bins()
            for unit in lut:
                if unit >= 0:
                    energy_bins.setdefault(int(unit), set()).add(n)
        for unit, counts in enumerate(per_unit):
            options = energy_bins.get(unit, set())
            if len(options) > 1:
                raise ValueError(
                    f"singles unit {unit} contains modules with different "
                    f"numbers of singles energy bins {sorted(options)}")
            if options and len(counts) != next(iter(options)):
                raise ValueError(
                    f"singlesPerSinglesUnitHistogram[{unit}] has {len(counts)} "
                    f"energy bins, expected {next(iter(options))}")
    else:  # LEVEL.ALL
        if per_unit:
            raise ValueError("singlesPerSinglesUnitHistogram must be empty "
                             "when singlesHistogramLevel is ALL")
        T = num_module_types(header)
        if len(per_bin) != T:
            raise ValueError(f"singlesPerDetectionBinHistogram has "
                             f"{len(per_bin)} entries, expected {T}")
        for t, counts in enumerate(per_bin):
            rep_module = s.scanner_geometry.replicated_modules[t]
            expected = (
                num_modules(header, t) *
                len(rep_module.object.detecting_elements.transforms) *
                s.singles_histogram_energy_bin_edges[t].number_of_bins())
            if len(counts) != expected:
                raise ValueError(
                    f"singlesPerDetectionBinHistogram[{t}] has {len(counts)} "
                    f"bins, expected {expected} (modules x elements x singles "
                    "energy bins)")


# ---------------------------------------------------------------- whole stream


@dataclass
class StreamSummary:
    """What was seen in the time-block stream."""
    blocks_read: int = 0
    block_counts: Counter = field(default_factory=Counter)
    event_counts: Counter = field(default_factory=Counter)
    event_intervals: list[Interval] = field(default_factory=list)
    dead_time_intervals: list[Interval] = field(default_factory=list)
    singles_histogram_intervals: list[Interval] = field(default_factory=list)

    def add(self, block: petsird.TimeBlock) -> None:
        tag, value = block.tag, block.value
        self.blocks_read += 1
        self.block_counts[tag] += 1
        interval = (int(value.time_interval.start),
                    int(value.time_interval.stop))
        if tag in ("EventTimeBlock", "WeightedEventTimeBlock"):
            self.event_intervals.append(interval)
            self.event_counts["prompts"] += sum(
                len(x) for row in value.prompt_events for x in row)
            if tag == "EventTimeBlock":
                self.event_counts["delayeds"] += sum(
                    len(x) for row in value.delayed_events for x in row)
            self.event_counts["singles"] += sum(
                len(x) for x in value.single_events)
        elif tag == "DeadTimeTimeBlock":
            self.dead_time_intervals.append(interval)
        elif tag == "SinglesHistogramTimeBlock":
            self.singles_histogram_intervals.append(interval)


def merge_intervals(intervals: list[Interval]) -> list[Interval]:
    """Union of half-open intervals [start, stop), as sorted disjoint intervals.

    Empty intervals (start >= stop) cover no time and are dropped.
    """
    merged: list[Interval] = []
    for start, stop in sorted(i for i in intervals if i[0] < i[1]):
        if merged and start <= merged[-1][1]:
            merged[-1] = (merged[-1][0], max(merged[-1][1], stop))
        else:
            merged.append((start, stop))
    return merged


def uncovered(needed: list[Interval],
              covering: list[Interval]) -> list[Interval]:
    """Parts of the union of `needed` that the union of `covering` misses."""
    cover = merge_intervals(covering)
    gaps = []
    for start, stop in merge_intervals(needed):
        position = start
        for c_start, c_stop in cover:
            if c_stop <= position:
                continue
            if c_start >= stop:
                break
            if c_start > position:
                gaps.append((position, c_start))
            position = max(position, c_stop)
            if position >= stop:
                break
        if position < stop:
            gaps.append((position, stop))
    return gaps


def _check_coverage(summary: StreamSummary, covering: list[Interval],
                    what: str) -> None:
    gaps = uncovered(summary.event_intervals, covering)
    if gaps:
        total = sum(stop - start for start, stop in gaps)
        shown = ", ".join(f"[{a}, {b})" for a, b in gaps[:5])
        more = f" and {len(gaps) - 5} more" if len(gaps) > 5 else ""
        raise ValueError(f"{total} ms of event time is not covered by {what} "
                         f"({len(covering)} found); gaps in ms: {shown}{more}")


def validate_dead_time_coverage(header: petsird.Header,
                                summary: StreamSummary) -> None:
    """DeadTimeTimeBlocks cover all the time covered by event blocks

    Protocol.yml: DeadTimeTimeBlock
    """
    _check_coverage(summary, summary.dead_time_intervals, "DeadTimeTimeBlocks")


def validate_singles_histogram_coverage(header: petsird.Header,
                                        summary: StreamSummary) -> None:
    """if singles histograms are stored, they cover all the time covered by event blocks

    Protocol.yml: SinglesHistogramTimeBlock
    """
    if header.scanner.singles_histogram_level != LEVEL.NONE:
        _check_coverage(summary, summary.singles_histogram_intervals,
                        "SinglesHistogramTimeBlocks")


protocol_tests_suite = {
    "event list shapes": {
        "func": validate_event_list_shapes,
        "level": "event_block",
    },
    "event order": {
        "func": validate_event_order,
        "level": "event_block",
    },
    "event block type": {
        "func": validate_event_block_type,
        "level": "event_block",
    },
    "weights": {
        "func": validate_weights,
        "level": "block",
        "block_types": ("WeightedEventTimeBlock", ),
    },
    "external signal": {
        "func": validate_external_signal,
        "level": "block",
        "block_types": ("ExternalSignalTimeBlock", ),
    },
    "bed movement": {
        "func": validate_bed_movement,
        "level": "block",
        "block_types": ("BedMovementTimeBlock", ),
    },
    "gantry movement": {
        "func": validate_gantry_movement,
        "level": "block",
        "block_types": ("GantryMovementTimeBlock", ),
    },
    "singles histogram": {
        "func": validate_singles_histogram,
        "level": "block",
        "block_types": ("SinglesHistogramTimeBlock", ),
    },
    "dead time coverage": {
        "func": validate_dead_time_coverage,
        "level": "stream",
    },
    "singles histogram coverage": {
        "func": validate_singles_histogram_coverage,
        "level": "stream",
    },
}
