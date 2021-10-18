# This file is part of Hypothesis, which may be found at
# https://github.com/HypothesisWorks/hypothesis/
#
# Most of this work is copyright (C) 2013-2021 David R. MacIver
# (david@drmaciver.com), but it contains contributions by others. See
# CONTRIBUTING.rst for a full list of people who may hold copyright, and
# consult the git log if you need to determine who owns an individual
# contribution.
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file, You can
# obtain one at https://mozilla.org/MPL/2.0/.
#
# END HEADER

import os
import sys

import pytest

from hypothesis import given, reporting
from hypothesis._settings import Verbosity, settings
from hypothesis.reporting import debug_report, report, verbose_report
from hypothesis.strategies import integers

from tests.common.utils import capture_out


def test_can_suppress_output():
    @given(integers())
    def test_int(x):
        raise AssertionError

    with capture_out() as o:
        with reporting.with_reporter(reporting.silent):
            with pytest.raises(AssertionError):
                test_int()
    assert "Falsifying example" not in o.getvalue()


def test_can_print_bytes():
    with capture_out() as o:
        with reporting.with_reporter(reporting.default):
            report(b"hi")
    assert o.getvalue() == "hi\n"


def test_prints_output_by_default():
    @given(integers())
    def test_int(x):
        raise AssertionError

    with capture_out() as o:
        with reporting.with_reporter(reporting.default):
            with pytest.raises(AssertionError):
                test_int()
    assert "Falsifying example" in o.getvalue()


def test_does_not_print_debug_in_verbose():
    @given(integers())
    @settings(verbosity=Verbosity.verbose)
    def f(x):
        debug_report("Hi")

    with capture_out() as o:
        f()
    assert "Hi" not in o.getvalue()


def test_does_print_debug_in_debug():
    @given(integers())
    @settings(verbosity=Verbosity.debug)
    def f(x):
        debug_report("Hi")

    with capture_out() as o:
        f()
    assert "Hi" in o.getvalue()


def test_does_print_verbose_in_debug():
    @given(integers())
    @settings(verbosity=Verbosity.debug)
    def f(x):
        verbose_report("Hi")

    with capture_out() as o:
        f()
    assert "Hi" in o.getvalue()


def test_can_report_when_system_locale_is_ascii(monkeypatch):
    read, write = os.pipe()
    with open(read, encoding="ascii") as read:
        with open(write, "w", encoding="ascii") as write:
            monkeypatch.setattr(sys, "stdout", write)
            reporting.default("☃")


def test_can_report_functions():
    with capture_out() as out:
        report(lambda: "foo")

    assert out.getvalue().strip() == "foo"
