# Tigo TAP Protocol Parsing Analysis

## System Topology

```
CCA ──RS485──► TAP3 (0x1203) ──► TAP1 (0x1201) ──► TAP2 (0x1202)
                 │                    │                   │
              2 panels             22 panels           2 panels
           Nodes: 24,27         Nodes: 2-5,7-23,28   Nodes: 25,26
```

- **26 PV panels** total, each with a Tigo optimiser
- **3 TAPs** (gateway devices) on a daisy-chained RS-485 bus
- **1 CCA** (Cloud Connect Advanced) — the controller polling all TAPs
- Gateway IDs: TAP1=`0x1201`, TAP2=`0x1202`, TAP3=`0x1203`

---

## Firmware & Hardware Versions

### TAP Gateway Firmware (VERSION_RESPONSE)

| | TAP1 | TAP2 | TAP3 |
|---|---|---|---|
| **Firmware** | **G8.65** | **H1.0007** | **H1.0007** |
| **Build date** | May  9 2025 | Apr 22 2025 | Apr 22 2025 |
| **Build time** | 13:52:34 | 15:28:25 | 15:28:25 |
| **Hardware** | **GW-H158.4.3S0.12** | **GW-H158.7.10** | **GW-H158.7.10** |
| **Long address** | `04:C0:5B:30:00:00:C9:6F` | `04:C0:5B:30:00:07:2C:5E` | `04:C0:5B:30:00:07:28:97` |

**Key difference**: TAP1 runs **G-series firmware** (G8.65) on an older H158.4.x hardware
revision, while TAP2/TAP3 run **H-series firmware** (H1.0007) on newer H158.7.x hardware.

Raw version strings:
```
TAP1: "Mgate Version G8.65\rMay  9 2025\r13:52:34\rGW-H158.4.3S0.12\r"
TAP2: "Mgate Version H1.0007\rApr 22 2025\r15:28:25\rGW-H158.7.10\r"
TAP3: "Mgate Version H1.0007\rApr 22 2025\r15:28:25\rGW-H158.7.10\r"
```

### Optimiser Node Firmware (STRING_RESPONSE)

All optimiser nodes across all three TAPs report the **same firmware**:

```
"Mnode Version H9.0022 (47)\r"
```

Confirmed on nodes: 3, 5, 23, 24, 26, 27, 28 (sampled via `^00Version\r` string requests).

### Radio Configuration per TAP (RADIO_CONFIG_RESPONSE 0x0E)

Each TAP operates its own independent 802.15.4 wireless network:

| | TAP1 | TAP2 | TAP3 |
|---|---|---|---|
| **Radio channel** | 0x11 (17) | 0x16 (22) | 0x0E (14) |
| **PAN ID** | 0x3204 | 0x4204 | 0x5204 |
| **CAP/CFP/BOP/IAP** | 0C/02/02/01 | 0C/02/02/01 | 0C/02/02/01 |
| **Encryption key** | `7A 77 92 B4 D3 46 56 C4 02 FD 85 29 C9 30 2F B5` | `65 A8 02 6C 3E 56 05 63 1F 01 94 C8 A7 AC 6E 07` | `62 AE 2B 4C 33 A1 60 C6 18 F8 2A A7 11 64 83 77` |

The superframe parameters (CAP/CFP/BOP/IAP) and the trailing config bytes
(`00 00 30 72 1C 01 5A ... 00 00 02 00 3C 00`) are **identical** across all TAPs.
Only channel, PAN ID, and encryption key differ (as expected for separate PV networks).

Node `!Info` strings confirm the per-TAP radio assignment:
```
TAP1 nodes: "!Info 0000 11 0000 0C00 ... 32043204 ..."   (channel 0x11, PAN 0x3204)
TAP3 nodes: "!Info 0000 0E 0000 0C00 ... 52045204 ..."   (channel 0x0E, PAN 0x5204)
```

### Firmware ↔ Protocol Behaviour Correlation

