"""
Validation functions for model/ExamInformation.yml: ExamInformation.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Hong Phuc Vo

from collections import Counter

import petsird

from ._common import warn


def validate_exam(header: petsird.Header) -> None:
    """externalSignals ids are unique; warns if modality is not 'PT'

    ExamInformation.yml: ExamInformation.externalSignals, modality
    """
    exam = header.exam
    if exam is None:
        return
    for signal_id, n in Counter(s.id for s in exam.external_signals).items():
        if n > 1:
            raise ValueError(
                f"exam.externalSignals: id {signal_id} is used by "
                f"{n} signals")
    if exam.modality != "PT":
        warn(f"exam.modality is {exam.modality!r}; expected 'PT'")


exam_information_tests_suite = {
    "exam information": {
        "func": validate_exam,
        "level": "header",
    },
}
