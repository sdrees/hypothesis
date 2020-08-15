# This file is part of Hypothesis, which may be found at
# https://github.com/HypothesisWorks/hypothesis/
#
# Most of this work is copyright (C) 2013-2020 David R. MacIver
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

"""
WARNING: this module is under development and should not be used... yet.
See https://github.com/HypothesisWorks/hypothesis/pull/2344 for progress.
"""

import builtins
import enum
import inspect
import sys
import types
from collections import OrderedDict
from itertools import permutations, zip_longest
from string import ascii_lowercase
from textwrap import indent
from typing import Callable, Dict, Set, Tuple, Type, Union

import black

from hypothesis import strategies as st
from hypothesis.errors import InvalidArgument
from hypothesis.strategies._internal.strategies import OneOfStrategy
from hypothesis.utils.conventions import InferType, infer

IMPORT_SECTION = """
# This test code was written by the `hypothesis.extra.ghostwriter` module
# and is provided under the Creative Commons Zero public domain dedication.

{imports}from hypothesis import given, {reject}strategies as st
"""

TEMPLATE = """
@given({given_args})
def test_{test_kind}_{func_name}({arg_names}):
{test_body}
"""

SUPPRESS_BLOCK = """\
try:
{test_body}
except {exceptions}:
    reject()
"""

Except = Union[Type[Exception], Tuple[Type[Exception], ...]]


def _check_except(except_: Except) -> Tuple[Type[Exception], ...]:
    if isinstance(except_, tuple):
        for i, e in enumerate(except_):
            if not isinstance(e, type) or not issubclass(e, Exception):
                raise InvalidArgument(
                    f"Expected an Exception but got except_[{i}]={e!r}"
                    f" (type={_get_qualname(type(e))})"
                )
        return except_
    if not isinstance(except_, type) or not issubclass(except_, Exception):
        raise InvalidArgument(
            "Expected an Exception or tuple of exceptions, but got except_="
            f"{except_!r} (type={_get_qualname(type(except_))})"
        )
    return (except_,)


def _check_style(style: str) -> None:
    if style not in ("pytest", "unittest"):
        raise InvalidArgument(f"Valid styles are 'pytest' or 'unittest', got {style!r}")


# Simple strategies to guess for common argument names - we wouldn't do this in
# builds() where strict correctness is required, but we only use these guesses
# when the alternative is nothing() to force user edits anyway.
#
# This table was constructed manually after skimming through the documentation
# for the builtins and a few stdlib modules.  Future enhancements could be based
# on analysis of type-annotated code to detect arguments which almost always
# take values of a particular type.
_GUESS_STRATEGIES_BY_NAME = (
    (st.text(), ["name", "filename", "fname"]),
    (st.integers(min_value=0), ["index"]),
    (st.floats(), ["real", "imag"]),
    (st.functions(), ["function", "func", "f"]),
    (st.iterables(st.integers()) | st.iterables(st.text()), ["iterable"]),
)


def _strategy_for(param: inspect.Parameter) -> Union[st.SearchStrategy, InferType]:
    # We use `infer` and go via `builds()` instead of directly through
    # `from_type()` so that `get_type_hints()` can resolve any forward
    # references for us.
    if param.annotation is not inspect.Parameter.empty:
        return infer
    # If our default value is an Enum or a boolean, we assume that any value
    # of that type is acceptable.  Otherwise, we only generate the default.
    if isinstance(param.default, bool):
        return st.booleans()
    if isinstance(param.default, enum.Enum):
        return st.sampled_from(type(param.default))
    if param.default is not inspect.Parameter.empty:
        # Using `st.from_type(type(param.default))` would  introduce spurious
        # failures in cases like the `flags` argument to regex functions.
        # Better in to keep it simple, and let the user elaborate if desired.
        return st.just(param.default)
    # If there's no annotation and no default value, we check against a table
    # of guesses of simple strategies for common argument names.
    if "string" in param.name and "as" not in param.name:
        return st.text()
    for strategy, names in _GUESS_STRATEGIES_BY_NAME:
        if param.name in names:
            return strategy
    # And if all that failed, we'll return nothing() - the user will have to
    # fill this in by hand, and we'll leave a comment to that effect later.
    return st.nothing()