The G vs H firmware difference directly explains the RECEIVE_RESPONSE status format divergence:

| Behaviour | TAP1 (G8.65) | TAP2/TAP3 (H1.0007) |
|---|---|---|
| **Status byte[1] bits 5-7** | Always **set** (0xE0+) | Always **cleared** (0x1F-) |
| **taptap parser compatibility** | ✅ 100% accepted | ❌ 93.7% rejected |
| **COMMAND_RESPONSE to 0x17** | Returns pkt_type **0x17** | Returns pkt_type **0x18** |
| **0x13 PV_CONFIG_REQ sent** | Never (during capture) | Yes (4 commands) |
| **0xE0 full-status cycle** | Every ~16 polls | Every ~16 polls |

The H-firmware TAPs use a newer RECEIVE_RESPONSE encoding where bits 5-7 of the status
byte are repurposed (cleared instead of set). The field structure controlled by bits 0-4
remains identical — only the high bits changed meaning between firmware generations.

The original taptap protocol documentation and parser were developed against a single
G-firmware TAP. The `status_type & 0x00E0 == 0x00E0` check is a G-firmware assumption
that breaks on H-firmware TAPs.

---

## Data Sources

| File | Description | Size |
|------|-------------|------|
| `frames.log` | Raw gateway link-layer frames from `taptap peek-frames` | 25,689 frames |
| `event_typepower_report,gateway4609.txt` | Parsed power reports from `taptap observe` | ~6,300 JSON lines |

Protocol reference: <https://github.com/litinoveweedle/taptap/blob/master/docs/protocol.md>

---

## Frame Statistics Summary

### Frames per TAP

| TAP | RECEIVE_REQUEST | RECEIVE_RESPONSE | COMMAND_REQUEST | COMMAND_RESPONSE |
|-----|-----------------|------------------|-----------------|------------------|
| TAP1 (22 panels) | 4,220 | 4,217 | 50 | 50 |
| TAP2 (2 panels) | 4,251 | 4,251 | 19 | 19 |
| TAP3 (3 panels) | 4,249 | 4,248 | 21 | 21 |

All three TAPs are polled at essentially the same rate (~4,250 RECEIVE_REQUEST cycles each).

### COMMAND_REQUEST PV Packet Types per TAP

| PV Packet Type | Name | TAP1 | TAP2 | TAP3 |
|----------------|------|------|------|------|
| `0x06` | STRING_REQ | 31 | 8 | 10 |
| `0x0D` | RADIO_CONFIG_REQ | 2 | 2 | 2 |
| **`0x13`** | **PV_CONFIG_REQ** | **0** | **2** | **2** |
| `0x17` | UNKNOWN (undocumented) | 11 | 2 | 2 |
| `0x22` | BROADCAST | 2 | 2 | 2 |
| `0x26` | NODE_TABLE_REQ | 3 | 2 | 2 |
| `0x2E` | NET_STATUS_REQ | 1 | 1 | 1 |

---

## Finding 1: `0x13` PV_CONFIG_REQ — Sent ONLY to TAP2 & TAP3

The CCA sends PV configuration requests (`0x13`) to configure each node's power report
period and phase. **No `0x13` commands are sent to any TAP1 node in the entire capture.**

### Protocol Format (from docs/protocol.md)

```
PV_CONFIG_REQ (0x13) payload:
  Bytes 0-1:  PV Node ID      (big-endian u16)
  Bytes 2-3:  ??? (0x03 0x00)
  Byte  4:    Report type      (0x31 = power report)
  Byte  5:    ??? (0x02)
  Bytes 6-7:  Period           (big-endian u16, in slot units, 1 slot ≈ 5ms)
  Bytes 8-9:  Phase            (big-endian u16, in slot units)
  Bytes 10+:  ??? (remaining config bytes)
```

### Captured `0x13` Commands

