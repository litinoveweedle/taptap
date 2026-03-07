# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

### Fixed
- H-firmware (H1.0007) TAP RECEIVE_RESPONSE parsing: removed overly-strict `status_type & 0x00E0`
  validation that rejected 93.7% of responses from H-firmware gateways, silently dropping power
  reports. Bits 5-7 are firmware-dependent flags with no effect on payload structure.
- TCP keepalive `with_retries()` cfg gate now correctly excludes Windows (where API is unavailable)

### Changed
- Updated `docs/protocol.md` to document H-firmware status type format

### Deprecated

### Removed


## [0.2.6] - 2025-11-09

### Changed
- generate infrastructure event independently of the state-file arg


## [0.2.5] - 2025-11-05

### Added

### Fixed
- compatibility with the Tigo FW v4.0.1

### Changed
- compatibility changes to the upstream taptap

### Deprecated
- persistent-file argument replace by state-file argument

### Removed


## [0.2.0] - 2025-10-27

### Added

- infrastructure even in observe mode - to output in JSON gateway and nodes addresses, version and barcodes
- persistent storage for infrastructure data

### Fixed

- invalid NodeTableResponse struct

### Changed

- format of the power report event message - this is breaking change
- Updated README to reflect recent implementation 


## [0.1.2] - 2025-10-24

### Added

- this Changelog.md file
- implementation of reconnect logic for both serial and tcp connections
- implementation of the TCP keepalive probing mechanism

### Fixed

- Rust compilation warnings
- duplication of main.rs code

### Changed

- updated Cargo deps
- cli arguments dependencies and exclusions
- README to reflects new cli arguments


## [0.1.1] - 2025-03-25

### Added

- initial build chain implementation

### Fixed

- fixed cli argument ---port can be used together with ---tcp


