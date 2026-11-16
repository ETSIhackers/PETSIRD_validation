"""
Validation functions for model/Events.yml: the fields of SingleEvent,
CoincidenceEvent, TripleEvent and QuadrupleEvent.

All functions take (header, block), where block is an EventTimeBlock or
WeightedEventTimeBlock. TimeInterval is in ms, while
SingleEvent.timeOffsetInTimeBlock is in ps.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Hong Phuc Vo

import petsird
import petsird.helpers

from ._common import num_module_types
from .protocol import EventBlock, event_bins, event_lists, raise_for_events

PS_PER_MS = 10**9
MAX_SINGLES_INTERVAL_PS = 2**32


def validate_detection_bins(header: petsird.Header, block: EventBlock) -> None:
    """every detection bin is < the number of detection bins of its module type

    Events.yml: SingleEvent.detectionBin, CoincidenceEvent.detectionBins, ...;
    DetectorInformation.yml: DetectionBin
    """
    for name, types, events in event_lists(header, block):
        limits = [
            petsird.helpers.get_num_detection_bins(header.scanner, t)
            for t in types
        ]
        bad = [
            k for k, ev in enumerate(events)
            if any(b >= n for b, n in zip(event_bins(ev), limits))
        ]
        if bad:
            raise_for_events(
                bad, events, name, "have a detection bin out of range",
                f"with bins {event_bins(events[bad[0]])}, but module types "
                f"{list(types)} have {limits} bins")


def validate_tof_indices(header: petsird.Header, block: EventBlock) -> None:
    """TOF indices are < the number of TOF bins for the module-type pair

    Events.yml: CoincidenceEvent.tofIdx, TripleEvent.tofIndices,
    QuadrupleEvent.tofIndices
    """
    tof = header.scanner.tof_bin_edges
    for name, types, events in event_lists(header,
                                           block,
                                           include_singles=False):
        # TOF of detection k (k >= 1) is relative to detection 0
        limits = [tof[types[0]][t].number_of_bins() for t in types[1:]]
        if len(types) == 2:
            bad = [k for k, ev in enumerate(events) if ev.tof_idx >= limits[0]]
        else:
            bad = [
                k for k, ev in enumerate(events)
                if any(i >= n for i, n in zip(ev.tof_indices, limits))
            ]
        if bad:
            ev = events[bad[0]]
            value = ev.tof_idx if len(types) == 2 else list(ev.tof_indices)
            raise_for_events(bad, events, name,
                             "have a TOF index out of range",
                             f"with {value}, but there are {limits} TOF bins")


def validate_singles_times(header: petsird.Header, block: EventBlock) -> None:
    """single-event offsets fall inside the block; blocks with singles < 2^32 ps

    Events.yml: SingleEvent.timeOffsetInTimeBlock;
    Protocol.yml: EventTimeBlock.timeInterval
    """
    interval = block.time_interval
    if interval.stop < interval.start:
        return  # validate_time_interval reports this
    duration_ps = (int(interval.stop) - int(interval.start)) * PS_PER_MS
    has_singles = False
    for t, events in enumerate(block.single_events[:num_module_types(header)]):
        has_singles = has_singles or bool(events)
        bad = [
            k for k, ev in enumerate(events)
            if ev.time_offset_in_time_block > duration_ps
        ]
        if bad:
            raise_for_events(
                bad, events, f"singleEvents[{t}]",
                f"have timeOffsetInTimeBlock beyond the block length "
                f"({duration_ps} ps)",
                f"at {events[bad[0]].time_offset_in_time_block} ps")
    if has_singles and duration_ps >= MAX_SINGLES_INTERVAL_PS:
        raise ValueError(
            f"timeInterval is {duration_ps} ps long; blocks with "
            "singles must be shorter than 2^32 ps (about 4.29 ms)")


events_tests_suite = {
    "detection bins": {
        "func": validate_detection_bins,
        "level": "event_block",
    },
    "TOF indices": {
        "func": validate_tof_indices,
        "level": "event_block",
    },
    "singles times": {
        "func": validate_singles_times,
        "level": "event_block",
    },
}