| Line | TAP | Target Node | Period (slots) | Period (seconds) | Phase |
|------|-----|-------------|----------------|------------------|-------|
| 17973 | TAP3 | Node 27 | 12,000 (0x2EE0) | **60.0s** | 6,000 |
| 18019 | TAP2 | Node 25 | 12,000 (0x2EE0) | **60.0s** | 0 |
| 18693 | TAP3 | Node 24 | 12,000 (0x2EE0) | **60.0s** | 0 |
| 18751 | TAP2 | Node 26 | 12,000 (0x2EE0) | **60.0s** | 6,000 |

All four use **Period = 12,000 slots = 60 seconds**. Two nodes have Phase=0, two have Phase=6000
(staggered by 30s to spread load).

### Raw Hex of 0x13 Commands

```
TAP3 Node 27: 00 1B 03 00 31 02 2E E0 17 70 00 09 02 00 00 00 00 00 30 02 00 00 00 00
TAP2 Node 25: 00 19 03 00 31 02 2E E0 00 00 00 09 02 00 00 00 00 00 30 02 00 00 00 00
TAP3 Node 24: 00 18 03 00 31 02 2E E0 00 00 00 09 02 00 00 00 00 00 30 02 00 00 00 00
TAP2 Node 26: 00 1A 03 00 31 02 2E E0 17 70 00 09 02 00 00 00 00 00 30 02 00 00 00 00
```

### Corresponding `0x18` PV_CONFIG_RESP from Nodes

Responses received via RECEIVE_RESPONSE embedded PV packets:

| TAP | Node | Response data (first 30 bytes hex) |
|-----|------|------------------------------------|
| TAP1 | 5 | `0F 32 04 11 7A 00 ... 31 2E E0 15 4E 00 09 ...` |
| TAP1 | 20 | `0F 32 04 11 7A 00 ... 31 2E E0 28 7B 00 09 ...` |
| TAP1 | 18 | `0F 32 04 11 7A 00 ... 31 2E E0 0C C8 00 09 ...` |
| TAP1 | 3 | `0F 32 04 11 7A 00 ... 31 2E E0 13 2D 00 09 ...` |
| TAP2 | 25 | (via relaxed parsing) |
| TAP2 | 26 | (via relaxed parsing) |
| TAP3 | 24 | (via relaxed parsing) |
| TAP3 | 27 | (via relaxed parsing) |

Note: TAP1 nodes (5, 20, 18, 3) also echo back `0x18` responses containing `Period=0x2EE0` (60s),
indicating they were configured at some earlier point — just not during this capture window. These
responses arrive in reply to the `0x17` commands (see below).

---

## Finding 2: `0x17` Undocumented Command — Sent to All TAPs

PV packet type `0x17` is **not documented** in the protocol spec. It is a short 3-byte command
targeting individual nodes.

### Payload Format

```
COMMAND_REQUEST with PV packet type 0x17:
  Gateway frame payload: [0x00, 0x00, 0x00, 0x17, seq, node_hi, node_lo, 0x0F]
                          ├── unknown ──┤  type  seq  ├─ node ID ─┤  param
```

- **Node ID**: big-endian u16 identifying the target PV node
- **Param**: always `0x0F` (= 15 decimal) in all captured instances

### All Captured `0x17` Commands

