"""
Command-line interface: ``petsird-validator FILE [--max-blocks N] [--color WHEN]``.

Reads a PETSIRD file and runs every validate function on it:
- the header checks, once;
- the time-block checks, on every time block of the type they check;
- the stream checks, once, on a summary of all the time blocks.
The results are printed grouped by stage and by model file, in colour when
the output is a terminal.
Exit code: 0 = all checks pass, 1 = a check failed, 2 = the file can't be read.
Warnings (soft checks) are printed but do not change the exit code.
"""
#  Copyright (C) 2026 ETSI hackathon contributors
#  Author: Hong Phuc Vo, MAX TOUSS, Kathiresan Chandrasekaran

import argparse
import io
import itertools
import os
import sys
import time
import warnings
from collections import Counter
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass

import petsird

from .detection_efficiencies import detection_efficiencies_tests_suite
from .detector_information import detector_information_tests_suite
from .events import events_tests_suite
from .exam_information import exam_information_tests_suite
from .geometry_information import geometry_information_tests_suite
from .material_information import material_information_tests_suite
from .protocol import StreamSummary, protocol_tests_suite
from .scanner_information import scanner_information_tests_suite
from .singles_histograms import singles_histograms_tests_suite
from .time_frame_information import time_frame_information_tests_suite

# The test suite of every module, in the order the checks are reported. Each
# suite maps a description to {"func": check, "level": level}, where the level
# says what the check takes and what it runs on:
#   "header"       check(header), once
#   "all_block"    check(header, block), on every time block
#   "event_block"  check(header, block), on every EventTimeBlock and
#                  WeightedEventTimeBlock
#   "block"        check(header, block), on the time blocks whose types are
#                  listed in "block_types", e.g. ("ExternalSignalTimeBlock", )
#   "stream"       check(header, summary), once, on the protocol.StreamSummary
#                  of all the time blocks
TEST_SUITES = (
    detector_information_tests_suite,
    geometry_information_tests_suite,
    material_information_tests_suite,
    scanner_information_tests_suite,
    detection_efficiencies_tests_suite,
    singles_histograms_tests_suite,
    exam_information_tests_suite,
    time_frame_information_tests_suite,
    events_tests_suite,
    protocol_tests_suite,
)

LEVELS = ("header", "all_block", "event_block", "block", "stream")
EVENT_BLOCK_TYPES = ("EventTimeBlock", "WeightedEventTimeBlock")
TIME_BLOCK_TYPES = tuple(case.tag for case in vars(petsird.TimeBlock).values()
                         if isinstance(case, type))


def _tests(level: str) -> list[dict]:
    """The test-suite entries with this level, after checking every entry."""
    for suite in TEST_SUITES:
        for description, test in suite.items():
            where = f"test suite entry {description!r}"
            if not callable(test.get("func")):
                raise TypeError(f"{where}: 'func' must be a function")
            if test.get("level") not in LEVELS:
                raise ValueError(f"{where}: 'level' must be one of {LEVELS}")
            unknown = set(test.get("block_types", ())) - set(TIME_BLOCK_TYPES)
            if unknown or (test["level"] == "block"
                           and not test.get("block_types")):
                raise ValueError(
                    f"{where}: a 'block' check needs 'block_types', "
                    f"from {TIME_BLOCK_TYPES}")
    return [
        test for suite in TEST_SUITES for test in suite.values()
        if test["level"] == level
    ]


# Run once, as check(header).
HEADER_CHECKS = tuple(test["func"] for test in _tests("header"))

# Run on every time block, whatever its type, as check(header, block).
ALL_BLOCK_CHECKS = tuple(test["func"] for test in _tests("all_block"))

# Run on every EventTimeBlock and WeightedEventTimeBlock.
EVENT_BLOCK_CHECKS = tuple(test["func"] for test in _tests("event_block"))

# Run on the time blocks of one type, as check(header, block).
BLOCK_CHECKS: dict[str, tuple[Callable,
                              ...]] = dict.fromkeys(EVENT_BLOCK_TYPES,
                                                    EVENT_BLOCK_CHECKS)
for _test in _tests("block"):
    for _tag in _test["block_types"]:
        BLOCK_CHECKS[_tag] = BLOCK_CHECKS.get(_tag, ()) + (_test["func"], )

# Run once after the last time block, as check(header, summary).
STREAM_CHECKS = tuple(test["func"] for test in _tests("stream"))


class ReadError(Exception):
    """The file could not be read (as opposed to a check that failed)."""


