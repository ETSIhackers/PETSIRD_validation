"""
Validation helpers for model/BasicTypes.yml (the matrix "template" types).
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Hong Phuc Vo

from collections.abc import Sequence


def check_lower_triangular(matrix: Sequence[Sequence], num_rows: int,
                           name: str) -> None:
    """Check a LowerTriangularMatrix: num_rows rows, row i has i+1 entries.

    BasicTypes.yml: LowerTriangularMatrix ("for matrix[i][j], j<=i")
    """
    if len(matrix) != num_rows:
        raise ValueError(f"{name} has {len(matrix)} rows, expected {num_rows} "
                         "(one per module type)")
    for i, row in enumerate(matrix):
        if len(row) != i + 1:
            hint = (" (looks rectangular; only the lower triangle with "
                    "type_of_module2 <= type_of_module1 is stored)"
                    if len(row) == num_rows and num_rows > 1 else "")
            raise ValueError(
                f"{name}[{i}] has {len(row)} entries, expected {i + 1}{hint}")


def check_lower_triangular_or_rectangular(matrix: Sequence[Sequence],
                                          num_rows: int, num_columns: int,
                                          is_lower_triangular: bool,
                                          name: str) -> None:
    """Check a LowerTriangularOrRectangularMatrix of the given size.

    BasicTypes.yml: LowerTriangularOrRectangularMatrix
    """
    if len(matrix) != num_rows:
        raise ValueError(f"{name} has {len(matrix)} rows, expected {num_rows}")
    for i, row in enumerate(matrix):
        expected = i + 1 if is_lower_triangular else num_columns
        if len(row) != expected:
            raise ValueError(f"{name}[{i}] has {len(row)} entries, expected "
                             f"{expected}")
