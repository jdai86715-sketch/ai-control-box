# Changelog

All notable changes to this project are documented in this file.

## [0.1.0] - 2026-09-16

### Added

- Local llama.cpp tool-routing backend.
- Tool registry, risk levels, confirmation flow and JSONL audit log.
- Safe file browsing, whitelisted Windows app launching and MQTT device-control foundation.
- Basic automated tests and GitHub Actions test workflow.

### Security

- Model output is restricted to registered tools and checked against application, directory and device allowlists.
- Medium- and high-risk actions require explicit confirmation.
