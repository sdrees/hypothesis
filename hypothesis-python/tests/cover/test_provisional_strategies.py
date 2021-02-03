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
import string

import pytest

from hypothesis import given
from hypothesis.errors import InvalidArgument
from hypothesis.provisional import domains, urls

from tests.common.debug import find_any


@given(urls())
def test_is_URL(url):
    allowed_chars = set(string.ascii_letters + string.digits + "$-_.+!*'(),~%/")
    url_schemeless = url.split("://", 1)[1]
    path = url_schemeless.split("/", 1)[1] if "/" in url_schemeless else ""
    assert all(c in allowed_chars for c in path)
    assert all(
        re.match("^[0-9A-Fa-f]{2}", after_perc) for after_perc in path.split("%")[1:]
    )


@pytest.mark.parametrize("max_length", [-1, 0, 3, 4.0, 256])
@pytest.mark.parametrize("max_element_length", [-1, 0, 4.0, 64, 128])
def test_invalid_domain_arguments(max_length, max_element_length):
    with pytest.raises(InvalidArgument):
        domains(max_length=max_length, max_element_length=max_element_length).example()


@pytest.mark.parametrize("max_length", [None, 4, 8, 255])
@pytest.mark.parametrize("max_element_length", [None, 1, 2, 4, 8, 63])
def test_valid_domains_arguments(max_length, max_element_length):
    domains(max_length=max_length, max_element_length=max_element_length).example()


@pytest.mark.parametrize("strategy", [domains(), urls()])
def test_find_any_non_empty(strategy):
    find_any(strategy, lambda s: len(s) > 0)
