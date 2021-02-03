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

import re

import pytest

from hypothesis import Verbosity, given, settings, strategies as st

from tests.common.utils import capture_out


def test_reports_passes():
    @given(st.integers())
    @settings(verbosity=Verbosity.debug, max_examples=1000)
    def test(i):
        assert i < 10

    with capture_out() as out:
        with pytest.raises(AssertionError):
            test()

    value = out.getvalue()

    assert "minimize_individual_blocks" in value
    assert "calls" in value
    assert "shrinks" in value

    shrinks_info = re.compile(r"call(s?) of which ([0-9]+) shrank")

    for l in value.splitlines():
        m = shrinks_info.search(l)
        if m is not None and int(m.group(2)) != 0:
            break
    else:
        pytest.xfail(reason="Sometimes the first failure is 10, and cannot shrink.")
