"""Setup configuration for TapTap Python."""

from setuptools import setup, find_packages

with open("README.md", "r", encoding="utf-8") as fh:
    long_description = fh.read()

setup(
    name="taptap",
    version="0.2.6-py",
    author="Will Glynn, LiTinOveWeedle, Python port by GitHub Copilot",
    description="Python implementation of the Tigo TAP protocol",
    long_description=long_description,
    long_description_content_type="text/markdown",
    url="https://github.com/azebro/taptap",
    packages=find_packages(),
    classifiers=[
        "Development Status :: 4 - Beta",
        "Intended Audience :: Developers",
        "License :: OSI Approved :: MIT License",
        "Programming Language :: Python :: 3",
        "Programming Language :: Python :: 3.8",
        "Programming Language :: Python :: 3.9",
        "Programming Language :: Python :: 3.10",
        "Programming Language :: Python :: 3.11",
    ],
    python_requires=">=3.8",
    install_requires=[
        "pyserial>=3.5",
        "jsonschema>=4.0",
        "click>=8.0",
    ],
    extras_require={
        "dev": [
            "pytest>=7.0",
            "pytest-cov>=4.0",
            "black>=23.0",
            "mypy>=1.0",
        ],
    },
    entry_points={
        "console_scripts": [
            "taptap=taptap.cli.main:main",
        ],
    },
)
