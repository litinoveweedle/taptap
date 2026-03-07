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
| **`0x0E03`** | **ENUMERATION_END_RESPONSE_2** | TAP→CCA | 🆕 All TAPs send after enum end. 13-byte payload `00×10 01 03`. Possibly the real enum_end_response. |
| **`0x000E`** | **CHANNEL_QUERY_REQUEST** | CCA→TAP | 🆕 H-firmware only. Empty payload. |
| **`0x000F`** | **CHANNEL_QUERY_RESPONSE** | TAP→CCA | 🆕 H-firmware only. 2 bytes: `20 {channel}`. |
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

**byte[0]** — **super-epoch counter** (CONFIRMED via live capture):

All TAPs (both G and H firmware) exhibit identical byte[0] behaviour. The value
cycles through `0x01 → 0x41 → 0x81 → 0xC1 → 0x01 → ...` synchronized to the
slot counter's epoch transitions:

| byte[0] | Binary | Bits 7:6 | Transitions at |
|---------|--------|----------|----------------|
| `0x01` | `00_000001` | 0 | Slot counter epoch 3→0 wrap |
| `0x41` | `01_000001` | 1 | Next epoch 3→0 wrap |
| `0x81` | `10_000001` | 2 | Next epoch 3→0 wrap |
| `0xC1` | `11_000001` | 3 | Next epoch 3→0 wrap |

**Bits 7:6** = 2-bit counter that increments each time the slot counter completes
a full cycle of 4 epochs (0→1→2→3→0). Since each epoch ≈ 60 seconds, the
super-epoch cycle is ~240 seconds, and the full byte[0] cycle wraps every
~960 seconds (~16 minutes).

**Bit 0** = always 1. Purpose unknown — possibly "data valid" flag.

**Bits 1-5** = always 0 in all observations.

Verified by live capture: tracking byte[0] transitions on TAP1, TAP2, TAP3
simultaneously shows all three TAPs transition at the same time (within ~2 seconds,
matching their slot counter skew).

### unknown_a and unknown_b Fields

Present when bits 2 and 3 are clear (in 0xE0/full-status responses, every ~16 polls).

| Field | Size | Observed values | Status |
|-------|------|-----------------|--------|
| unknown_a | 2 bytes | Always `00 01` | **Constant** — verified across all TAPs over extended captures |
| unknown_b | 2 bytes | Always `02 00` | **Constant** — verified across all TAPs over extended captures |

**tx_buffers_free**: Consistently `14` (0x0E) across all TAPs. This is likely the total
Tx buffer capacity when no commands are pending.

**rx_buffers_used**: Ranges 0-4, averaging ~0.4 for TAP1 (22 nodes) and ~0.0 for
TAP2/TAP3 (2-3 nodes). Correlates with node count — more nodes = more queued
PV packets between polls.

> These fields appear to be static configuration values, not dynamic counters.
> unknown_a may be a protocol version indicator, unknown_b a buffer configuration.
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
| **`0x14`** | **PV_CONFIGURATION_ACK** | gateway→CCA | 🆕 | H-firmware gateway ack for 0x13 |
| `0x17` | **PV_CONFIG_QUERY** | CCA→node | 🆕 Decoded | Requests current config — see §4 |
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

## 7. RECEIVE_REQUEST Fields

```
payload: [unknown_1[0], unknown_1[1], packet_number[0], packet_number[1], unknown_2]
```

| Field | Observed values | Status |
|-------|-----------------|--------|
| unknown_1 | Always `00 01` | **Constant** — matches unknown_a in RECEIVE_RESPONSE. Likely protocol version. |
| unknown_2 | Always `0x04` | **Constant** — possibly max PV packets per response or buffer hint. |

Verified constant across all 3 TAPs over thousands of polls in live capture.

---

## 8. Power Report Format

### Extended 15-byte format (PV packet type 0x31)

**All 26 nodes** in this system transmit the **15-byte extended format** (not the 13-byte
standard). The 15-byte `PowerReport15` format is now the de facto standard.