@dataclass
class Result:
    """The outcome of one check over everything it ran on."""
    runs: int = 0
    failures: int = 0
    first_failure: str = ""
    warnings: int = 0
    first_warning: str = ""

    def run(self, check: Callable, *args, where: str = "") -> None:
        """Run check(*args); record a ValueError as a failure, and warnings.

        Any other exception is recorded as a failure too, so that one
        broken check does not stop the others.
        """
        self.runs += 1
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            try:
                check(*args)
            except ValueError as e:
                self._fail(f"{where}{e}")
            except Exception as e:  # noqa: BLE001 - reported, see docstring
                self._fail(f"{where}the check crashed with "
                           f"{type(e).__name__}: {e}")
        for warning in caught:
            self.warnings += 1
            if self.warnings == 1:
                self.first_warning = f"{where}{warning.message}"

    def _fail(self, message: str) -> None:
        self.failures += 1
        if self.failures == 1:
            self.first_failure = message


@dataclass
class Outcome:
    """What to report for one check: its result, or why it was skipped."""
    check: Callable
    result: Result | None = None
    skip_reason: str = ""
    unit: str = ""  # what the check ran on, e.g. "blocks"; empty if it ran once


def model_file(check: Callable) -> str:
    """The model file a check belongs to, from its module name.

    For example petsird_validation.detector_information gives
    DetectorInformation.yml.
    """
    module = check.__module__.rsplit(".", 1)[-1]
    return "".join(part.capitalize() for part in module.split("_")) + ".yml"


# ---------------------------------------------------------------- output

_STYLES = {
    "passed": "1;32",  # bold green
    "failed": "1;31",  # bold red
    "warned": "1;33",  # bold yellow
    "skipped": "2",  # dim
    "title": "1",  # bold
    "group": "36",  # cyan
    "dim": "2",
}
_LABELS = {
    "passed": "✓ PASS",
    "failed": "✗ FAIL",
    "warned": "! WARN",
    "skipped": "- SKIP",
}
_DETAIL_INDENT = " " * 12


class Report:
    """Prints outcomes grouped by stage and model file, and keeps the tally."""

    def __init__(self, color: bool):
        self.color = color
        # one of "passed", "warned", "failed" or "skipped" per check
        self.marks: list[str] = []

    def paint(self, text: str, style: str) -> str:
        if not self.color:
            return text
        return f"\033[{_STYLES[style]}m{text}\033[0m"

    def stage(self,
              title: str,
              outcomes: Iterable[Outcome],
              details: str = "") -> None:
        """Print a stage: its title, then its outcomes grouped by model file."""
        print()
        print(
            self.paint(title, "title") +
            (f"  {self.paint(details, 'dim')}" if details else ""))
        groups: dict[str, list[Outcome]] = {}
        for outcome in outcomes:
            groups.setdefault(model_file(outcome.check), []).append(outcome)
        for group, group_outcomes in groups.items():
            print(f"  {self.paint(group, 'group')}")
            for outcome in group_outcomes:
                self._outcome(outcome)

    def _line(self,
              status: str,
              name: str,
              note: str = "",
              detail: str = "") -> None:
        note = f"  {self.paint(f'({note})', 'dim')}" if note else ""
        print(f"    {self.paint(_LABELS[status], status)}  {name}{note}")
        if detail:
            print(f"{_DETAIL_INDENT}{detail}")

    def _outcome(self, outcome: Outcome) -> None:
        name, result, unit = outcome.check.__name__, outcome.result, outcome.unit
        if result is None:
            self.marks.append("skipped")
            self._line("skipped", name, outcome.skip_reason)
            return
        if result.failures:
            note = f"{result.failures:,} of {result.runs:,} {unit}" if unit else ""
            first = f"first in {result.first_failure}" if unit else (
                result.first_failure)
            self._line("failed", name, note, first)
        else:
            self._line("passed", name,
                       f"{result.runs:,} {unit}" if unit else "")
        if result.warnings:
            note = f"{result.warnings:,} warnings" if result.warnings > 1 else ""
            first = f"first in {result.first_warning}" if unit else (
                result.first_warning)
            self._line("warned", name, note, first)
        if result.failures:
            self.marks.append("failed")
        else:
            self.marks.append("warned" if result.warnings else "passed")

    def summary(self) -> int:
        """Print the tally of all checks; return the number that failed."""
        counts = Counter(self.marks)
        passed = counts["passed"] + counts["warned"]
        failed, skipped = counts["failed"], counts["skipped"]
        print()
        bar = "".join(self.paint("■", mark) for mark in self.marks)
        print(
            self.paint("Summary", "title") +
            (f"  {bar}" if self.color else ""))
        parts = [
            self.paint(f"{passed} passed", "passed" if passed else "dim"),
            self.paint(f"{failed} failed", "failed" if failed else "dim"),
            self.paint(f"{skipped} skipped", "dim"),
        ]
        if counts["warned"]:
            parts.append(
                self.paint(f"{counts['warned']} with warnings", "warned"))
        print("  " + " · ".join(parts))
        print(f"  {failed} of {passed + failed} checks failed")
        return failed


