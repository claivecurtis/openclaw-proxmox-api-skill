# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Phase 2 Implementation**: Advanced VM and Container features
  - VM operations: clone, snapshots (create/list/rollback/delete), migrate, resize, move_volume, template, VNC/SPICE proxies, monitor commands, firewall rules
  - Container class for LXC operations with all VM features supported
  - All operations work for both QEMU VMs and LXC containers

### Changed
- Updated `load_client()` to use `OPENCLAW_WORKSPACE` environment variable with fallback to relative path from script directory, making secrets paths generic for any OpenClaw install.