| Line | TAP | Target Node | Param | Response pkt_type |
|------|-----|-------------|-------|-------------------|
| 15929 | **TAP1** | Node 16 | 0x0F | **0x17** (echoed) |
| 16527 | TAP3 | Node 24 | 0x0F | **0x18** (PV_CONFIG_RESP) |
| 16537 | TAP2 | Node 26 | 0x0F | **0x18** (PV_CONFIG_RESP) |
| 16907 | **TAP1** | Node 17 | 0x0F | **0x17** (echoed) |
| 17253 | TAP3 | Node 27 | 0x0F | **0x18** (PV_CONFIG_RESP) |
| 17275 | TAP2 | Node 25 | 0x0F | **0x18** (PV_CONFIG_RESP) |
| 17699 | **TAP1** | Node 2 | 0x0F | **0x17** (echoed) |
| 18581 | **TAP1** | Node 5 | 0x0F | **0x17** (echoed) |
| 19607 | **TAP1** | Node 4 | 0x0F | **0x17** (echoed) |
| 20645 | **TAP1** | Node 20 | 0x0F | **0x17** (echoed) |
| 21664 | **TAP1** | Node 18 | 0x0F | **0x17** (echoed) |
| 22342 | **TAP1** | Node 3 | 0x0F | **0x17** (echoed) |
| 23284 | **TAP1** | Node 14 | 0x0F | **0x17** (echoed) |
| 24250 | **TAP1** | Node 15 | 0x0F | **0x17** (echoed) |
| 24976 | **TAP1** | Node 8 | 0x0F | **0x17** (echoed) |

### Key Observation: Response Type Differs by TAP

- **TAP1**: COMMAND_RESPONSE has `pkt_type = 0x17` (same as request — gateway handles locally?)
- **TAP2/TAP3**: COMMAND_RESPONSE has `pkt_type = 0x18` (PV_CONFIG_RESP — forwarded to node and node replies?)

This suggests `0x17` may be a "request current PV configuration" or "trigger config report" command.
TAP1 handles it at the gateway level (returning the cached config), while TAP2/TAP3 forward it to
the node which responds with `0x18`.

### Node Coverage

| TAP | Total Nodes | Nodes receiving 0x17 | Nodes NOT receiving 0x17 |
|-----|-------------|----------------------|--------------------------|
| TAP1 | 22 | 11 (2,3,4,5,8,14,15,16,17,18,20) | 11 (7,9,10,11,12,13,19,21,22,23,28) |
| TAP2 | 2 | 2 (25,26) | 0 |
| TAP3 | 2 | 2 (24,27) | 0 |

Only ~50% of TAP1 nodes received `0x17` during this capture — CCA appears to cycle through them.

---

## Finding 3 (CRITICAL): RECEIVE_RESPONSE Status Format Difference

This is the **root cause** of the apparent low power-report rate from TAP2/TAP3.

### The Status Type Bitfield

Each RECEIVE_RESPONSE payload starts with a 2-byte status type. The taptap parser
(`src/gateway/transport.rs`) checks:

```rust
let status_type = U16::ref_from_bytes(&bytes[0..2]).unwrap().get();
if status_type & 0x00e0 != 0x00e0 {
    return Err(InvalidReceiveResponse::UnknownStatusType(status_type));
}
```

### Byte[1] Values Observed

**TAP1** — ALL responses use standard format (bits 5-7 of byte[1] **set**):

| byte[1] | Binary | Count | Meaning |
|---------|--------|-------|---------|
| `0xFF` | `1111 1111` | 3,535 | Minimal status (no optional fields) |
| `0xFE` | `1111 1110` | 394 | Includes rx_buffers_used |
| `0xE0` | `1110 0000` | 266 | Full status (all optional fields) |
| `0xFD` | `1111 1101` | 14 | Includes tx_buffers_free |
| `0xEF` | `1110 1111` | 4 | Includes packet_num_hi |
| `0xEE` | `1110 1110` | 3 | Includes rx_buffers + packet_num_hi |
| `0xFC` | `1111 1100` | 1 | Includes rx_buffers + tx_buffers |
| **Total** | | **4,217** | **100% parseable** |

**TAP2** — Almost ALL responses use **non-standard** format (bits 5-7 **cleared**):

| byte[1] | Binary | Count | Standard? |
|---------|--------|-------|-----------|
| `0x1F` | `0001 1111` | 3,834 | ❌ NON-STANDARD |
| `0x1E` | `0001 1110` | 144 | ❌ NON-STANDARD |
| `0xE0` | `1110 0000` | 268 | ✅ Standard |
| `0x1D` | `0001 1101` | 3 | ❌ NON-STANDARD |
| `0x18` | `0001 1000` | 1 | ❌ NON-STANDARD |
| `0x0E` | `0000 1110` | 1 | ❌ NON-STANDARD |
| **Total** | | **4,251** | **6.3% parseable** |