```
Offset  Size   Field             Encoding
0       1.5    voltage_in        12-bit U12, × 0.05V
1.5     1.5    voltage_out       12-bit U12, × 0.10V
3       1      dc_dc_duty_cycle  u8 / 255.0 (1.0 = 100%)
4       1.5    current_in        12-bit U12, × 0.005A
5.5     1.5    temperature       12-bit U12, × 0.1°C
7       1      power_low         Slowly incrementing value — see below
8       1      always_zero       Always 0x00
9       1      percentage        Always 0x64 (= 100 decimal)
10      2      slot_counter      BE u16 — measurement timestamp ref
12      1      RSSI              Radio signal strength indicator
13      2      extra             See below
```

### Unknown bytes at offset 7-9

| Byte | Observed | Analysis |
|------|----------|----------|
| **byte[7]** | 0x92-0x94 (TAP1 nodes), 0x11 (TAP2), 0x93 (TAP3) | Slowly incrementing per-node value. May be an energy accumulator low byte or operational hour counter. Differs between captures taken hours apart. |
| **byte[8]** | Always `0x00` | Constant across all nodes and captures |
| **byte[9]** | Always `0x64` (100) | Likely a percentage (100% = healthy/normal). Could be module efficiency or health score. |

### Extended bytes (offset 13-14)

| Source | Extra bytes | Notes |
|--------|-------------|-------|
| Live capture (daytime, generating) | `03 00` | All 26 nodes, consistent |
| frames.log (early morning, low generation) | `00 00` | All nodes, consistent |

The extra bytes change between captures at different times of day. `03 00` during
active generation, `00 00` during low/no generation. Hypothesis: **operating mode
or state flags**.

Possible encoding: byte[13] = mode (0x00=idle, 0x03=active generation), byte[14] = reserved.

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

### Session 1 — 2026-03-07 ~12:05-12:15 UTC (daytime, active generation)

**Connection**: TCP 192.168.2.94:4196

**Duration**: ~10 minutes, ~46,000 frames captured

**Observations**:
- Steady-state daytime operation: only RECEIVE_REQUEST/RESPONSE polling
- No COMMAND_REQUEST, no enumeration, no ping — pure polling loop
- Polling order: TAP2 → TAP3 → TAP1 → TAP2 → ... (round-robin)
- All TAPs polled at identical rate: ~26 polls/second each
- No unknown frame types or PV packet types observed during daytime

**Discoveries**:
1. **byte[0] is a super-epoch counter** — bits 7:6 increment at each slot counter
   full-cycle boundary (epoch 3→0). Cycle: 0x01→0x41→0x81→0xC1. All TAPs synchronized.
2. **unknown_a** = always `00 01`, **unknown_b** = always `02 00` (constant)
3. **tx_buffers_free** = always 14 (no commands pending during polling)
4. **All power reports are 15-byte** extended format
5. **Extra bytes** = `03 00` during active generation (was `00 00` in morning log)
6. **byte[9] of power report** = always `0x64` (100) — possible health/efficiency score

### Session 2 — 2026-03-07 13:28 UTC (CCA reboot, daytime)

**Trigger**: CCA manually rebooted to force control message sequences.

**Duration**: ~5 minutes capturing the full initialization sequence.

#### New Frame Types Discovered

| Frame type | Direction | Payload | Context |
|-----------|-----------|---------|---------|
| **`0x0E03`** | TAP→CCA | `00 00 00 00 00 00 00 00 00 00 00 01 03` | Sent by all 3 TAPs immediately after ENUMERATION_END. Identical payload. Possibly "ready" or "reset complete" signal. Note: `0x0E02` = ENUM_END_REQ, so `0x0E03` is likely the true ENUM_END_RESPONSE (not `0x0006`). |
| **`0x000E`** | CCA→TAP | (empty) | Sent only to TAP2 & TAP3 (H-firmware). Not sent to TAP1 (G-firmware). |
| **`0x000F`** | TAP→CCA | 2 bytes | Response to `0x000E`. TAP2: `20 16`, TAP3: `20 0E`. byte[1] = radio channel! (0x16=22, 0x0E=14). |

