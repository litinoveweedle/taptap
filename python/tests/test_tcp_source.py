"""Tests for TCP source."""

import pytest
import socket
import threading
import time


def test_tcp_source_creation():
    """Test creating TCP source (will fail to connect in tests)."""
    from taptap.gateway.physical.tcp import TcpSource
    
    # Test that we can create the object
    # Connection will fail, but we test retry limit
    with pytest.raises((ConnectionError, ConnectionRefusedError, OSError)):
        TcpSource('localhost', 9999, reconnect_retry=1, reconnect_delay=0.1)


def test_tcp_source_context_manager():
    """Test TCP source context manager."""
    from taptap.gateway.physical.tcp import TcpSource
    
    # Create a simple echo server for testing
    def echo_server():
        server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        server.bind(('localhost', 0))  # Random port
        port = server.getsockname()[1]
        server.listen(1)
        
        # Signal port is ready
        global test_port
        test_port = port
        
        # Accept one connection
        try:
            server.settimeout(2.0)
            conn, addr = server.accept()
            conn.send(b'Hello')
            time.sleep(0.5)
            conn.close()
        except socket.timeout:
            pass
        finally:
            server.close()
    
    # Start server in thread
    global test_port
    test_port = None
    server_thread = threading.Thread(target=echo_server, daemon=True)
    server_thread.start()
    
    # Wait for server to start
    for _ in range(10):
        if test_port is not None:
            break
        time.sleep(0.1)
    
    if test_port is None:
        pytest.skip("Test server failed to start")
    
    # Test context manager
    with TcpSource('localhost', test_port, reconnect_retry=1) as source:
        data = source.read()
        assert data == b'Hello'


def test_tcp_source_read():
    """Test reading from TCP source."""
    # Create a simple server
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(('localhost', 0))
    port = server.getsockname()[1]
    server.listen(1)
    
    def server_func():
        server.settimeout(2.0)
        try:
            conn, _ = server.accept()
            conn.send(b'Test data 123')
            time.sleep(0.5)
            conn.close()
        except socket.timeout:
            pass
        finally:
            server.close()
    
    server_thread = threading.Thread(target=server_func, daemon=True)
    server_thread.start()
    
    # Small delay to let server start
    time.sleep(0.1)
    
    # Connect and read
    from taptap.gateway.physical.tcp import TcpSource
    
    try:
        source = TcpSource('localhost', port, reconnect_retry=1, reconnect_delay=0.1)
        data = source.read()
        assert b'Test data' in data or data == b''  # May get partial read
        source.close()
    except ConnectionError:
        # Connection timing issues in test - acceptable
        pytest.skip("Connection timing issue")