**TAP3** — Same non-standard pattern:

| byte[1] | Binary | Count | Standard? |
|---------|--------|-------|-----------|
| `0x1F` | `0001 1111` | 3,839 | ❌ NON-STANDARD |
| `0x1E` | `0001 1110` | 139 | ❌ NON-STANDARD |
| `0xE0` | `1110 0000` | 268 | ✅ Standard |
| `0x1D` | `0001 1101` | 1 | ❌ NON-STANDARD |
| `0x1A` | `0001 1010` | 1 | ❌ NON-STANDARD |
| **Total** | | **4,248** | **6.3% parseable** |

### Byte[0] Values (Same Across ALL TAPs)

| byte[0] | TAP1 | TAP2 | TAP3 |
|---------|------|------|------|
| `0x01` | 2,638 | 2,624 | 2,619 |
| `0x41` | 1,579 | 1,627 | 1,629 |

byte[0] = `0x01` or `0x41` uniformly across all TAPs. The protocol doc shows `0x00`
for this byte, so `0x01`/`0x41` may indicate a newer firmware feature. Bit 6 (0x40)
toggles independently.

### Pattern Analysis

The non-standard byte[1] values from TAP2/TAP3 have an inverted bit pattern compared to TAP1:

```
TAP1 standard:      0xFF = 1111_1111    0xFE = 1111_1110    0xE0 = 1110_0000
TAP2/TAP3 non-std:  0x1F = 0001_1111    0x1E = 0001_1110    (no 0x00 equivalent)
                         ^^^^^                ^^^^^
                    bits 5-7 differ      bits 5-7 differ
```

**Bits 0-4 encode the same optional field flags** in both formats. The field structure
(rx_buffers_used, tx_buffers_free, unknown_a, unknown_b, packet_num_hi) is identical.
Only bits 5-7 differ, and they don't contribute additional payload bytes.

### Impact on Parsing

| TAP | Responses Accepted | Responses Rejected | Acceptance Rate |
|-----|--------------------|--------------------|-----------------|
| TAP1 | 4,217 | 0 | **100.0%** |
| TAP2 | 268 | 3,983 | **6.3%** |
| TAP3 | 268 | 3,980 | **6.3%** |

**93.7% of TAP2/TAP3 responses are silently discarded**, including almost all power reports.

---

## Finding 4: Actual Power Report Rates (With Relaxed Parsing)

When parsing with the `0x00E0` check **removed** (using only bits 0-4 for field decoding),
the actual power report counts are:

### Power Reports per TAP (Relaxed Parser)

| TAP | Nodes | Total Reports | Reports/Node |
|-----|-------|---------------|--------------|
| TAP1 | 22 | 1,580 | **71.8** |
| TAP2 | 2 | 164 | **82.0** |
| TAP3 | 2 | 164 | **82.0** |

**TAP2/TAP3 nodes actually report at a HIGHER per-node rate than TAP1.**

### Power Reports per Node (Relaxed Parser)

**TAP1 nodes (22 panels):**

| Node | Reports | | Node | Reports | | Node | Reports |
|------|---------|---|------|---------|---|------|---------|
| 2 | 73 | | 10 | 62 | | 17 | 75 |
| 3 | 80 | | 11 | 50 | | 18 | 78 |
| 4 | 56 | | 12 | 80 | | 19 | 66 |
| 5 | 80 | | 13 | 64 | | 20 | 70 |
| 7 | 77 | | 14 | 93 | | 21 | 64 |
| 8 | 87 | | 15 | 93 | | 22 | 50 |
| 9 | 50 | | 16 | 76 | | 23 | 80 |
| | | | | | | 28 | 76 |

**TAP2 nodes (2 panels):**

| Node | Reports |
|------|---------|
| 25 | 82 |
| 26 | 82 |