**`0x000E`/`0x000F`**: This is an **H-firmware-only channel query**. The CCA queries
H-firmware TAPs for their radio channel via this dedicated frame type, while G-firmware
TAPs get their channel via the standard radio config command (0x0D/0x0E).

#### CCA Boot Sequence (complete order)

```
1. Enumeration: start → response → assign IDs → identify → version → end
2. 0x0E03 response from ALL TAPs (13 bytes, all zeros + 01 03)
3. 0x000E/0x000F channel query (H-firmware TAPs only)
4. PING all TAPs
5. RADIO_CONFIG_REQ (0x0D) to each TAP — twice (data=00 00, then 00 01)
6. PING all TAPs again
7. BROADCAST (0x22) data=00 00 to all TAPs (PV off assert)
8. NET_STATUS_REQ (0x2E) to TAP1, TAP2
9. NODE_TABLE_REQ (0x26) to TAP1, TAP2 (page 1)
10. NET_STATUS_REQ (0x2E) to TAP3
11. NODE_TABLE_REQ (0x26) to TAP3 (page 1)
12. BROADCAST (0x22) data=00 01 to all TAPs (PV on)
13. NODE_TABLE_REQ (0x26) to all TAPs (page 2 → end)
14. Per-node discovery cycle begins:
    For each node in each TAP:
      a. STRING_REQ "^00Version\r"
      b. 0x17 config query (param=0x0F)
      c. STRING_REQ "^00Info\r"
      d. STRING_REQ "^00Smrt\r"
      e. STRING_REQ "^00Mppt\r" (some nodes)
      f. STRING_REQ "^00Smrt_........S0000...0000\r" (write Smrt config)
      g. PV_CONFIG_REQ (0x13) — only to TAP2/TAP3 nodes
    → Nodes respond with TOPOLOGY_REPORT as they join
    → 0x17 triggers PV_CONFIG_RESP (0x18) from nodes
```

#### PV_CONFIG_REQ (0x13) → Response Type `0x14` (NEW!)

A new response type was discovered: `0x14`. When CCA sends `0x13` (PV_CONFIG_REQ)
to H-firmware TAPs, the COMMAND_RESPONSE has `pkt_type = 0x14` (not `0x18`):

| TAP firmware | 0x13 sent? | COMMAND_RESPONSE pkt_type | Node 0x18 via RECEIVE_RESPONSE? |
|-------------|-----------|--------------------------|--------------------------------|
| G (TAP1) | No | N/A | N/A |
| H (TAP2/3) | Yes | **0x14** (NEW) | Yes (later) |

`0x14` is the **gateway-level acknowledgement** of a PV config request on H-firmware.
The actual node response (`0x18`) arrives later via the RECEIVE_RESPONSE PV packet stream.

#### PV_CONFIG_RESP (0x18) Detail — TAP Comparison

**TAP1 (G-firmware) nodes — configured with period=0x2EE0 (60s):**
```
Node  2: 0F 32 04 11 7A 00 32 04 11 7A 00 03 00 30 ... 31 2E E0 00 00 00 09
Node  3: 0F 32 04 11 7A 00 32 04 11 7A 00 03 00 30 ... 31 2E E0 13 2D 00 09
         │  └─PAN──┘ └CH┘ └─?─┘ └PAN──┘ └CH┘ │        └type└period─┘ └phase┘
         │  0x3204    0x11  7A    0x3204   0x11│          0x31  12000
         0F                                   00 03 00 30 ...
```

**TAP2 (H-firmware) node 26 — NOT YET configured (0x13 not received before 0x17):**
```
Node 26: 0F 42 04 16 65 00 42 04 16 65 00 03 00 00 00 00 FF FF 00 31 00 00 FF FF
         │  └─PAN──┘ └CH┘ └─?─┘ └PAN──┘ └CH┘ │        └type└period─┘ └phase┘
         │  0x4204    0x16  65    0x4204   0x16│          0x31  0x0000   0xFFFF
         0F                                   00 03 00 00 ...
```

Key difference: **unconfigured H-firmware nodes report period=0x0000 and phase=0xFFFF**
(vs the expected 0x2EE0 / specific phase). The CCA then sends `0x13` to set the correct
values.

