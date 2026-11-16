"""
Write valid and broken PETSIRD files and check what `petsird-validator` says
about them.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Claude (Anthropic AI assistant), not yet reviewed by a person

import broken_files
import pytest
from petsird_validation import cli

CHECK_NAMES = {check.__name__ for check in cli.HEADER_CHECKS}


def run_validator(path, capsys):
    """run petsird-validator on path; return exit code, failed checks, output"""
    exit_code = cli.main([str(path)])
    out = capsys.readouterr().out
    failed = {
        line.split()[1].rstrip(":")
        for line in out.splitlines() if line.startswith("FAIL ")
    }
    return exit_code, failed, out


@pytest.mark.parametrize("ndjson", [False, True], ids=["binary", "ndjson"])
def test_valid_file_passes(ndjson, tmp_path, capsys):
    path = broken_files.write(broken_files.make_header(),
                              tmp_path / "valid.petsird",
                              ndjson=ndjson)
    exit_code, failed, out = run_validator(path, capsys)
    assert failed == set(), out
    assert exit_code == 0
    assert f"0 of {len(CHECK_NAMES)} checks failed" in out


@pytest.mark.parametrize("name", sorted(broken_files.BROKEN))
def test_broken_file(name, tmp_path, capsys):
    case = broken_files.BROKEN[name]
    path = broken_files.write_broken(name, tmp_path)
    exit_code, failed, out = run_validator(path, capsys)
    assert failed == set(case.fails), out
    assert exit_code == 1
    assert case.match in out


def test_every_check_has_a_broken_file():
    """each check in HEADER_CHECKS fails for at least one broken file"""
    tested = {
        name
        for case in broken_files.BROKEN.values()
        for name in case.fails
    }
    assert CHECK_NAMES - tested == set()


def test_not_a_petsird_file(tmp_path, capsys):
    path = tmp_path / "notes.txt"
    path.write_text("not a PETSIRD file")
    assert cli.main([str(path)]) == 2
    assert "not a PETSIRD binary or NDJSON file" in capsys.readouterr().err


def test_missing_file(tmp_path, capsys):
    assert cli.main([str(tmp_path / "missing.petsird")]) == 2
    assert "could not read" in capsys.readouterr().err


def test_truncated_file(tmp_path, capsys):
    path = broken_files.write(broken_files.make_header(),
                              tmp_path / "truncated.petsird")
    path.write_bytes(path.read_bytes()[:-200])
    assert cli.main([str(path)]) == 2
    assert "could not read" in capsys.readouterr().err