def use_color(choice: str, stream=sys.stdout) -> bool:
    """Whether to colour stream, for --color auto, always or never."""
    if choice != "auto":
        return choice == "always"
    return (stream.isatty() and "NO_COLOR" not in os.environ
            and os.environ.get("TERM") != "dumb")


def _duration(seconds: float) -> str:
    seconds = round(seconds)
    return f"{seconds // 60}m {seconds % 60:02d}s" if seconds >= 60 else f"{seconds}s"


class Progress:
    """A progress bar on stderr while the time blocks are read.

    The fraction done is blocks / max_blocks with --max-blocks, otherwise how
    far through the file the reader is.
    """

    WIDTH = 30  # characters
    REDRAW_S = 0.1  # seconds between redraws

    def __init__(self, fraction_read: Callable[[], float],
                 max_blocks: int | None, color: bool):
        self._fraction_read = fraction_read
        self._max_blocks = max_blocks
        self._color = color
        self._start = self._last_draw = time.monotonic()
        self._shown = False

    def update(self, blocks: int) -> None:
        """Redraw the bar, at most every REDRAW_S seconds."""
        now = time.monotonic()
        if now - self._last_draw < self.REDRAW_S:
            return
        self._last_draw = now
        if self._max_blocks:
            done = min(1.0, blocks / self._max_blocks)
        else:
            done = self._fraction_read()
        filled = round(done * self.WIDTH)
        bar, rest = "█" * filled, "░" * (self.WIDTH - filled)
        if self._color:
            bar, rest = f"\033[32m{bar}\033[0m", f"\033[2m{rest}\033[0m"
        elapsed = now - self._start
        left = (f" · ~{_duration(elapsed * (1 - done) / done)} left"
                if done > 0.01 else "")
        sys.stderr.write(f"\r\033[K  reading time blocks {bar}{rest} "
                         f"{done:4.0%} · {blocks:,} blocks · "
                         f"{_duration(elapsed)}{left}")
        sys.stderr.flush()
        self._shown = True

    def close(self) -> None:
        """Remove the bar."""
        if self._shown:
            sys.stderr.write("\r\033[K")
            sys.stderr.flush()


# ---------------------------------------------------------------- reading


class PetsirdFile:
    """An open binary or NDJSON PETSIRD file: its reader, and how far
    through the file reading has got.

    Use it as a context manager; it closes the file at the end.
    """

    def __init__(self, path: str):
        self._file = open(path, "rb")
        try:
            magic = self._file.read(8)
            self._file.seek(0)
            if magic.startswith(b"yardl"):
                self._stream = self._file
                self.reader = petsird.BinaryPETSIRDReader(
                    self._stream, skip_completed_check=True)
            elif magic.lstrip().startswith(b"{"):
                self._stream = io.TextIOWrapper(self._file, encoding="utf-8")
                self.reader = petsird.NDJsonPETSIRDReader(
                    self._stream, skip_completed_check=True)
            else:
                raise ValueError("not a PETSIRD binary or NDJSON file")
        except BaseException:
            self._file.close()
            raise
        self._size = os.fstat(self._file.fileno()).st_size

    def fraction_read(self) -> float:
        """How far through the file reading has got, from 0 to 1.

        This runs slightly ahead of the time blocks checked so far, because
        the reader reads ahead into a buffer.
        """
        if not self._size:
            return 1.0
        position = os.lseek(self._file.fileno(), 0, os.SEEK_CUR)
        return min(1.0, position / self._size)

    def __enter__(self) -> "PetsirdFile":
        return self

    def __exit__(self, *exc_info) -> None:
        self.reader.close()
        self._stream.close()  # also closes self._file


def read_time_blocks(reader: petsird.PETSIRDReaderBase,
                     max_blocks: int | None) -> Iterator[petsird.TimeBlock]:
    """Yield the time blocks of the stream, at most max_blocks of them.

    An error while reading raises ReadError, so that it is not reported as
    a failed check.
    """
    blocks = itertools.islice(reader.read_time_blocks(), max_blocks)
    for k in itertools.count():
        try:
            time_block = next(blocks)
        except StopIteration:
            return
        except Exception as e:  # noqa: BLE001 - any read error means exit code 2
            raise ReadError(f"time block {k}: {e}") from e
        yield time_block


# ---------------------------------------------------------------- checks


def run_header_checks(header: petsird.Header) -> list[Outcome]:
    """Run HEADER_CHECKS."""
    outcomes = []
    for check in HEADER_CHECKS:
        result = Result()
        result.run(check, header)
        outcomes.append(Outcome(check, result))
    return outcomes