**TAP3 (H-firmware) node 24 — configured (0x13 received):**
```
Node 24: 0F 52 04 0E 62 00 52 04 0E 62 00 03 00 30 ... 31 2E E0 11 94 00 09
         │  └─PAN──┘ └CH┘         └PAN──┘ └CH┘           └type└period─┘ └phase┘
         │  0x5204    0x0E                                 0x31  12000    4500
```

#### 0x18 Response Full Decode

```
Offset  Size  Field              TAP1 example        Unconfigured (TAP2)
0       1     ???                0x0F                0x0F
1       2     PAN_ID             0x3204              0x4204
3       1     channel            0x11                0x16
4       2     ???                0x7A 0x00           0x65 0x00
6       2     PAN_ID (backup?)   0x3204              0x4204
8       1     channel (backup?)  0x11                0x16
9       2     ???                0x7A 0x00           0x65 0x00
11      1     ???                0x03                0x03
12      1     ???                0x00                0x00
13      1     config_flag        0x30                0x00        ← differs!
14      8     ???                varies              00 00 FF FF
22      1     report_type        0x31                0x31
23      2     period             0x2EE0 (60s)        0x0000 (not set)
25      2     phase              varies              0xFFFF (not set)
27      2     ???                0x00 0x09           0x00 0x00
... (repeat for backup config)
```

`config_flag` at offset 13: `0x30` = configured, `0x00` = unconfigured.

#### Node Firmware Variants

Most nodes report `H9.0022 (47)`, but some differ:

| Firmware | Nodes |
|----------|-------|
| `Mnode Version H9.0022 (47)` | 2, 3, 5, 10, 11, 12, 13, 16, 18, 21, 23, 24, 27 |
| `Mnode Version H9.0022 (41)` | **7, 8, 9** |

The `(41)` vs `(47)` suffix likely indicates a hardware revision or build variant.

#### Topology Report Decode (0x09) — with next-hop routing

```
Offset  Size  Field           Example (Node 18)
0       2     short_address   0x0003
2       2     PV_node_id      0x0012 (18)
4       2     next_hop        0x0002 (node 2)     ← mesh routing!
6       2     ???             0x0002
8       8     long_address    04:C0:5B:40:00:D3:9A:58
16      1     RSSI            0x4B (75)
17      1     ???             0x02
18      2     ???             0x1D 0x15
20      2     ???             0x00 0x17
22      1     ???             0x28
```

Interesting routing observations from topology reports:
- Nodes 2, 3, 11, 21, 23, 28 → next_hop = `00 01` (direct to gateway)
- Nodes 5, 10 → next_hop = `00 18` (via node 24)
- Nodes 15, 22 → multi-hop chains
- **TAP2/TAP3 nodes** (24, 26, 27) → all direct to gateway (next_hop = `00 01`)

#### Broadcast Commands

| Sequence | Data | Meaning |
|----------|------|---------|
| First (seq 7-9) | `00 00` | PV OFF — sent to all TAPs during init |
| Second (seq 16-18) | `00 01` | PV ON — sent to all TAPs after node table loaded |

Confirms the protocol doc: byte[1] is the PV on/off flag (0=off, 1=on).
BCAST_ACK response data = `02` (same for all TAPs).

#### Network Status Response Detail

| TAP | Response hex | Node count |
|-----|-------------|------------|
| TAP1 | `00 00 00 00 00 00 18 00 18 00` | 0x18 = **24** nodes |
| TAP2 | `00 00 00 00 00 00 02 00 02 00` | 0x02 = **2** nodes |
| TAP3 | `00 00 00 00 00 00 02 00 02 00` | 0x02 = **2** nodes |

Note: TAP1 reports 24 nodes (includes gateway + 22 optimisers + 1 extra?).
The first 6 bytes are all zeros at boot time (counters not yet started).

### Pending observations

- [ ] 0x41 packets (overnight only)
- [ ] 0x2D long network status (overnight only)
- [ ] Frame type 0x0010/0x0011 (seen in frames.log enumeration but not in this reboot)
- [ ] Power report extra bytes transition (`03 00` → `00 00`) at sunset