def _get_params(func: Callable) -> Dict[str, inspect.Parameter]:
    """Get non-vararg parameters of `func` as an ordered dict."""
    var_param_kinds = (inspect.Parameter.VAR_POSITIONAL, inspect.Parameter.VAR_KEYWORD)
    try:
        params = list(inspect.signature(func).parameters.values())
    except Exception:
        # `inspect.signature` doesn't work on ufunc objects, but we can work out
        # what the required parameters would look like if it did.
        if not _is_probably_ufunc(func):
            raise
        # Note that we use args named a, b, c... to match the `operator` module,
        # rather than x1, x2, x3... like the Numpy docs.  Because they're pos-only
        # this doesn't make a runtime difference, and it's much nicer for use-cases
        # like `equivalent(numpy.add, operator.add)`.
        params = [
            inspect.Parameter(name=name, kind=inspect.Parameter.POSITIONAL_ONLY)
            for name in ascii_lowercase[: func.nin]  # type: ignore
        ]
    return OrderedDict((p.name, p) for p in params if p.kind not in var_param_kinds)


def _get_strategies(
    *funcs: Callable, pass_result_to_next_func: bool = False
) -> Dict[str, st.SearchStrategy]:
    """Return a dict of strategies for the union of arguments to `funcs`.

    If `pass_result_to_next_func` is True, assume that the result of each function
    is passed to the next, and therefore skip the first argument of all but the
    first function.

    This dict is used to construct our call to the `@given(...)` decorator.
    """
    given_strategies = {}  # type: Dict[str, st.SearchStrategy]
    for i, f in enumerate(funcs):
        params = _get_params(f)
        if pass_result_to_next_func and i >= 1:
            del params[next(iter(params))]
        builder_args = {k: _strategy_for(v) for k, v in params.items()}
        strat = st.builds(f, **builder_args).wrapped_strategy  # type: ignore

        args, kwargs = strat.mapped_strategy.wrapped_strategy.element_strategies
        if args.element_strategies:
            raise NotImplementedError("Expected to pass everything as kwargs")

        for k, v in zip(kwargs.keys, kwargs.mapped_strategy.element_strategies):
            if isinstance(v, OneOfStrategy):
                # repr nested one_of as flattened (their real behaviour)
                v = st.one_of(v.element_strategies)
            if repr(given_strategies.get(k, v)) != repr(v):
                # In this branch, we have two functions that take an argument of the
                # same name but different strategies - probably via the equivalent()
                # ghostwriter.  In general, we would expect the test to pass given
                # the *intersection* of the domains of these functions.  However:
                #   - we can't take the intersection of two strategies
                #   - this may indicate a problem which should be exposed to the user
                # and so we take the *union* instead - either it'll work, or the
                # user will be presented with a reasonable suite of options.
                given_strategies[k] = given_strategies[k] | v
            else:
                given_strategies[k] = v

    # If there is only one function, we pass arguments to @given in the order of
    # that function's signature.  Otherwise, we use alphabetical order.
    if len(funcs) == 1:
        return {name: given_strategies[name] for name in _get_params(f)}
    return dict(sorted(given_strategies.items()))


def _assert_eq(style, a, b):
    return {
        "pytest": f"assert {a} == {b}, ({a}, {b})",
        "unittest": f"self.assertEqual({a}, {b})",
    }[style]


def _valid_syntax_repr(strategy):
    if strategy == st.text().wrapped_strategy:
        return "text()"
    # Return a syntactically-valid strategy repr, including fixing some
    # strategy reprs and replacing invalid syntax reprs with `"nothing()"`.
    # String-replace to hide the special case in from_type() for Decimal('snan')
    r = repr(strategy).replace(".filter(_can_hash)", "")
    try:
        compile(r, "<string>", "eval")
        return r
    except SyntaxError:
        return "nothing()"


# (g)ufuncs do not have a __module__ attribute, so we simply look for them in
# any of the following modules which are found in sys.modules.  The order of
# these entries doesn't matter, because we check identity of the found object.
LOOK_FOR_UFUNCS_IN_MODULES = ("numpy", "astropy", "erfa", "dask", "numba")