def run_time_block_checks(
        header: petsird.Header,
        time_blocks: Iterable[petsird.TimeBlock],
        progress: Progress | None = None
) -> tuple[list[Outcome], StreamSummary]:
    """Run ALL_BLOCK_CHECKS and BLOCK_CHECKS on every time block.

    A check is skipped if there is no block of its type. The progress bar,
    if given, is updated after every block and removed at the end.
    """
    results = {check: Result() for check in ALL_BLOCK_CHECKS}
    block_types = {check: ["time block"] for check in ALL_BLOCK_CHECKS}
    for tag, checks in BLOCK_CHECKS.items():
        for check in checks:
            results.setdefault(check, Result())
            block_types.setdefault(check, []).append(tag)

    summary = StreamSummary()
    try:
        for k, time_block in enumerate(time_blocks):
            summary.add(time_block)
            block = time_block.value
            for check in (ALL_BLOCK_CHECKS +
                          BLOCK_CHECKS.get(time_block.tag, ())):
                results[check].run(check,
                                   header,
                                   block,
                                   where=f"time block {k}: ")
            if progress:
                progress.update(k + 1)
    finally:
        if progress:
            progress.close()

    return [
        Outcome(check, result, unit="blocks") if result.runs else Outcome(
            check,
            skip_reason=f"no {' or '.join(block_types[check])} in the stream")
        for check, result in results.items()
    ], summary


def run_stream_checks(header: petsird.Header, summary: StreamSummary,
                      complete: bool) -> list[Outcome]:
    """Run STREAM_CHECKS on the summary of the time blocks.

    They are skipped if the stream was not read to the end, or has no event
    blocks.
    """
    outcomes = []
    for check in STREAM_CHECKS:
        if not complete:
            outcomes.append(
                Outcome(check,
                        skip_reason="stopped at --max-blocks, so the stream "
                        "may not have been read to the end"))
        elif not summary.event_intervals:
            outcomes.append(
                Outcome(check, skip_reason="no event blocks in the stream"))
        else:
            result = Result()
            result.run(check, header, summary)
            outcomes.append(Outcome(check, result))
    return outcomes


def describe_stream(summary: StreamSummary) -> str:
    """One line saying which time blocks and events were read."""
    blocks = ", ".join(f"{n:,} {tag}"
                       for tag, n in summary.block_counts.items())
    text = f"{summary.blocks_read:,} read" + (f": {blocks}" if blocks else "")
    if summary.event_counts:
        text += " · " + ", ".join(f"{n:,} {kind}"
                                  for kind, n in summary.event_counts.items())
    return text


# ---------------------------------------------------------------- main


def _could_not_read(path: str, error: Exception) -> int:
    print(f"petsird-validator: error: could not read {path}: {error}",
          file=sys.stderr)
    return 2


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="petsird-validator",
        description="Check a PETSIRD file against the constraints in the "
        "PETSIRD model.")
    parser.add_argument("file", help="PETSIRD binary or NDJSON file")
    parser.add_argument("--max-blocks",
                        type=int,
                        metavar="N",
                        help="check only the first N time blocks "
                        "(default: all)")
    parser.add_argument("--color",
                        choices=("auto", "always", "never"),
                        default="auto",
                        help="colour the output (default: auto, i.e. when "
                        "printing to a terminal and NO_COLOR is not set)")
    args = parser.parse_args(argv)
    if args.max_blocks is not None and args.max_blocks < 0:
        parser.error("--max-blocks must be 0 or more")

    try:
        petsird_file = PetsirdFile(args.file)
    except Exception as e:  # noqa: BLE001 - any read error means exit code 2
        return _could_not_read(args.file, e)

    report = Report(use_color(args.color))
    with petsird_file:
        reader = petsird_file.reader
        try:
            header = reader.read_header()
        except Exception as e:  # noqa: BLE001 - any read error means exit code 2
            return _could_not_read(args.file, e)
        print(f"{report.paint('petsird-validator', 'title')}  {args.file}")
        report.stage("Header", run_header_checks(header))
        sys.stdout.flush()  # show the header results while the blocks are read
        progress = None
        if sys.stderr.isatty():
            progress = Progress(petsird_file.fraction_read, args.max_blocks,
                                use_color(args.color, sys.stderr))
        try:
            block_outcomes, summary = run_time_block_checks(
                header, read_time_blocks(reader, args.max_blocks), progress)
        except ReadError as e:
            return _could_not_read(args.file, e)

    report.stage("Time blocks", block_outcomes, describe_stream(summary))
    complete = (args.max_blocks is None
                or summary.blocks_read < args.max_blocks)
    report.stage("Whole stream", run_stream_checks(header, summary, complete))
    return 1 if report.summary() else 0


if __name__ == "__main__":
    sys.exit(main())
