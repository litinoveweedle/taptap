"""pytap package setup."""
from setuptools import setup

setup(
    name='pytap',
    version='0.1.0',
    description='Simplified TapTap protocol parser for Tigo TAP solar monitoring',
    package_dir={'pytap': '.'},
    packages=['pytap', 'pytap.core', 'pytap.cli', 'pytap.tests'],
    python_requires='>=3.10',
    install_requires=[],
    extras_require={
        'serial': ['pyserial>=3.5'],
        'cli': ['click>=8.0'],
        'dev': ['pytest>=7.0', 'pytest-cov'],
    },
    entry_points={
        'console_scripts': [
            'pytap=pytap.cli.main:main',
        ],
    },
)
