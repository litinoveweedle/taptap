# Tigo CCA ↔ TAP Protocol — Reverse Engineering Notes

> **Living document** — updated as new message types and data points are identified.
> Source: live capture from CCA at 192.168.2.94:4196 + frames.log analysis.

---

## System Under Test

```
CCA (192.168.2.94:4196)
  └─ RS-485 bus (38400 baud 8N1)
      ├─ TAP3  0x1203  "Mgate Version H1.0007"  GW-H158.7.10  (3 nodes: 24, 27)
      ├─ TAP1  0x1201  "Mgate Version G8.65"    GW-H158.4.3S0.12  (22 nodes)
      └─ TAP2  0x1202  "Mgate Version H1.0007"  GW-H158.7.10  (2 nodes: 25, 26)
```

All optimisers: `Mnode Version H9.0022 (47)`

---

## 1. Gateway Link Layer — Frame Types

### Known Frame Types

| Type (hex) | Name | Direction | Status |
|------------|------|-----------|--------|
| `0x0148` | RECEIVE_REQUEST | CCA→TAP | ✅ Fully documented |
| `0x0149` | RECEIVE_RESPONSE | TAP→CCA | ⚠️ H-firmware status bits differ |
| `0x0B0F` | COMMAND_REQUEST | CCA→TAP | ✅ Fully documented |
| `0x0B10` | COMMAND_RESPONSE | TAP→CCA | ✅ Fully documented |
| `0x0B00` | PING_REQUEST | CCA→TAP | ✅ Documented |
| `0x0B01` | PING_RESPONSE | TAP→CCA | ✅ Documented |
| `0x0014` | ENUMERATION_START_REQUEST | CCA→broadcast | ✅ Documented |
| `0x0015` | ENUMERATION_START_RESPONSE | TAP→broadcast | ✅ Documented |
| `0x0038` | ENUMERATION_REQUEST | CCA→enum addr | ✅ Documented |
| `0x0039` | ENUMERATION_RESPONSE | TAP→enum addr | ✅ Documented |
| `0x003C` | ASSIGN_GATEWAY_ID_REQUEST | CCA→TAP | ✅ Documented |
| `0x003D` | ASSIGN_GATEWAY_ID_RESPONSE | TAP→CCA | ✅ Documented |
| `0x003A` | IDENTIFY_REQUEST | CCA→TAP | ✅ Documented |
| `0x003B` | IDENTIFY_RESPONSE | TAP→CCA | ✅ Documented |
| `0x000A` | VERSION_REQUEST | CCA→TAP | ✅ Documented |
| `0x000B` | VERSION_RESPONSE | TAP→CCA | ✅ Documented |
| `0x0E02` | ENUMERATION_END_REQUEST | CCA→TAP | ✅ Documented |
| `0x0006` | ENUMERATION_END_RESPONSE | TAP→CCA | ✅ Documented |
| `0x0010` | UNKNOWN_0010 | CCA→broadcast | ❓ Sent during enumeration |
| `0x0011` | UNKNOWN_0011 | TAP→broadcast | ❓ Response to 0x0010 |

---

## 2. RECEIVE_RESPONSE Status Byte — H-Firmware Difference

### Status word format: `byte[0] byte[1]`

**Bits 0-4 of byte[1]** — field presence flags (0=included, 1=omitted):

| Bit | Field | Size when present |
|-----|-------|-------------------|
| 0 | rx_buffers_used | 1 byte |
| 1 | tx_buffers_free | 1 byte |
| 2 | unknown_a | 2 bytes |
| 3 | unknown_b | 2 bytes |
| 4 | packet_number mode | 0=full 2-byte, 1=lo-byte only |

Always followed by: `slot_counter` (2 bytes), then zero or more PV packets.

**Bits 5-7 of byte[1]** — firmware-dependent:

| Firmware | Bits 5-7 | Example byte[1] values |
|----------|----------|------------------------|
| G8.65 (TAP1) | Always **set** (= 0xE0 mask) | `0xFF, 0xFE, 0xE0` |
| H1.0007 (TAP2/3) | Always **cleared** | `0x1F, 0x1E, 0x1D` |