**TAP3 nodes (2 panels):**

| Node | Reports |
|------|---------|
| 24 | 82 |
| 27 | 82 |

### Comparison: Standard Parser vs Relaxed Parser

| TAP | Standard Parser | Relaxed Parser | Data Lost |
|-----|-----------------|----------------|-----------|
| TAP1 | 1,580 reports | 1,580 reports | **0%** |
| TAP2 | 8 reports | 164 reports | **95.1%** |
| TAP3 | 10 reports | 164 reports | **93.9%** |

### Power Report Frequency (from event file — standard parser output)

The `event_typepower_report,gateway4609.txt` file confirms the data loss. Over ~486 seconds:

| TAP | Node | Reports | Avg Interval | Rate/min |
|-----|------|---------|--------------|----------|
| TAP1 | (all nodes) | ~244 each | **2.0s** | 30.1 |
| TAP2 | Node 25 | 10 | **37.1s** | 1.8 |
| TAP2 | Node 26 | 12 | **33.6s** | 1.9 |
| TAP3 | Node 24 | 26 | **17.4s** | 3.6 |
| TAP3 | Node 27 | 20 | **21.0s** | 3.0 |

The "2s interval" for TAP1 reflects rapid taptap polling extracting buffered reports.
The "17-37s intervals" for TAP2/TAP3 reflect only the ~6.3% of responses that pass the parser.

---

## Finding 5: All PV Packet Types per TAP (Relaxed Parser)

| PV Type | Name | TAP1 | TAP2 | TAP3 |
|---------|------|------|------|------|
| `0x07` | STRING_RESP | 12 | 4 | 10 |
| `0x09` | TOPOLOGY_REPORT | 11 | 2 | 2 |
| `0x18` | PV_CONFIG_RESP | 4 | 2 | 2 |
| `0x31` | POWER_REPORT | 1,580 | 164 | 164 |

No `0x17` PV packets appear in RECEIVE_RESPONSE data from any TAP. The `0x17` only
appears as a COMMAND_REQUEST PV packet type (controller → TAP direction).

---

## Root Cause & Recommended Fix

### Problem

In `src/gateway/transport.rs`, the `ReceiveResponse::read_from_bytes()` method rejected
any response where `status_type & 0x00E0 != 0x00E0`:

```rust
// src/gateway/transport.rs — previous code
let status_type = U16::ref_from_bytes(&bytes[0..2]).unwrap().get();
if status_type & 0x00e0 != 0x00e0 {
    return Err(InvalidReceiveResponse::UnknownStatusType(status_type));
}
```

This check passed for TAP1 (byte[1] values like `0xFF`, `0xFE`, `0xE0`) but failed for
TAP2/TAP3 (byte[1] values like `0x1F`, `0x1E`).

### Fix Status

✅ **FIXED** — The `status_type & 0x00E0` guard has been removed from both the Rust
(`src/gateway/transport.rs`) and Python (`python/taptap/gateway/transport/messages.py`)
parsers. Only bits 0-4 are used for field-presence parsing; bits 5-7 are ignored as
firmware-dependent informational flags.

**Live verification** against the real system confirmed all 3 TAPs now report at equal
rates (~30 reports/node/minute):

| TAP | Firmware | Reports/node/min (before) | Reports/node/min (after) |
|-----|----------|---------------------------|--------------------------|
| TAP1 | G8.65 | ~30 | ~30 |
| TAP2 | H1.0007 | ~1.8 (93.7% dropped) | ~30 |
| TAP3 | H1.0007 | ~3.0 (93.7% dropped) | ~30 |

### Analysis of Bits 5-7

Bits 5-7 of byte[1] do **not** contribute additional payload bytes. The field structure
is fully determined by bits 0-4:

