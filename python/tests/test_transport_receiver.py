"""Tests for gateway transport receiver."""

import pytest
from taptap.gateway.transport.messages import (
    ReceiveRequest, ReceiveResponse, interpret_packet_number_lo
)
from taptap.gateway.transport.receiver import Receiver, Counters
from taptap.gateway.link import Frame, Type, Address, GatewayID
from taptap.pv.link.slot_counter import SlotCounter
from taptap.pv.network import ReceivedPacketHeader


def test_interpret_packet_number_lo():
    """Test packet number expansion."""
    # No wrap
    assert interpret_packet_number_lo(0x84, 0x1883) == 0x1884
    
    # Wrap
    assert interpret_packet_number_lo(0x00, 0x18FF) == 0x1900
    assert interpret_packet_number_lo(0x01, 0x18FF) == 0x1901


def test_receive_request_from_bytes():
    """Test parsing ReceiveRequest."""
    data = bytes([0x00, 0x01, 0x18, 0x83, 0x04])
    req = ReceiveRequest.from_bytes(data)
    
    assert req is not None
    assert req.unknown_1 == bytes([0x00, 0x01])
    assert req.packet_number == 0x1883
    assert req.unknown_2 == 0x04


def test_receive_request_too_short():
    """Test ReceiveRequest with insufficient data."""
    assert ReceiveRequest.from_bytes(bytes([1, 2, 3])) is None


def test_receive_response_from_bytes():
    """Test parsing ReceiveResponse."""
    # Example from Rust tests
    data = bytes([
        0x00, 0xFE,  # status_type
        0x01,  # rx_buffers_used
        0x83,  # packet_number_lo
        0x5A, 0xDE,  # slot_counter
        # Packets data follows
        0x07, 0x00, 0x0A, 0x01, 0x14, 0x63, 0x3A,
    ])
    
    result = ReceiveResponse.read_from_bytes(data, 0x1883)
    assert result is not None
    
    response, packets = result
    assert response.rx_buffers_used == 0x01
    assert response.tx_buffers_free is None
    assert response.packet_number == 0x1883  # Expanded from 0x83
    
    # Check slot counter
    assert response.slot_counter.to_u16() == 0x5ADE


def test_receive_response_full_packet_number():
    """Test ReceiveResponse with full 16-bit packet number."""
    data = bytes([
        0x00, 0xEF,  # status_type (bits 0-3 set, bit 4 clear = full packet number, bits 5-7 set)
        0x18, 0x84,  # packet_number (16-bit)
        0x5A, 0xDE,  # slot_counter
    ])
    
    result = ReceiveResponse.read_from_bytes(data, 0x0000)
    assert result is not None
    
    response, packets = result
    assert response.packet_number == 0x1884
    assert response.rx_buffers_used is None
    assert response.tx_buffers_free is None


def test_receive_response_h_firmware_no_optional_fields():
    """Test H-firmware status 0x011F — no optional fields (equivalent to G-firmware 0x01FF).
    
    From tigo_parsing.md Appendix A: TAP2: 01 1F AD D3 CB
    """
    data = bytes([0x01, 0x1F, 0xAD, 0xD3, 0xCB])
    result = ReceiveResponse.read_from_bytes(data, 0x00AC)
    assert result is not None

    response, packets = result
    assert response.rx_buffers_used is None
    assert response.tx_buffers_free is None
    assert response.unknown_a is None
    assert response.unknown_b is None
    assert response.packet_number == 0x00AD
    assert response.slot_counter.to_u16() == 0xD3CB
    assert packets._data == b''


def test_receive_response_h_firmware_with_rx_buffers():
    """Test H-firmware status 0x011E — rx_buffers_used present (equivalent to G-firmware 0x01FE).
    
    From tigo_parsing.md Appendix A: TAP3 data-bearing response with power report.
    """
    data = bytes([0x01, 0x1E, 0x02, 0x4A, 0xD4, 0x57, 0x31, 0x00, 0x1B])
    result = ReceiveResponse.read_from_bytes(data, 0x0049)
    assert result is not None

    response, packets = result
    assert response.rx_buffers_used == 0x02
    assert response.tx_buffers_free is None
    assert response.packet_number == 0x004A
    assert response.slot_counter.to_u16() == 0xD457
    assert packets._data == bytes([0x31, 0x00, 0x1B])