**byte[0] values** — observed across all TAPs:

| Value | Meaning | Notes |
|-------|---------|-------|
| `0x01` | Normal response | ~62% of responses |
| `0x41` | Normal response (alt) | ~38% of responses, bit 6 set |

> **TODO**: Determine meaning of byte[0] bit 6 (0x40). Toggles for all TAPs equally.
> Could be: retransmit flag, alternate buffer, epoch indicator?

### unknown_a and unknown_b Fields

Present when bits 2 and 3 are clear (in 0xE0/full-status responses, every ~16 polls).

| Field | Size | Observed values | Hypothesis |
|-------|------|-----------------|------------|
| unknown_a | 2 bytes | `00 01`, varies | Possibly Tx-related counter |
| unknown_b | 2 bytes | `02 00`, varies | Possibly link quality metric |

> **TODO**: Correlate with node count, packet loss, or timing.

---

## 3. PV Application Layer — Packet Types

### Known Packet Types

| Type | Name | Direction | Parsing | Notes |
|------|------|-----------|---------|-------|
| `0x06` | STRING_REQUEST | CCA→node | ✅ | ASCII command with `\r` terminator |
| `0x07` | STRING_RESPONSE | node→CCA | ✅ | ASCII response |
| `0x09` | TOPOLOGY_REPORT | node→CCA | ✅ | Mesh routing info |
| `0x0D` | GATEWAY_RADIO_CONFIG_REQ | CCA→gateway | ✅ | Request radio params |
| `0x0E` | GATEWAY_RADIO_CONFIG_RESP | gateway→CCA | ✅ | Channel, PAN ID, encryption key |
| `0x13` | PV_CONFIGURATION_REQUEST | CCA→node | ✅ | Sets report period & phase |
| `0x17` | **UNKNOWN — see §4** | CCA→node | ❓ | **Undocumented** |
| `0x18` | PV_CONFIGURATION_RESPONSE | node→CCA | ✅ | Echoes config + radio params |
| `0x22` | BROADCAST | CCA→all | ✅ | PV on/off signal |
| `0x23` | BROADCAST_ACK | gateway→CCA | ✅ | Gateway acknowledgement |
| `0x26` | NODE_TABLE_REQUEST | CCA→gateway | ✅ | Request node ID ↔ address map |
| `0x27` | NODE_TABLE_RESPONSE | gateway→CCA | ✅ | Node table entries |
| `0x2D` | LONG_NETWORK_STATUS_REQ | CCA→gateway | ⚠️ | Alternate/legacy status request |
| `0x2E` | NETWORK_STATUS_REQUEST | CCA→gateway | ⚠️ | Request mesh node count |
| `0x2F` | NETWORK_STATUS_RESPONSE | gateway→CCA | ⚠️ | Node counts (3× u16) |
| `0x31` | POWER_REPORT | node→CCA | ✅ | Core monitoring data |
| `0x41` | UNKNOWN_0x41 | CCA→node/gw | ❓ | **Undocumented** — see §5 |

---

## 4. Packet Type 0x17 — "PV Configuration Query"

**Observed in**: COMMAND_REQUEST (CCA → TAP → node)

### Format

```
COMMAND_REQUEST payload:
  [0:3]  unknown: 00 00 00
  [3]    packet_type: 0x17
  [4]    sequence_number
  [5:7]  node_id: big-endian u16
  [7]    parameter: always 0x0F observed
```

### Behaviour

| TAP firmware | COMMAND_RESPONSE pkt_type | Node responds via RECEIVE_RESPONSE? |
|-------------|--------------------------|-------------------------------------|
| G8.65 (TAP1) | `0x17` (echoed) | Yes — later returns `0x18` PV_CONFIG_RESP |
| H1.0007 (TAP2/3) | `0x18` (PV_CONFIG_RESP) | Yes — same `0x18` |

### Hypothesis

`0x17` is a **PV configuration query/poll** that requests the node's current
configuration. The node responds with `0x18` (PV_CONFIGURATION_RESPONSE) containing
current radio settings + report period/phase.

