"""Tests for CLI."""

import pytest
from click.testing import CliRunner


def test_cli_help():
    """Test CLI help output."""
    from taptap.cli.main import cli
    
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    
    assert result.exit_code == 0
    assert 'TapTap' in result.output
    assert 'observe' in result.output


def test_cli_version():
    """Test CLI version output."""
    from taptap.cli.main import cli
    
    runner = CliRunner()
    result = runner.invoke(cli, ['--version'])
    
    assert result.exit_code == 0
    assert '0.2.6.post1' in result.output


def test_observe_requires_source():
    """Test that observe command requires --serial or --tcp."""
    from taptap.cli.main import cli
    
    runner = CliRunner()
    result = runner.invoke(cli, ['observe'])
    
    assert result.exit_code != 0
    assert 'Must specify either --serial or --tcp' in result.output


def test_observe_rejects_both_sources():
    """Test that observe rejects both --serial and --tcp."""
    from taptap.cli.main import cli
    
    runner = CliRunner()
    result = runner.invoke(cli, ['observe', '--serial', '/dev/ttyUSB0', '--tcp', 'localhost'])
    
    assert result.exit_code != 0
    assert 'Cannot specify both' in result.output


def test_observe_help():
    """Test observe command help."""
    from taptap.cli.main import cli
    
    runner = CliRunner()
    result = runner.invoke(cli, ['observe', '--help'])
    
    assert result.exit_code == 0
    assert '--serial' in result.output
    assert '--tcp' in result.output
    assert '--state-file' in result.output


def test_list_serial_ports():
    """Test list-serial-ports command."""
    from taptap.cli.main import cli
    
    runner = CliRunner()
    result = runner.invoke(cli, ['list-serial-ports'])
    
    # Should either list ports or say none found
    assert result.exit_code == 0 or 'pyserial is not installed' in result.output


def test_peek_bytes_help():
    """Test peek-bytes command help."""
    from taptap.cli.main import cli
    
    runner = CliRunner()
    result = runner.invoke(cli, ['peek-bytes', '--help'])
    
    assert result.exit_code == 0
    assert '--raw' in result.output


def test_peek_frames_help():
    """Test peek-frames command help."""
    from taptap.cli.main import cli
    
    runner = CliRunner()
    result = runner.invoke(cli, ['peek-frames', '--help'])
    
    assert result.exit_code == 0
    assert '--serial' in result.output
    assert '--tcp' in result.output


def test_peek_frames_requires_source():
    """Test that peek-frames requires --serial or --tcp."""
    from taptap.cli.main import cli
    
    runner = CliRunner()
    result = runner.invoke(cli, ['peek-frames'])
    
    assert result.exit_code != 0
    assert 'Must specify either --serial or --tcp' in result.output


def test_peek_activity_help():
    """Test peek-activity command help."""
    from taptap.cli.main import cli
    
    runner = CliRunner()
    result = runner.invoke(cli, ['peek-activity', '--help'])
    
    assert result.exit_code == 0
    assert '--serial' in result.output
    assert '--tcp' in result.output


def test_peek_activity_requires_source():
    """Test that peek-activity requires --serial or --tcp."""
    from taptap.cli.main import cli
    
    runner = CliRunner()
    result = runner.invoke(cli, ['peek-activity'])
    
    assert result.exit_code != 0
    assert 'Must specify either --serial or --tcp' in result.output


def test_cli_lists_all_commands():
    """Test that CLI help lists all five commands."""
    from taptap.cli.main import cli
    
    runner = CliRunner()
    result = runner.invoke(cli, ['--help'])
    
    assert result.exit_code == 0
    assert 'observe' in result.output
    assert 'peek-bytes' in result.output
    assert 'peek-frames' in result.output
    assert 'peek-activity' in result.output
    assert 'list-serial-ports' in result.output
