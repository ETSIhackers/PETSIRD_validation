"""
Write valid and broken PETSIRD files and check what `petsird-validator` says
about them.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Claude (Anthropic AI assistant), not yet reviewed by a person

import re

import broken_files
import pytest
from petsird_validation import cli

# Every check the command runs.
CHECKS = (cli.HEADER_CHECKS + cli.ALL_BLOCK_CHECKS +
          tuple(check for checks in cli.BLOCK_CHECKS.values()
                for check in checks) + cli.STREAM_CHECKS)
CHECK_NAMES = {check.__name__ for check in CHECKS}


def run_validator(path, capsys, *options):
    """run petsird-validator on path

    Returns the exit code, the names of the failed, skipped and warned
    checks, and the output without colour codes.
    """
    exit_code = cli.main([str(path), *options])
    out = re.sub(r"\033\[[0-9;]*m", "", capsys.readouterr().out)

    def names(status):
        return set(re.findall(rf"{status} +(\w+)", out))

    return exit_code, names("FAIL"), names("SKIP"), names("WARN"), out


@pytest.mark.parametrize("ndjson", [False, True], ids=["binary", "ndjson"])
def test_valid_file_passes(ndjson, tmp_path, capsys):
    path = broken_files.write(broken_files.make_valid(),
                              tmp_path / "valid.petsird",
                              ndjson=ndjson)
    exit_code, failed, skipped, warned, out = run_validator(path, capsys)
    assert failed == set(), out
    assert warned == set(), out
    # the valid file has a block of every type except weighted event blocks
    assert skipped == {"validate_weights"}, out
    assert exit_code == 0
    assert f"0 of {len(CHECK_NAMES) - 1} checks failed" in out


def test_valid_weighted_file_passes(tmp_path, capsys):
    data = broken_files.make_weighted(broken_files.make_valid())
    path = broken_files.write(data, tmp_path / "valid_weighted.petsird")
    exit_code, failed, skipped, _, out = run_validator(path, capsys)
    assert failed == set(), out
    assert skipped == set(), out
    assert exit_code == 0


@pytest.mark.parametrize("name", sorted(broken_files.BROKEN))
def test_broken_file(name, tmp_path, capsys):
    case = broken_files.BROKEN[name]
    not_run = set(case.fails) - CHECK_NAMES
    if not_run:
        pytest.skip(f"petsird-validator does not run {sorted(not_run)} yet")
    path = broken_files.write_broken(name, tmp_path)
    exit_code, failed, _, _, out = run_validator(path, capsys)
    assert failed == set(case.fails), out
    assert exit_code == 1
    assert case.match in out


def test_every_check_has_a_broken_file():
    """each check the command runs fails for at least one broken file"""
    tested = {
        name
        for case in broken_files.BROKEN.values()
        for name in case.fails
    }
    assert CHECK_NAMES - tested == set()


def test_warning_does_not_fail(tmp_path, capsys):
    data = broken_files.make_valid()
    data.header.exam.modality = "CT"
    path = broken_files.write(data, tmp_path / "ct.petsird")
    exit_code, failed, _, warned, out = run_validator(path, capsys)
    assert warned == {"validate_exam"}, out
    assert "exam.modality is 'CT'; expected 'PT'" in out
    assert failed == set(), out
    assert exit_code == 0


def test_max_blocks_skips_stream_checks(tmp_path, capsys):
    path = broken_files.write_broken("no_dead_time_blocks", tmp_path)
    exit_code, failed, skipped, _, out = run_validator(path, capsys,
                                                       "--max-blocks", "4")
    assert "read 4 time blocks" in out or "4 read" in out
    assert {
        "validate_dead_time_coverage", "validate_singles_histogram_coverage"
    } <= skipped, out
    assert failed == set(), out
    assert exit_code == 0


@pytest.mark.parametrize("color, has_codes",
                         [("always", True), ("never", False), ("auto", False)])
def test_color(color, has_codes, tmp_path, capsys):
    """colour codes only when asked, or in a terminal (capsys is not one)"""
    path = broken_files.write_broken("no_bulk_materials", tmp_path)
    cli.main([str(path), "--color", color])
    assert ("\033[" in capsys.readouterr().out) == has_codes


def test_not_a_petsird_file(tmp_path, capsys):
    path = tmp_path / "notes.txt"
    path.write_text("not a PETSIRD file")
    assert cli.main([str(path)]) == 2
    assert "not a PETSIRD binary or NDJSON file" in capsys.readouterr().err


def test_missing_file(tmp_path, capsys):
    assert cli.main([str(tmp_path / "missing.petsird")]) == 2
    assert "could not read" in capsys.readouterr().err


@pytest.mark.parametrize("keep_bytes", [200, -60],
                         ids=["in_header", "in_time_blocks"])
def test_truncated_file(keep_bytes, tmp_path, capsys):
    path = broken_files.write(broken_files.make_valid(),
                              tmp_path / "truncated.petsird")
    path.write_bytes(path.read_bytes()[:keep_bytes])
    assert cli.main([str(path)]) == 2
    assert "could not read" in capsys.readouterr().err