- The `0x0F` parameter may be a "report all config" flag.
- G-firmware echoes `0x17` as the immediate command response type (gateway handles locally),
  while H-firmware returns `0x18` (perhaps the gateway forwards and proxies the node reply).
- Both firmware versions eventually produce a `0x18` PV packet from the node.

### All captured instances (from frames.log)

| TAP | Node | Line | Response type |
|-----|------|------|---------------|
| TAP1 | 16, 17, 2, 5, 4, 20, 18, 3, 14, 15, 8 | various | 0x17 |
| TAP2 | 26, 25 | 16537, 17275 | 0x18 |
| TAP3 | 24, 27 | 16527, 17253 | 0x18 |

> **TODO**: Capture more instances live. Determine if parameter can be values other than 0x0F.
> Check if response data (beyond the 5-byte header) contains any information.

---

## 5. Packet Type 0x41 — Unknown

**Observed in**: COMMAND_REQUEST (CCA → gateway and nodes)

### Format (from protocol.md)

```
  [0:2]  ???: 00 00
  [2:4]  PV node ID: big-endian u16 (00 01 = gateway, 00 02+ = node)
  [4:]   ???: 00 AA 00 00 00 00 04 05 0F E8 08 95 09 FD 8F F6 05 C7
```

### Timing

Per the protocol documentation:
- Sent to the gateway overnight when no nodes are online
- Sent to the first few nodes at sunrise
- Sent to the last few nodes at sunset

No responses have been observed (packets are unacknowledged).

> **TODO**: Capture live instances. Full payload analysis needed.

---

## 6. COMMAND_REQUEST Unknown Fields

The first 3 bytes of every COMMAND_REQUEST payload are marked "unknown":

```
payload: [unknown[0], unknown[1], unknown[2], packet_type, sequence_number, ...]
```

Observed values: always `00 00 00` in all captures.

> **TODO**: Verify with longer captures. Could be priority, flags, or padding.

---

## 7. RECEIVE_REQUEST Unknown Fields

```
payload: [unknown_1[0], unknown_1[1], packet_number[0], packet_number[1], unknown_2]
```

| Field | Observed values | Hypothesis |
|-------|-----------------|------------|
| unknown_1 | `00 01` | Always the same; possibly protocol version or buffer ID |
| unknown_2 | `04` | Always the same; possibly request flags or max packets |

> **TODO**: Verify with longer captures.

---

## 8. Power Report Format

### Standard 13-byte format (PV packet type 0x31)

```
Offset  Size  Field             Encoding
0       1.5   voltage_in        12-bit, × 0.05V
1.5     1.5   voltage_out       12-bit, × 0.10V
3       1     dc_dc_duty_cycle  u8 / 255.0
4       1.5   current_in        12-bit, × 0.005A
5.5     1.5   temperature       12-bit, × 0.1°C
7       3     unknown           3 bytes — purpose unclear
10      2     slot_counter      Timing reference for measurement
12      1     RSSI              Radio signal strength
```

### Extended 15-byte format

Same as above with 2 additional bytes appended. Seen as `PowerReport15` in source.

> **TODO**: Determine meaning of the 3 "unknown" bytes at offset 7-9.
> Could be: energy accumulator, fault flags, or optimiser state.

---

## 9. PV Configuration (0x13 / 0x18) Detail

### 0x13 Request payload (24 bytes)

```
Offset  Size  Field         Observed values
0       2     node_id       Target node (big-endian u16)
2       2     ???           03 00
4       1     report_type   0x31 (power report)
5       1     ???           02
6       2     period        Slot count (e.g., 0x2EE0 = 12000 = 60s)
8       2     phase         Slot offset for this node
10      14    ???           00 09 02 00 00 00 00 00 30 02 00 00 00 00
```

### 0x18 Response payload (~40 bytes)

```
Offset  Size  Field          Notes
0       1     ???            0x0F
1       2     PAN_ID         802.15.4 PAN identifier
3       1     channel        Radio channel
4       2     ???            Varies
6       varies  alternate?   Repeat of radio config (backup?)
...     2     ???            03 00
...     1     ???            30/31
...     2     period         Echoed from request
...     2     phase          Echoed from request
...     varies ???           Remaining config
```