def _get_module(obj):
    try:
        return obj.__module__
    except AttributeError:
        if not _is_probably_ufunc(obj):
            raise
    for module_name in LOOK_FOR_UFUNCS_IN_MODULES:
        if obj is getattr(sys.modules.get(module_name), obj.__name__, None):
            return module_name
    raise RuntimeError(f"Could not find module for ufunc {obj.__name__} ({obj!r}")


def _get_qualname(obj, include_module=False):
    # Replacing angle-brackets for objects defined in `.<locals>.`
    qname = getattr(obj, "__qualname__", obj.__name__)
    qname = qname.replace("<", "_").replace(">", "_")
    if include_module:
        return _get_module(obj) + "." + qname
    return qname


def _write_call(func: Callable, *pass_variables: str) -> str:
    """Write a call to `func` with explicit and implicit arguments.

    >>> _write_call(sorted, "my_seq", "func")
    "builtins.sorted(my_seq, key=func, reverse=reverse)"
    """
    args = ", ".join(
        (v or p.name)
        if p.kind is inspect.Parameter.POSITIONAL_ONLY
        else f"{p.name}={v or p.name}"
        for v, p in zip_longest(pass_variables, _get_params(func).values())
    )
    return f"{_get_qualname(func, include_module=True)}({args})"


def _make_test_body(
    *funcs: Callable,
    ghost: str,
    test_body: str,
    except_: Tuple[Type[Exception], ...],
    style: str,
) -> Tuple[Set[str], str]:
    # Get strategies for all the arguments to each function we're testing.
    given_strategies = _get_strategies(
        *funcs, pass_result_to_next_func=ghost in ("idempotent", "roundtrip")
    )
    given_args = ", ".join(
        "{}={}".format(k, _valid_syntax_repr(v)) for k, v in given_strategies.items()
    )
    for name in st.__all__:
        given_args = given_args.replace(f"{name}(", f"st.{name}(")

    # A set of modules to import - we might add to this later.  The import code
    # is written later, so we can have one import section for multiple magic()
    # test functions.
    imports = {_get_module(f) for f in funcs}

    if except_:
        # This is reminiscent of de-duplication logic I wrote for flake8-bugbear,
        # but with access to the actual objects we can just check for subclasses.
        # This lets us print e.g. `Exception` instead of `(Exception, OSError)`.
        uniques = list(except_)
        for a, b in permutations(except_, 2):
            if a in uniques and issubclass(a, b):
                uniques.remove(a)
        # Then convert to strings, either builtin names or qualified names.
        exceptions = []
        for ex in uniques:
            if ex.__qualname__ in dir(builtins):
                exceptions.append(ex.__qualname__)
            else:
                imports.add(ex.__module__)
                exceptions.append(_get_qualname(ex, include_module=True))
        # And finally indent the existing test body into a try-except block
        # which catches these exceptions and calls `hypothesis.reject()`.
        test_body = SUPPRESS_BLOCK.format(
            test_body=indent(test_body, prefix="    "),
            exceptions="(" + ", ".join(exceptions) + ")"
            if len(exceptions) > 1
            else exceptions[0],
        )

    # Indent our test code to form the body of a function or method.
    argnames = (["self"] if style == "unittest" else []) + list(given_strategies)
    body = TEMPLATE.format(
        given_args=given_args,
        test_kind=ghost,
        func_name="_".join(_get_qualname(f).replace(".", "_") for f in funcs),
        arg_names=", ".join(argnames),
        test_body=indent(test_body, prefix="    "),
    )

    # For unittest-style, indent method further into a class body
    if style == "unittest":
        imports.add("unittest")
        body = "class Test{}{}(unittest.TestCase):\n".format(
            ghost.title(),
            "".join(_get_qualname(f).replace(".", "").title() for f in funcs),
        ) + indent(body, "    ")

    return imports, body


def _make_test(imports: Set[str], body: str) -> str:
    # Discarding "builtins." and "__main__" probably isn't particularly useful
    # for user code, but important for making a good impression in demos.
    body = body.replace("builtins.", "").replace("__main__.", "")
    imports.discard("builtins")
    imports.discard("__main__")
    header = IMPORT_SECTION.format(
        imports="".join(f"import {imp}\n" for imp in sorted(imports)),
        reject="reject, " if "        reject()\n" in body else "",
    )
    nothings = body.count("=st.nothing()")
    if nothings == 1:
        header += "# TODO: replace st.nothing() with an appropriate strategy\n\n"
    elif nothings >= 1:
        header += "# TODO: replace st.nothing() with appropriate strategies\n\n"
    return black.format_str(header + body, mode=black.FileMode())