def test_receive_response_h_firmware_all_optional_fields():
    """Test H-firmware status 0x0100 — all optional fields (equivalent to G-firmware 0x01E0)."""
    data = bytes([0x01, 0x00, 0x04, 0x0E, 0x00, 0x01, 0x02, 0x00, 0x40, 0xFB, 0x21, 0x1B, 5, 6])
    result = ReceiveResponse.read_from_bytes(data, 0x40FB)
    assert result is not None

    response, packets = result
    assert response.rx_buffers_used == 0x04
    assert response.tx_buffers_free == 0x0E
    assert response.unknown_a == bytes([0x00, 0x01])
    assert response.unknown_b == bytes([0x02, 0x00])
    assert response.packet_number == 0x40FB
    assert response.slot_counter.to_u16() == 0x211B
    assert packets._data == bytes([5, 6])


class MockSink:
    """Mock sink for testing — implements all 8 transport.Sink methods."""
    
    def __init__(self):
        self.slot_counter_captured = []
        self.slot_counter_observed = []
        self.packets_received = []
        self.enumeration_started_events = []
        self.gateway_identities = []
        self.gateway_versions = []
        self.enumeration_ended_events = []
        self.commands_executed = []
    
    def enumeration_started(self, enumeration_gateway_id: GatewayID) -> None:
        self.enumeration_started_events.append(enumeration_gateway_id)
    
    def gateway_identity_observed(self, gateway_id: GatewayID, address) -> None:
        self.gateway_identities.append((gateway_id, address))
    
    def gateway_version_observed(self, gateway_id: GatewayID, version: str) -> None:
        self.gateway_versions.append((gateway_id, version))
    
    def enumeration_ended(self, gateway_id: GatewayID) -> None:
        self.enumeration_ended_events.append(gateway_id)
    
    def gateway_slot_counter_captured(self, gateway_id: GatewayID) -> None:
        self.slot_counter_captured.append(gateway_id)
    
    def gateway_slot_counter_observed(self, gateway_id: GatewayID, slot_counter: SlotCounter) -> None:
        self.slot_counter_observed.append((gateway_id, slot_counter))
    
    def packet_received(self, gateway_id: GatewayID, header: ReceivedPacketHeader, data: bytes) -> None:
        self.packets_received.append((gateway_id, header, data))
    
    def command_executed(self, gateway_id: GatewayID, request, response) -> None:
        self.commands_executed.append((gateway_id, request, response))


def test_transport_receiver_receive_request():
    """Test transport receiver handles RECEIVE_REQUEST."""
    sink = MockSink()
    rx = Receiver(sink)
    
    frame = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.RECEIVE_REQUEST,
        payload=bytes([0x00, 0x01, 0x18, 0x83, 0x04])
    )
    
    rx.frame(frame)
    
    assert rx.counters.receive_requests == 1
    assert len(sink.slot_counter_captured) == 1


def test_transport_receiver_receive_response():
    """Test transport receiver handles RECEIVE_RESPONSE."""
    sink = MockSink()
    rx = Receiver(sink)
    
    # First send a request to establish packet number
    request_frame = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.RECEIVE_REQUEST,
        payload=bytes([0x00, 0x01, 0x18, 0x83, 0x04])
    )
    rx.frame(request_frame)
    
    # Then send a response
    response_frame = Frame(
        address=Address.from_(GatewayID(0x1201)),
        frame_type=Type.RECEIVE_RESPONSE,
        payload=bytes([
            0x00, 0xFE,  # status_type
            0x01,  # rx_buffers_used
            0x83,  # packet_number_lo
            0x5A, 0xDE,  # slot_counter
            # No packets
        ])
    )
    rx.frame(response_frame)
    
    assert rx.counters.receive_responses == 1
    assert len(sink.slot_counter_observed) == 1
    assert sink.slot_counter_observed[0][1].to_u16() == 0x5ADE


def test_transport_receiver_ping():
    """Test transport receiver counts ping frames."""
    sink = MockSink()
    rx = Receiver(sink)
    
    ping_req = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.PING_REQUEST,
        payload=bytes()
    )
    rx.frame(ping_req)
    
    ping_resp = Frame(
        address=Address.from_(GatewayID(0x1201)),
        frame_type=Type.PING_RESPONSE,
        payload=bytes()
    )
    rx.frame(ping_resp)
    
    assert rx.counters.ping_requests == 1
    assert rx.counters.ping_responses == 1