> **TODO**: Full field-by-field decode of 0x18 response. Live capture needed.

---

## 10. Network Status (0x2E / 0x2D / 0x2F) Detail

### 0x2E Request — no payload (sent to gateway node 0x0001)

### 0x2F Response (11 bytes)

```
Offset  Size  Field          Observed
0       2     PV node ID     00 01 (gateway)
2       1     ???            01
3       2     counter?       Incrementing value
5       2     node_count_a   Total mesh nodes
7       2     node_count_b   Total mesh nodes (usually same as a)
9       2     node_count_c   Total mesh nodes (usually same as a)
```

### 0x2D Long Request (8 bytes)

```
Offset  Size  Field
0       3     ???            BA BE 02 (magic?)
3       2     counter?
5       2     node_count?
7       1     ???            01
```

> **TODO**: Capture 0x2D/0x2E/0x2F live and track counter progression.

---

## 11. Topology Report (0x09)

```
Offset  Size  Field
0       2     short_address    802.15.4 short address
2       2     PV_node_id
4       2     next_hop_node    Routing: which node relays to gateway
6       2     ???              00 02 observed
8       8     long_address     802.15.4 EUI-64
16      1     RSSI
17      6     ???              Possibly link metrics, age, or counters
```

> **TODO**: Track topology changes live. Decode the trailing 6 unknown bytes.

---

## 12. String Commands (0x06 / 0x07)

### Known String Commands

| Command | Response prefix | Description |
|---------|----------------|-------------|
| `^00Info\r` | `!Info ...` | Device info: channel, node count, PAN ID |
| `^00Version\r` | `Mnode Version ...` | Firmware version |
| `^00Tests\r` | `!Tests ...` | Self-test results |
| `^00Smrt\r` | `!Smrt ...` | Smart/MPPT configuration |
| `^00Mppt_1.1\r` | (none) | MPPT command (no response observed) |
| `#00w255\r` | (none) | Unknown write command |

### !Info Response Format

```
!Info AAAA BB CCCC DDDD EEE FFFF GGGG HH II JJJJ KKKK LLL MMMMNNNN OOOO\r
```

| Field | Example | Notes |
|-------|---------|-------|
| AAAA | 0000 | Unknown |
| BB | 11 / 0E | Radio channel (hex) — matches TAP assignment |
| CCCC | 0000 | Unknown |
| DDDD | 0C00 | Unknown (3072 decimal) |
| EEE | 32B | Unknown (counter? node-specific) |
| FFFF | 0000 | Unknown |
| GGGG | 0000 | Unknown |
| HH | FF | Unknown (always FF) |
| II | 00 | Unknown |
| JJJJ | 0000 | Unknown |
| KKKK | 0000 | Unknown |
| LLL | 000 | Unknown |
| MMMMNNNN | 32043204 / 52045204 | PAN ID (repeated) — matches TAP radio config |
| OOOO | 0000 | Unknown |

> **TODO**: Decode remaining !Info fields. Correlate EEE with node behaviour.

---

## 13. Radio Configuration (0x0D / 0x0E)

### 0x0E Response (per TAP)

```
Offset  Size  Field              TAP1        TAP2        TAP3
0       1     ???                00          00          00
1       1     channel            0x11 (17)   0x16 (22)   0x0E (14)
2       2     PAN_ID             0x3204      0x4204      0x5204
4       1     CAP                0x0C        0x0C        0x0C
5       1     CFP                0x02        0x02        0x02
6       1     BOP                0x02        0x02        0x02
7       1     IAP                0x01        0x01        0x01
8       7     ???                00 00 30 72 1C 01 5A    (same for all)
15      16    encryption_key     (unique per TAP)
31      6     ???                00 00 02 00 3C 00       (same for all)
```

CAP/CFP/BOP/IAP likely define 802.15.4 superframe slot allocation.
Trailing `00 3C` = 60 decimal, possibly epoch duration in seconds.

---

## 14. Live Capture Log

_Observations from live capture sessions will be appended below._

