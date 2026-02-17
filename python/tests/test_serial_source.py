"""Tests for serial source."""

import pytest


def test_serial_source_import():
    """Test that SerialSource can be imported."""
    from taptap.gateway.physical.serial import SerialSource, SERIAL_AVAILABLE
    
    # Just verify import works
    assert SerialSource is not None


def test_serial_source_requires_pyserial():
    """Test that SerialSource raises ImportError without pyserial."""
    from taptap.gateway.physical.serial import SERIAL_AVAILABLE, SerialSource
    
    if SERIAL_AVAILABLE:
        # pyserial is installed - just verify we can create object
        # (won't try to open actual port)
        assert SerialSource is not None
    else:
        # pyserial not installed - verify error message
        with pytest.raises(ImportError, match="pyserial is required"):
            SerialSource('/dev/null')


def test_serial_source_context_manager():
    """Test serial source supports context manager."""
    from taptap.gateway.physical.serial import SerialSource, SERIAL_AVAILABLE
    
    if not SERIAL_AVAILABLE:
        pytest.skip("pyserial not available")
    
    # Test context manager protocol exists
    assert hasattr(SerialSource, '__enter__')
    assert hasattr(SerialSource, '__exit__')
