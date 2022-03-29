# This file is part of Hypothesis, which may be found at
# https://github.com/HypothesisWorks/hypothesis/
#
# Copyright the Hypothesis Authors.
# Individual contributors are listed in AUTHORS.rst and the git log.
#
# This Source Code Form is subject to the terms of the Mozilla Public License,
# v. 2.0. If a copy of the MPL was not distributed with this file, You can
# obtain one at https://mozilla.org/MPL/2.0/.

"""
'Golden master' tests for the ghostwriter.

To update the recorded outputs, run `pytest --hypothesis-update-outputs ...`.
"""

import ast
import base64
import builtins
import operator
import pathlib
import re
import sys
from typing import Sequence

import numpy
import pytest

import hypothesis
from hypothesis.extra import ghostwriter
from hypothesis.utils.conventions import not_set


@pytest.fixture
def update_recorded_outputs(request):
    return request.config.getoption("--hypothesis-update-outputs")


def get_recorded(name, actual=""):
    file_ = pathlib.Path(__file__).parent / "recorded" / f"{name}.txt"
    if actual:
        file_.write_text(actual)
    return file_.read_text()


def timsort(seq: Sequence[int]) -> Sequence[int]:
    return sorted(seq)


def with_docstring(a, b, c, d=int, e=lambda x: f"xx{x}xx") -> None:
    """Demonstrates parsing params from the docstring

    :param a: sphinx docstring style
    :type a: sequence of integers

    b (list, tuple, or None): Google docstring style

    c : {"foo", "bar", or None}
        Numpy docstring style
    """


class A_Class:
    @classmethod
    def a_classmethod(cls, arg: int):
        pass


def add(a: float, b: float) -> float:
    return a + b


def divide(a: int, b: int) -> float:
    """This is a RST-style docstring for `divide`.

    :raises ZeroDivisionError: if b == 0
    """
    return a / b


# Note: for some of the `expected` outputs, we replace away some small
#       parts which vary between minor versions of Python.
@pytest.mark.parametrize(
    "data",
    [
        ("fuzz_sorted", ghostwriter.fuzz(sorted)),
        ("fuzz_with_docstring", ghostwriter.fuzz(with_docstring)),
        ("fuzz_classmethod", ghostwriter.fuzz(A_Class.a_classmethod)),
        ("fuzz_ufunc", ghostwriter.fuzz(numpy.add)),
        ("magic_gufunc", ghostwriter.magic(numpy.matmul)),
        ("magic_base64_roundtrip", ghostwriter.magic(base64.b64encode)),
        ("re_compile", ghostwriter.fuzz(re.compile)),
        (
            "re_compile_except",
            ghostwriter.fuzz(re.compile, except_=re.error)
            # re.error fixed it's __module__ in Python 3.7
            .replace("import sre_constants\n", "").replace("sre_constants.", "re."),
        ),
        ("re_compile_unittest", ghostwriter.fuzz(re.compile, style="unittest")),
        pytest.param(
            ("base64_magic", ghostwriter.magic(base64)),
            marks=pytest.mark.skipif("sys.version_info[:2] >= (3, 10)"),
        ),
        ("sorted_idempotent", ghostwriter.idempotent(sorted)),
        ("timsort_idempotent", ghostwriter.idempotent(timsort)),
        (
            "timsort_idempotent_asserts",
            ghostwriter.idempotent(timsort, except_=AssertionError),
        ),
        ("eval_equivalent", ghostwriter.equivalent(eval, ast.literal_eval)),
        ("sorted_self_equivalent", ghostwriter.equivalent(sorted, sorted, sorted)),
        ("addition_op_magic", ghostwriter.magic(add)),
        ("addition_op_multimagic", ghostwriter.magic(add, operator.add, numpy.add)),
        ("division_fuzz_error_handler", ghostwriter.fuzz(divide)),
        (
            "division_binop_error_handler",
            ghostwriter.binary_operation(divide, identity=1),
        ),
        (
            "division_roundtrip_error_handler",
            ghostwriter.roundtrip(divide, operator.mul),
        ),
        (
            "division_roundtrip_arithmeticerror_handler",
            ghostwriter.roundtrip(divide, operator.mul, except_=ArithmeticError),
        ),
        (
            "division_roundtrip_typeerror_handler",
            ghostwriter.roundtrip(divide, operator.mul, except_=TypeError),
        ),
        (
            "division_operator",
            ghostwriter.binary_operation(
                operator.truediv, associative=False, commutative=False
            ),
        ),
        (
            "multiplication_operator",
            ghostwriter.binary_operation(
                operator.mul, identity=1, distributes_over=operator.add
            ),
        ),
        (
            "multiplication_operator_unittest",
            ghostwriter.binary_operation(
                operator.mul,
                identity=1,
                distributes_over=operator.add,
                style="unittest",
            ),
        ),
        (
            "sorted_self_error_equivalent_simple",
            ghostwriter.equivalent(sorted, sorted, allow_same_errors=True),
        ),
        (
            "sorted_self_error_equivalent_threefuncs",
            ghostwriter.equivalent(sorted, sorted, sorted, allow_same_errors=True),
        ),
        (
            "sorted_self_error_equivalent_1error",
            ghostwriter.equivalent(
                sorted,
                sorted,
                allow_same_errors=True,
                except_=ValueError,
            ),
        ),
        (
            "sorted_self_error_equivalent_2error_unittest",
            ghostwriter.equivalent(
                sorted,
                sorted,
                allow_same_errors=True,
                except_=(TypeError, ValueError),
                style="unittest",
            ),
        ),
        pytest.param(
            ("magic_builtins", ghostwriter.magic(builtins)),
            marks=[
                pytest.mark.skipif(
                    sys.version_info[:2] not in [(3, 8), (3, 9)],
                    reason="compile arg new in 3.8, aiter and anext new in 3.10",
                )
            ],
        ),
    ],
    ids=lambda x: x[0],
)
def test_ghostwriter_example_outputs(update_recorded_outputs, data):
    name, actual = data
    expected = get_recorded(name, actual * update_recorded_outputs)
    assert actual == expected  # We got the expected source code
    exec(expected, {})  # and there are no SyntaxError or NameErrors


def test_ghostwriter_on_hypothesis(update_recorded_outputs):
    actual = ghostwriter.magic(hypothesis).replace("Strategy[+Ex]", "Strategy")
    expected = get_recorded("hypothesis_module_magic", actual * update_recorded_outputs)
    if sys.version_info[:2] < (3, 10):
        assert actual == expected
    exec(expected, {"not_set": not_set})
