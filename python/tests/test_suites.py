"""
Check that every module registers its checks in its `<module>_tests_suite`,
in the format that cli.py expects, and that cli.py runs every suite.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Claude (Anthropic AI assistant), not yet reviewed by a person

import importlib
import inspect
import pkgutil

import petsird_validation
import pytest
from petsird_validation import cli

MODULES = [
    importlib.import_module(f"petsird_validation.{info.name}")
    for info in pkgutil.iter_modules(petsird_validation.__path__)
]


def short_name(module) -> str:
    return module.__name__.rsplit(".", 1)[-1]


def suite_of(module):
    return getattr(module, f"{short_name(module)}_tests_suite", None)


def checks_in(module) -> set:
    """the validate_* functions of a module that take a header"""
    return {
        func
        for name, func in inspect.getmembers(module, inspect.isfunction)
        if name.startswith("validate_") and func.__module__ == module.__name__
        and next(iter(inspect.signature(func).parameters), None) == "header"
    }


@pytest.mark.parametrize("module", MODULES, ids=short_name)
def test_every_check_is_registered(module):
    """every validate_*(header, ...) function is in its module's suite"""
    registered = {test["func"] for test in (suite_of(module) or {}).values()}
    missing = {func.__name__ for func in checks_in(module) - registered}
    assert missing == set(), (
        f"add these to {short_name(module)}_tests_suite: {sorted(missing)}")


@pytest.mark.parametrize("module",
                         [m for m in MODULES if suite_of(m) is not None],
                         ids=short_name)
def test_suite_format(module):
    """entries are {"func", "level"[, "block_types"]} with matching arguments"""
    for description, test in suite_of(module).items():
        assert set(test) <= {"func", "level", "block_types"}, description
        func, level = test["func"], test["level"]
        assert func.__module__ == module.__name__, description
        assert level in cli.LEVELS, description
        expected_arguments = 1 if level == "header" else 2
        assert len(inspect.signature(func).parameters) == expected_arguments, (
            f"{description}: a {level!r} check takes {expected_arguments} "
            "arguments")
        if level == "block":
            assert set(test["block_types"]) <= set(cli.TIME_BLOCK_TYPES)
        else:
            assert "block_types" not in test, description


def test_cli_runs_every_suite():
    suites = [suite_of(m) for m in MODULES if suite_of(m) is not None]
    assert all(any(suite is s for s in cli.TEST_SUITES) for suite in suites)
    assert len(cli.TEST_SUITES) == len(suites)