def test_transport_receiver_reset_counters():
    """Test counter reset."""
    sink = MockSink()
    rx = Receiver(sink)
    
    ping = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.PING_REQUEST,
        payload=bytes()
    )
    rx.frame(ping)
    
    assert rx.counters.ping_requests == 1
    
    rx.reset_counters()
    
    assert rx.counters.ping_requests == 0


# --- Enumeration tests ---

def test_enumeration_start_request():
    """Test ENUMERATION_START_REQUEST triggers enumeration_started."""
    sink = MockSink()
    rx = Receiver(sink)

    # Build payload: 4 unknown bytes + 2-byte "to" address for enum gateway
    enum_gw_id = GatewayID(0x0005)
    enum_addr_bytes = Address.to(enum_gw_id).to_bytes()
    payload = bytes([0x00, 0x00, 0x00, 0x00]) + enum_addr_bytes

    frame = Frame(
        address=Address.to(GatewayID(0)),  # broadcast (gateway_id=0)
        frame_type=Type.ENUMERATION_START_REQUEST,
        payload=payload,
    )
    rx.frame(frame)

    assert rx.counters.enumeration_start_requests == 1
    assert len(sink.enumeration_started_events) == 1
    assert sink.enumeration_started_events[0].value == 0x0005


def test_enumeration_start_request_invalid_direction():
    """ENUMERATION_START_REQUEST with wrong direction is invalid."""
    sink = MockSink()
    rx = Receiver(sink)

    frame = Frame(
        address=Address.from_(GatewayID(0)),  # wrong direction
        frame_type=Type.ENUMERATION_START_REQUEST,
        payload=bytes([0x00] * 6),
    )
    rx.frame(frame)

    assert rx.counters.invalid_enumeration_start_request == 1
    assert len(sink.enumeration_started_events) == 0


def test_enumeration_start_request_short_payload():
    """ENUMERATION_START_REQUEST with <6 bytes payload."""
    sink = MockSink()
    rx = Receiver(sink)

    frame = Frame(
        address=Address.to(GatewayID(0)),
        frame_type=Type.ENUMERATION_START_REQUEST,
        payload=bytes([0x00, 0x01, 0x02]),
    )
    rx.frame(frame)

    assert rx.counters.invalid_enumeration_start_request == 1


def test_enumeration_response():
    """Test ENUMERATION_RESPONSE emits gateway_identity_observed."""
    sink = MockSink()
    rx = Receiver(sink)

    long_addr = bytes([0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08])
    frame = Frame(
        address=Address.from_(GatewayID(0x0005)),
        frame_type=Type.ENUMERATION_RESPONSE,
        payload=long_addr,
    )
    rx.frame(frame)

    assert rx.counters.enumeration_responses == 1
    assert len(sink.gateway_identities) == 1
    assert sink.gateway_identities[0][0].value == 0x0005
    assert sink.gateway_identities[0][1].address == long_addr


def test_enumeration_response_short_payload():
    """ENUMERATION_RESPONSE with <8 bytes is invalid."""
    sink = MockSink()
    rx = Receiver(sink)

    frame = Frame(
        address=Address.from_(GatewayID(5)),
        frame_type=Type.ENUMERATION_RESPONSE,
        payload=bytes([0x01, 0x02, 0x03]),
    )
    rx.frame(frame)

    assert rx.counters.invalid_enumeration_responses == 1
    assert len(sink.gateway_identities) == 0


def test_identify_response():
    """Test IDENTIFY_RESPONSE emits gateway_identity_observed."""
    sink = MockSink()
    rx = Receiver(sink)

    long_addr = bytes([0xAA, 0xBB, 0xCC, 0xDD, 0xEE, 0xFF, 0x11, 0x22])
    frame = Frame(
        address=Address.from_(GatewayID(0x1201)),
        frame_type=Type.IDENTIFY_RESPONSE,
        payload=long_addr,
    )
    rx.frame(frame)

    assert rx.counters.identify_responses == 1
    assert len(sink.gateway_identities) == 1
    assert sink.gateway_identities[0][1].address == long_addr


def test_version_response():
    """Test VERSION_RESPONSE emits gateway_version_observed."""
    sink = MockSink()
    rx = Receiver(sink)

    version_str = b"1.2.3"
    frame = Frame(
        address=Address.from_(GatewayID(0x1201)),
        frame_type=Type.VERSION_RESPONSE,
        payload=version_str,
    )
    rx.frame(frame)

    assert rx.counters.version_responses == 1
    assert len(sink.gateway_versions) == 1
    assert sink.gateway_versions[0][1] == "1.2.3"


