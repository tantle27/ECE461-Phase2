# RESTler Integration for API Fuzz Testing

This directory contains the configuration and scripts for running RESTler API fuzz tests.

## Overview

RESTler is Microsoft's stateful REST API fuzzing tool that automatically tests REST APIs by generating and executing sequences of requests. It can:
- Discover API vulnerabilities and bugs
- Test for authentication bypasses
- Find resource leaks and crashes
- Validate input handling and edge cases

## Setup Instructions

### Prerequisites
- Python 3.8+
- .NET 6.0 SDK
- Docker (optional, for isolated testing)

### Installation

1. **Install RESTler from GitHub:**
```bash
git clone https://github.com/microsoft/restler-fuzzer.git
cd restler-fuzzer
python ./build-restler.py --dest_dir ./restler_bin
```

2. **Set up environment:**
```bash
# Add RESTler to PATH (Windows)
set PATH=%PATH%;C:\path\to\restler_bin

# Add RESTler to PATH (Linux/Mac)
export PATH=$PATH:/path/to/restler_bin
```

## Usage

### Basic Fuzz Testing
```bash
# Run all fuzz tests
python run_restler_tests.py

# Run specific test suite
python run_restler_tests.py --suite authentication

# Run with custom API endpoint
python run_restler_tests.py --endpoint http://localhost:5000
```

### Integration with CI/CD
```bash
# Run in CI mode (generates reports)
python run_restler_tests.py --ci --output-dir ./restler_reports
```

## Configuration Files

- `restler_config.json` - Main RESTler configuration
- `restler_auth_config.json` - Authentication settings
- `custom_mutations.py` - Custom payload mutations
- `openapi.yaml` - API specification for RESTler

## Test Suites

1. **Authentication Tests** - Test auth bypass, token validation
2. **Input Validation Tests** - Test malformed inputs, boundary conditions  
3. **Resource Management Tests** - Test for resource leaks, DoS
4. **Business Logic Tests** - Test workflow violations, state corruption

## Reports

RESTler generates detailed reports in `./restler_reports/`:
- `bug_buckets/` - Categorized bug reports
- `logs/` - Detailed execution logs
- `network_traces/` - Request/response traces
- `coverage/` - API endpoint coverage

## Coverage Integration

The fuzz tests integrate with pytest-cov to ensure comprehensive testing coverage.
Coverage reports are generated in both XML and HTML formats for CI integration.