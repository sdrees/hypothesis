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

from hypothesis import given, strategies as st


class BadRepr:
    def __init__(self, value):
        self.value = value

    def __repr__(self):
        return self.value


Frosty = BadRepr("☃")


def test_just_frosty():
    assert repr(st.just(Frosty)) == "just(☃)"


def test_sampling_snowmen():
    assert repr(st.sampled_from((Frosty, "hi"))) == "sampled_from((☃, 'hi'))"


def varargs(*args, **kwargs):
    pass


@given(
    st.sampled_from(
        [
            "✐",
            "✑",
            "✒",
            "✓",
            "✔",
            "✕",
            "✖",
            "✗",
            "✘",
            "✙",
            "✚",
            "✛",
            "✜",
            "✝",
            "✞",
            "✟",
            "✠",
            "✡",
            "✢",
            "✣",
        ]
    )
)
def test_sampled_from_bad_repr(c):
    pass