def test_version_response_empty():
    """Empty VERSION_RESPONSE is invalid."""
    sink = MockSink()
    rx = Receiver(sink)

    frame = Frame(
        address=Address.from_(GatewayID(0x1201)),
        frame_type=Type.VERSION_RESPONSE,
        payload=b"",
    )
    rx.frame(frame)

    assert rx.counters.invalid_version_responses == 1
    assert len(sink.gateway_versions) == 0


def test_version_response_invalid_utf8():
    """VERSION_RESPONSE with invalid UTF-8 is rejected."""
    sink = MockSink()
    rx = Receiver(sink)

    frame = Frame(
        address=Address.from_(GatewayID(0x1201)),
        frame_type=Type.VERSION_RESPONSE,
        payload=bytes([0xFF, 0xFE]),
    )
    rx.frame(frame)

    assert rx.counters.invalid_version_responses == 1
    assert len(sink.gateway_versions) == 0


def test_enumeration_end_response():
    """Test ENUMERATION_END_RESPONSE emits enumeration_ended."""
    sink = MockSink()
    rx = Receiver(sink)

    frame = Frame(
        address=Address.from_(GatewayID(0x1201)),
        frame_type=Type.ENUMERATION_END_RESPONSE,
        payload=bytes(),
    )
    rx.frame(frame)

    assert rx.counters.enumeration_end_responses == 1
    assert len(sink.enumeration_ended_events) == 1
    assert sink.enumeration_ended_events[0].value == 0x1201


def test_full_enumeration_sequence():
    """Test a complete enumeration: start → response → identify → version → end."""
    sink = MockSink()
    rx = Receiver(sink)
    enum_gw = GatewayID(0x0005)
    real_gw = GatewayID(0x0001)

    # 1. Start
    enum_addr_bytes = Address.to(enum_gw).to_bytes()
    start = Frame(
        address=Address.to(GatewayID(0)),
        frame_type=Type.ENUMERATION_START_REQUEST,
        payload=bytes([0x00] * 4) + enum_addr_bytes,
    )
    rx.frame(start)

    # 2. Enumeration response (identity via enumeration)
    long_addr = bytes([0x11, 0x22, 0x33, 0x44, 0x55, 0x66, 0x77, 0x88])
    enum_resp = Frame(
        address=Address.from_(enum_gw),
        frame_type=Type.ENUMERATION_RESPONSE,
        payload=long_addr,
    )
    rx.frame(enum_resp)

    # 3. Identify response
    ident = Frame(
        address=Address.from_(real_gw),
        frame_type=Type.IDENTIFY_RESPONSE,
        payload=long_addr,
    )
    rx.frame(ident)

    # 4. Version response
    ver = Frame(
        address=Address.from_(real_gw),
        frame_type=Type.VERSION_RESPONSE,
        payload=b"2.0.0",
    )
    rx.frame(ver)

    # 5. End
    end = Frame(
        address=Address.from_(real_gw),
        frame_type=Type.ENUMERATION_END_RESPONSE,
        payload=bytes(),
    )
    rx.frame(end)

    assert rx.counters.enumeration_start_requests == 1
    assert rx.counters.enumeration_responses == 1
    assert rx.counters.identify_responses == 1
    assert rx.counters.version_responses == 1
    assert rx.counters.enumeration_end_responses == 1
    assert len(sink.enumeration_started_events) == 1
    assert len(sink.gateway_identities) == 2  # enumeration + identify
    assert len(sink.gateway_versions) == 1
    assert len(sink.enumeration_ended_events) == 1


# --- Command correlation tests ---

