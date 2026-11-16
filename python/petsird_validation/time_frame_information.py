"""
Validation functions for model/TimeFrameInformation.yml: TimeInterval.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Hong Phuc Vo

import petsird


def validate_time_interval(header: petsird.Header, block) -> None:
    """timeInterval.start <= timeInterval.stop (all time blocks)

    TimeFrameInformation.yml: TimeInterval
    """
    interval = block.time_interval
    if interval.start > interval.stop:
        raise ValueError(f"timeInterval start {interval.start} ms is after "
                         f"stop {interval.stop} ms")


time_frame_information_tests_suite = {
    "time interval": {
        "func": validate_time_interval,
        "level": "all_block",
    },
}
