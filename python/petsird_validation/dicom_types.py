"""
Validation functions for model/DICOMTypes.yml.

Checks DICOM patient information, orientation, radiopharmaceutical
information, UIDs, and basic code sequences.
"""

# Copyright (C) 2026 ETSI hackathon contributors
# Authors: Kathiresan Chandrasekaran

import math
import re
from collections.abc import Mapping

import petsird

_UID_PATTERN = re.compile(r"(?:0|[1-9][0-9]*)(?:\.(?:0|[1-9][0-9]*))*\Z")
_ALLOWED_SEX = {"M", "F", "O", ""}


def _field(obj, name, default=None):
    """Read a field from a Yardl record or dictionary."""
    if isinstance(obj, Mapping):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _records(root, record_name):
    """
    Find nested DICOM records in the PETSIRD header.

    Traverses Yardl records, lists, tuples, and dictionaries while
    avoiding repeated objects.
    """
    seen = set()
    stack = [("header", root)]

    while stack:
        path, obj = stack.pop()

        if obj is None or isinstance(obj, (str, bytes, int, float, bool)):
            continue

        if id(obj) in seen:
            continue
        seen.add(id(obj))

        if isinstance(obj, Mapping):
            fields = obj.items()
        elif isinstance(obj, (list, tuple)):
            for i, value in enumerate(obj):
                stack.append((f"{path}[{i}]", value))
            continue
        elif hasattr(obj, "__dict__"):
            fields = vars(obj).items()
        else:
            continue

        for name, value in fields:
            child_path = f"{path}.{name}"

            if value is None:
                continue

            if name == record_name:
                yield child_path, value

            stack.append((child_path, value))


def _finite_nonnegative(value, name):
    """Check a numeric value is finite and non-negative."""
    try:
        number = float(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise ValueError(f"{name} must be numeric") from exc

    if not math.isfinite(number) or number < 0:
        raise ValueError(f"{name} must be finite and non-negative")


def _validate_uid(value, name):
    """Check the syntax and length of a DICOM UID."""
    if not isinstance(value, str):
        raise ValueError(f"{name} must be a string")

    if not value:
        return

    if len(value) > 64 or not _UID_PATTERN.fullmatch(value):
        raise ValueError(f"{name}: invalid DICOM UID {value!r}")


def _validate_code_sequence(code, name):
    """Validate the fields of a DICOM basic code sequence."""
    if code is None:
        return

    code_value = _field(code, "code_value", "")
    code_urn = _field(code, "code_value_urn", "")
    scheme = _field(code, "coding_scheme_designator", "")

    if code_value and code_urn:
        raise ValueError(f"{name}: codeValue and codeValueURN "
                         "must not both be populated")

    if code_value and not scheme:
        raise ValueError(f"{name}: codingSchemeDesignator is required "
                         "when codeValue is populated")


def validate_patient_information(header: petsird.Header):
    """Validate DICOM patient information."""
    for path, patient in _records(header, "dicom_patient_information"):
        sex = _field(patient, "patients_sex")

        if sex is not None and sex not in _ALLOWED_SEX:
            raise ValueError(f"{path}.patientsSex: invalid value {sex!r}; "
                             "expected M, F, O, or empty string")

        for field in (
                "patients_size",
                "patients_weight",
                "patients_body_mass_index",
        ):
            value = _field(patient, field)

            if value is not None:
                _finite_nonnegative(value, f"{path}.{field}")


def validate_patient_orientation(header: petsird.Header):
    """Validate DICOM patient orientation code sequences."""
    for path, orientation in _records(header,
                                      "dicom_patient_orientation_information"):
        for field in (
                "patient_orientation_code_sequence",
                "patient_orientation_modifier_code_sequence",
                "patient_gantry_relationship_code_sequence",
        ):
            _validate_code_sequence(
                _field(orientation, field),
                f"{path}.{field}",
            )


def validate_radiopharmaceutical_information(header: petsird.Header, ):
    """Validate DICOM radiopharmaceutical information."""
    for path, radiopharm in _records(header,
                                     "dicom_radiopharmaceutical_information"):
        for field in (
                "radiopharmaceutical_volume",
                "radionuclide_total_dose",
                "radiopharmaceutical_specific_activity",
        ):
            value = _field(radiopharm, field)

            if value is not None:
                _finite_nonnegative(value, f"{path}.{field}")

        start = _field(
            radiopharm,
            "radiopharmaceutical_start_date_time",
        )
        stop = _field(
            radiopharm,
            "radiopharmaceutical_stop_date_time",
        )

        if start is not None and stop is not None:
            try:
                invalid = stop < start
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{path}: incompatible administration "
                                 "start and stop times") from exc

            if invalid:
                raise ValueError(f"{path}: radiopharmaceuticalStopDateTime "
                                 "precedes radiopharmaceuticalStartDateTime")

        _validate_uid(
            _field(
                radiopharm,
                "radiopharmaceutical_administration_event_uid",
                "",
            ),
            f"{path}.radiopharmaceuticalAdministrationEventUID",
        )


def validate_dicom_uid(header: petsird.Header):
    """Validate DICOM UIDs found in nested header records."""
    seen = set()
    stack = [("header", header)]

    while stack:
        path, obj = stack.pop()

        if obj is None or isinstance(obj, (str, bytes, int, float, bool)):
            continue

        if id(obj) in seen:
            continue
        seen.add(id(obj))

        if isinstance(obj, Mapping):
            fields = obj.items()
        elif isinstance(obj, (list, tuple)):
            for i, value in enumerate(obj):
                stack.append((f"{path}[{i}]", value))
            continue
        elif hasattr(obj, "__dict__"):
            fields = vars(obj).items()
        else:
            continue

        for name, value in fields:
            child_path = f"{path}.{name}"

            if isinstance(name,
                          str) and name.lower().endswith("uid") and isinstance(
                              value, str):
                _validate_uid(value, child_path)

            stack.append((child_path, value))


def validate_dicom_code_sequences(header: petsird.Header):
    """Validate nested DICOM basic code sequences."""
    sequence_fields = (
        "patient_orientation_code_sequence",
        "patient_orientation_modifier_code_sequence",
        "patient_gantry_relationship_code_sequence",
        "radiopharmaceutical_code_sequence",
        "radionuclide_code_sequence",
    )

    for field in sequence_fields:
        for path, code in _records(header, field):
            _validate_code_sequence(code, path)


dicom_types_tests_suite = {
    "patient information": {
        "func": validate_patient_information,
        "level": "header",
    },
    "patient orientation": {
        "func": validate_patient_orientation,
        "level": "header",
    },
    "radiopharmaceutical information": {
        "func": validate_radiopharmaceutical_information,
        "level": "header",
    },
    "DICOM UID": {
        "func": validate_dicom_uid,
        "level": "header",
    },
    "DICOM code sequences": {
        "func": validate_dicom_code_sequences,
        "level": "header",
    },
}