def _is_probably_ufunc(obj):
    # See https://numpy.org/doc/stable/reference/ufuncs.html - there doesn't seem
    # to be an upstream function to detect this, so we just guess.
    has_attributes = "nin nout nargs ntypes types identity signature".split()
    return callable(obj) and all(hasattr(obj, name) for name in has_attributes)


def magic(
    *modules_or_functions: Union[Callable, types.ModuleType],
    except_: Except = (),
    style: str = "pytest",
) -> str:
    """Guess which ghostwriters to use, for a module or collection of functions.

    As for all ghostwriters, the ``except_`` argument should be an
    :class:`python:Exception` or tuple of exceptions, and ``style`` may be either
    ``"pytest"`` to write test functions or ``"unittest"`` to write test methods
    and :class:`~python:unittest.TestCase`.

    After finding the public functions attached to any modules, the ``magic``
    ghostwriter looks for pairs of functions to pass to :func:`~roundtrip`,
    and any others are passed to :func:`~fuzz`.
    """
    except_ = _check_except(except_)
    _check_style(style)
    if not modules_or_functions:
        raise InvalidArgument("Must pass at least one function or module to test.")
    functions = set()
    for thing in modules_or_functions:
        if callable(thing):
            functions.add(thing)
        elif isinstance(thing, types.ModuleType):
            if hasattr(thing, "__all__"):
                funcs = [getattr(thing, name) for name in thing.__all__]  # type: ignore
            else:
                funcs = [
                    v
                    for k, v in vars(thing).items()
                    if callable(v) and not k.startswith("_")
                ]
            for f in funcs:
                try:
                    if callable(f) and inspect.signature(f).parameters:
                        functions.add(f)
                except ValueError:
                    pass
        else:
            raise InvalidArgument(f"Can't test non-module non-callable {thing!r}")

    imports = set()
    parts = []
    by_name = {_get_qualname(f): f for f in functions}
    if len(by_name) < len(functions):
        raise InvalidArgument("Functions to magic() test must have unique names")

    # TODO: identify roundtrip pairs, and write a specific test for each

    # For all remaining callables, just write a fuzz-test.  In principle we could
    # guess at equivalence or idempotence; but it doesn't seem accurate enough to
    # be worth the trouble when it's so easy for the user to specify themselves.
    for _, f in sorted(by_name.items()):
        imp, body = _make_test_body(
            f, test_body=_write_call(f), except_=except_, ghost="fuzz", style=style,
        )
        imports |= imp
        parts.append(body)
    return _make_test(imports, "\n".join(parts))


def fuzz(func: Callable, *, except_: Except = (), style: str = "pytest") -> str:
    """Write source code for a property-based test of ``func``.

    The resulting test checks that valid input only leads to expected exceptions.
    For example:

    .. code-block:: python

        from re import compile, error
        from hypothesis.extra import ghostwriter

        ghostwriter.fuzz(compile, except_=error)

    Gives:

    .. code-block:: python

        # This test code was written by the `hypothesis.extra.ghostwriter` module
        # and is provided under the Creative Commons Zero public domain dedication.
        import re
        from hypothesis import given, reject, strategies as st

        # TODO: replace st.nothing() with an appropriate strategy

        @given(pattern=st.nothing(), flags=st.just(0))
        def test_fuzz_compile(pattern, flags):
            try:
                re.compile(pattern=pattern, flags=flags)
            except re.error:
                reject()

    Note that it includes all the required imports.
    Because the ``pattern`` parameter doesn't have annotations or a default argument,
    you'll need to specify a strategy - for example :func:`~hypothesis.strategies.text`
    or :func:`~hypothesis.strategies.binary`.  After that, you have a test!
    """
    if not callable(func):
        raise InvalidArgument(f"Got non-callable func={func!r}")
    except_ = _check_except(except_)
    _check_style(style)

    imports, body = _make_test_body(
        func, test_body=_write_call(func), except_=except_, ghost="fuzz", style=style
    )
    return _make_test(imports, body)