def test_command_request_response_correlation():
    """Test command request/response are correlated via sequence number."""
    sink = MockSink()
    rx = Receiver(sink)

    gw = GatewayID(0x1201)
    seq_num = 0x42
    packet_type_req = 0x0A  # arbitrary
    packet_type_resp = 0x0B

    # Command request: 3 unknown + packet_type + seq_num + payload
    req_frame = Frame(
        address=Address.to(gw),
        frame_type=Type.COMMAND_REQUEST,
        payload=bytes([0x00, 0x00, 0x00, packet_type_req, seq_num]) + b"\x01\x02",
    )
    rx.frame(req_frame)
    assert rx.counters.command_requests == 1

    # Command response: unknown1 + tx_buf_free + unknown2 + packet_type + cmd_seq + payload
    resp_frame = Frame(
        address=Address.from_(gw),
        frame_type=Type.COMMAND_RESPONSE,
        payload=bytes([0x00, 0x01, 0x00, packet_type_resp, seq_num]) + b"\x03\x04",
    )
    rx.frame(resp_frame)
    assert rx.counters.command_responses == 1

    assert len(sink.commands_executed) == 1
    gw_out, req_out, resp_out = sink.commands_executed[0]
    assert gw_out.value == gw.value
    assert req_out == (packet_type_req, b"\x01\x02")
    assert resp_out == (packet_type_resp, b"\x03\x04")


def test_command_response_without_request():
    """Response without prior request is counted as retransmitted."""
    sink = MockSink()
    rx = Receiver(sink)

    frame = Frame(
        address=Address.from_(GatewayID(0x1201)),
        frame_type=Type.COMMAND_RESPONSE,
        payload=bytes([0x00, 0x01, 0x00, 0x0B, 0x42]),
    )
    rx.frame(frame)

    assert rx.counters.retransmitted_command_responses == 1
    assert len(sink.commands_executed) == 0


def test_retransmitted_command_request():
    """Duplicate sequence number counts as retransmitted."""
    sink = MockSink()
    rx = Receiver(sink)

    gw = GatewayID(0x1201)
    frame = Frame(
        address=Address.to(gw),
        frame_type=Type.COMMAND_REQUEST,
        payload=bytes([0x00, 0x00, 0x00, 0x0A, 0x42]),
    )
    rx.frame(frame)
    rx.frame(frame)

    assert rx.counters.command_requests == 1
    assert rx.counters.retransmitted_command_requests == 1


def test_command_request_short_payload():
    """COMMAND_REQUEST with <5 bytes is invalid."""
    sink = MockSink()
    rx = Receiver(sink)

    frame = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.COMMAND_REQUEST,
        payload=bytes([0x00, 0x01]),
    )
    rx.frame(frame)

    assert rx.counters.invalid_command_requests == 1


def test_command_response_wrong_direction():
    """COMMAND_RESPONSE with to-direction is invalid."""
    sink = MockSink()
    rx = Receiver(sink)

    frame = Frame(
        address=Address.to(GatewayID(0x1201)),
        frame_type=Type.COMMAND_RESPONSE,
        payload=bytes([0x00, 0x01, 0x00, 0x0B, 0x42]),
    )
    rx.frame(frame)

    assert rx.counters.invalid_command_responses == 1


# --- Counting-only frame types ---

def test_counting_only_frame_types():
    """Frame types that only increment counters."""
    sink = MockSink()
    rx = Receiver(sink)

    cases = [
        (Type.ENUMERATION_START_RESPONSE, Address.from_(GatewayID(1)), "enumeration_start_responses"),
        (Type.ENUMERATION_REQUEST, Address.to(GatewayID(1)), "enumeration_requests"),
        (Type.ASSIGN_GATEWAY_ID_REQUEST, Address.to(GatewayID(1)), "assign_gateway_id_requests"),
        (Type.ASSIGN_GATEWAY_ID_RESPONSE, Address.from_(GatewayID(1)), "assign_gateway_id_responses"),
        (Type.IDENTIFY_REQUEST, Address.to(GatewayID(1)), "identify_requests"),
        (Type.VERSION_REQUEST, Address.to(GatewayID(1)), "version_requests"),
        (Type.ENUMERATION_END_REQUEST, Address.to(GatewayID(1)), "enumeration_end_requests"),
    ]

    for ft, addr, counter_name in cases:
        frame = Frame(address=addr, frame_type=ft, payload=bytes())
        rx.frame(frame)
        assert getattr(rx.counters, counter_name) == 1, f"Counter {counter_name} should be 1"


def test_unhandled_frame_type():
    """Unknown frame type increments unhandled counter."""
    sink = MockSink()
    rx = Receiver(sink)

    frame = Frame(
        address=Address.to(GatewayID(1)),
        frame_type=0xFFFF,
        payload=bytes(),
    )
    rx.frame(frame)

    assert rx.counters.unhandled_frame_type == 1