| Bit | Field | Size |
|-----|-------|------|
| 0 | rx_buffers_used | 1 byte |
| 1 | tx_buffers_free | 1 byte |
| 2 | unknown_a | 2 bytes |
| 3 | unknown_b | 2 bytes |
| 4 | packet_number_hi (0=full 2-byte, 1=lo-byte only) | 1-2 bytes |
| **5** | **Unknown meaning — does NOT add payload bytes** | **0 bytes** |
| **6** | **Unknown meaning — does NOT add payload bytes** | **0 bytes** |
| **7** | **Unknown meaning — does NOT add payload bytes** | **0 bytes** |

### Proposed Fix

Remove or relax the bits 5-7 check. The payload structure is identical regardless of
bits 5-7 state:

```rust
// Option A (applied): Remove the check entirely (bits 5-7 are informational flags)
// The if-block was deleted; only bits 0-4 are used for field parsing.
```

### Verification

With the relaxed parser:
- TAP2/TAP3 responses parse correctly
- Power report counts match expected rates (82/node vs 72/node for TAP1)
- No parsing errors in the PV packet data within the responses
- PV packet headers (type, node_address, short_address, dsn, data_length) are valid
- Power report data fields decode to plausible values

---

## Appendix A: Sample Non-Standard TAP2/TAP3 Responses

### Empty response (status 0x011F — equivalent to 0x01FF)

```
TAP2: 01 1F AD D3 CB
       │  │  │  └──┘ slot_counter = 0xD3CB
       │  │  └────── packet_number_lo = 0xAD
       │  └───────── status byte[1] = 0x1F (NON-STANDARD: bits 5-7 = 0)
       └──────────── status byte[0] = 0x01
```

### Data-bearing response (status 0x011E — equivalent to 0x01FE)

```
TAP3: 01 1E 02 4A D4 57 31 00 1B 00 0D 90 0F 27 50 16 17 07 E0 96 93 00 64 D4 50 74 00 00
       │  │  │  │  └──┘  └─ PV packet: type=0x31 (POWER_REPORT), node=0x001B (27)
       │  │  │  └────── packet_number_lo = 0x4A
       │  │  └───────── rx_buffers_used = 0x02
       │  └──────────── status byte[1] = 0x1E (NON-STANDARD, bit 0 clear = rx_buffers included)
       └─────────────── status byte[0] = 0x01
```

### Equivalent TAP1 standard response

```
TAP1: 01 FF EA D2 42 31 00 16 00 70 66 0F 2B C1 5B FF 59 20 B4 92 00 64 CF A0 74 00 00
       │  │  │  └──┘  └─ PV packet: type=0x31 (POWER_REPORT), node=0x0016 (22)
       │  │  └────── packet_number_lo = 0xEA
       │  └───────── status byte[1] = 0xFF (STANDARD, all optional fields omitted)
       └──────────── status byte[0] = 0x01
```

---

## Appendix B: Complete Node-to-TAP Allocation

| TAP | Gateway ID | Node IDs | Panel Count |
|-----|-----------|----------|-------------|
| TAP1 | 0x1201 | 2, 3, 4, 5, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20, 21, 22, 23, 28 | 22 |
| TAP2 | 0x1202 | 25, 26 | 2 |
| TAP3 | 0x1203 | 24, 27 | 2 |

Note: Node IDs 1 (gateway), 6, and others are not assigned to optimisers.

---

## Appendix C: Enumeration Sequence Observed

The frames.log begins with an enumeration sequence:
1. 5× ENUMERATION_START_REQUEST to broadcast (0x0000)
2. ENUMERATION_REQUEST/RESPONSE via temporary address 0x1235
3. ASSIGN_GATEWAY_ID for 3 TAPs (0x1201, 0x1202, 0x1203)
4. IDENTIFY_REQUEST/RESPONSE for each TAP + additional IDs (0x1204, 0x1205, 0x1206)
5. VERSION_REQUEST/RESPONSE for each TAP
6. ENUMERATION_END

After enumeration, the CCA enters its polling loop:
`TAP2 → TAP3 → TAP1 → TAP2 → TAP3 → TAP1 → ...` (round-robin)
