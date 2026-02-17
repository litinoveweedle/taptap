"""Tests for the public API module."""

import pytest
from pytap.core.parser import Parser
import pytap


def test_create_parser():
    """create_parser() returns a Parser instance."""
    p = pytap.create_parser()
    assert isinstance(p, Parser)


def test_parse_bytes_empty():
    """parse_bytes(b'') returns empty list."""
    events = pytap.parse_bytes(b'')
    assert events == []


def test_parse_bytes_with_data():
    """parse_bytes with enumeration sequence data returns events."""
    from pytap.tests.test_parser import ENUMERATION_SEQUENCE
    events = pytap.parse_bytes(ENUMERATION_SEQUENCE)
    # Should return at least some events
    assert isinstance(events, list)


def test_connect_invalid():
    """connect({}) raises ValueError."""
    with pytest.raises(ValueError, match="'tcp' or 'serial'"):
        pytap.connect({})


def test_version():
    """Version string is available."""
    assert hasattr(pytap, '__version__')
    assert isinstance(pytap.__version__, str)


def test_all_exports_accessible():
    """All items in __all__ are importable."""
    for name in pytap.__all__:
        assert hasattr(pytap, name), f"{name} not accessible from pytap"
