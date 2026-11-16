"""
Tests for the matrix-shape helpers in basic_types.py.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Claude (Anthropic AI assistant), not yet reviewed by a person

import pytest
from petsird_validation.basic_types import (
    check_lower_triangular, check_lower_triangular_or_rectangular)


def test_lower_triangular_ok():
    check_lower_triangular([[1], [2, 3], [4, 5, 6]], 3, "m")


@pytest.mark.parametrize("matrix, message", [
    ([[1], [2, 3]], r"m has 2 rows, expected 3"),
    ([[1], [2], [4, 5, 6]], r"m\[1\] has 1 entries, expected 2$"),
    ([[1, 0, 0], [2, 3, 0], [4, 5, 6]], r"m\[0\] .*\(looks rectangular"),
])
def test_lower_triangular_wrong_shape(matrix, message):
    with pytest.raises(ValueError, match=message):
        check_lower_triangular(matrix, 3, "m")


@pytest.mark.parametrize("matrix, is_lower_triangular", [
    ([[1], [2, 3]], True),
    ([[1, 2, 3], [4, 5, 6]], False),
])
def test_lower_triangular_or_rectangular_ok(matrix, is_lower_triangular):
    check_lower_triangular_or_rectangular(matrix, 2, 3, is_lower_triangular,
                                          "m")


@pytest.mark.parametrize("matrix, is_lower_triangular, message", [
    ([[1]], True, r"m has 1 rows, expected 2"),
    ([[1], [2, 3, 4]], True, r"m\[1\] has 3 entries, expected 2"),
    ([[1, 2, 3], [4, 5]], False, r"m\[1\] has 2 entries, expected 3"),
])
def test_lower_triangular_or_rectangular_wrong_shape(matrix,
                                                     is_lower_triangular,
                                                     message):
    with pytest.raises(ValueError, match=message):
        check_lower_triangular_or_rectangular(matrix, 2, 3,
                                              is_lower_triangular, "m")
