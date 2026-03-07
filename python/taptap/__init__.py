"""TapTap: Tigo TAP protocol implementation in Python.

This is a Python port of the TapTap Rust implementation, providing
identical functionality for monitoring Tigo TAP solar energy systems.
"""

__version__ = '0.2.6.post1'
__author__ = 'Will Glynn, LiTinOveWeedle, Python port by Copilot'

from .barcode import Barcode

__all__ = ['Barcode']
