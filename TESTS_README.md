# 🧪 Test Suite Documentation

**ECE461 Phase 2 - Trustworthy Model Registry**  
**Total Tests: 190** | **Coverage: 42%** | **Status: ✅ All Passing**

---

## 📊 **Test Suite Overview**

This repository contains a comprehensive test suite covering both **Phase 1** (CLI-based model evaluation) and **Phase 2** (REST API model registry) functionality.

```
├── Phase 1 Tests: 137 tests (Original CLI system)
│   ├── API Layer: 46 tests (External integrations)
│   ├── Metrics Layer: 91 tests (Algorithm precision)
│   └── Application Layer: 0 tests (CLI removed)
└── Phase 2 Tests: 53 tests (New REST API scaffolding)
    ├── Backend Services: 16 tests
    ├── New Metrics: 15 tests
    └── API Endpoints: 22 tests
```

---

## 🎯 **Quick Start**

```bash
# Run all tests
python -m pytest

# Run with coverage (includes both src/ and app/ directories)
python -m pytest --cov=src --cov=app

# Run specific test categories
python -m pytest -m "unit"          # Unit tests only
python -m pytest -m "integration"   # Integration tests only
python -m pytest -m "api"           # API tests only
python -m pytest -m "backend"       # Backend tests only
python -m pytest -m "slow"          # Performance tests only

# Run Phase 1 vs Phase 2 tests
python -m pytest tests/api/ tests/metrics/ tests/test_main.py  # Phase 1
python -m pytest tests/test_*.py --ignore=tests/test_main.py   # Phase 2
```

---

## 🏗️ **Phase 1 Tests (144 tests) - CLI Model Evaluation**

### 🌐 **API Layer Tests (46 tests)**

#### `test_gen_ai_client.py` - **21 tests** 🤖
**Purpose**: Tests AI integration with Purdue's GenAI API for performance analysis

- **Basic Communication (4 tests)**
  - ✅ Successful API calls and responses
  - ⚠️ Error handling (400, 401, authentication failures)
  - 🔧 Custom model selection and API configuration

- **Performance Claims Analysis (8 tests)**
  - 📊 Extracts benchmark metrics from README files
  - 📝 Handles markdown code blocks and JSON parsing
  - 🔄 Fallback strategies for malformed responses
  - 🛡️ Edge case handling (nested braces, invalid JSON)

- **README Clarity Analysis (9 tests)**
  - 📖 AI-powered documentation quality scoring
  - 🔢 Numerical score extraction and validation
  - 🎯 Perfect scores (1.0) and zero scores (0.0)
  - 🤪 AI misbehavior and "LLM disobedience" handling

#### `test_git_client.py` - **12 tests** 📁
**Purpose**: Tests Git repository operations with REAL repositories

- **Repository Management (3 tests)**
  - 🏗️ Creates actual Git repositories for testing
  - 🧹 Cleanup and temporary directory management
  - ❌ Error handling for invalid repository URLs

- **Commit Analysis (5 tests)**
  - 👥 Analyzes commit history and contributor patterns
  - 📈 Handles empty repos and single-author scenarios
  - 🔍 Multi-contributor analysis and bus factor calculation

- **Code Quality Analysis (3 tests)**
  - 🐍 Python code quality metrics and linting
  - 📦 Handles repositories without Python files
  - 🛡️ Error handling for inaccessible files

- **Repository Size Analysis (2 tests)**
  - 📏 Calculates repository size for hardware compatibility
  - ⚡ Performance optimization for large repositories

#### `test_git_client_coverage.py` - **7 tests** 🛡️
**Purpose**: Extended edge case testing for Git operations

- **Error Conditions & Edge Cases**
  - 🚫 Non-existent repository handling
  - 💥 Corrupted repository recovery
  - 📄 Missing README file scenarios
  - 🔒 File permission and access errors
  - 📁 Empty directory and cleanup edge cases

#### `test_hugging_face_client.py` - **6 tests** 🤗
**Purpose**: Tests HuggingFace API integration for dataset metrics

- **Mathematical Normalization (3 tests)**
  - 📊 Logarithmic scaling for popularity metrics
  - 0️⃣ Zero value handling and boundary conditions
  - 📈 Maximum value capping and normalization

- **Dataset Information (2 tests)**
  - ❤️ Fetches dataset likes and download counts
  - 🔍 Handles missing metadata gracefully

- **File Operations (1 test)**
  - 📥 HuggingFace file download functionality

### 🎯 **Metrics Layer Tests (91 tests)**

#### `test_license_metric.py` - **20 tests** ⚖️
**Purpose**: License detection and compatibility scoring

- **License Type Recognition (5 tests)**
  - ✅ Permissive licenses (MIT, Apache, BSD) → Score: 1.0
  - ⚠️ Weak copyleft (LGPL) → Score: 0.5
  - 🔒 Strong copyleft (GPL, AGPL) → Score: 0.1
  - ❌ No license → Score: 0.0

- **Text Processing & Edge Cases (8 tests)**
  - 🔍 Case-insensitive license detection
  - 🇬🇧 British spelling ("Licence" vs "License")
  - 📝 Multiple license sections and formats
  - 📄 Missing README or empty license sections

- **Integration & Validation (7 tests)**
  - 🔗 End-to-end Git client integration
  - ✔️ Input validation and type checking
  - 🧪 Real-world license format testing

#### `test_dataset_code_metric.py` - **17 tests** 🗂️
**Purpose**: ML repository completeness analysis

- **Core ML Assessment (4 tests)**
  - 🏆 Dataset + Training Code → Score: 1.0
  - 📊 Only dataset information → Score: 0.5
  - 💻 Only training code → Score: 0.5
  - ❌ Neither present → Score: 0.0

- **File Pattern Recognition (6 tests)**
  - 🏃 Training scripts (train.py, finetune.py, etc.)
  - 🌐 Dataset URLs (Kaggle, HuggingFace, academic)
  - 📁 Data files (.csv, .json, .parquet)
  - 📓 Jupyter notebook analysis (.ipynb)
  - 📂 Data directory detection (/data/, /datasets/)

- **Configuration & Metadata (3 tests)**
  - ⚙️ config.json dataset references
  - 🏷️ Repository type classification (model/dataset/training)
  - 🔗 Enhanced dataset source detection

- **Edge Cases (4 tests)**
  - 📭 Empty repository handling
  - 📄 Missing README scenarios
  - 🛡️ Malformed configuration handling

#### `test_ramp_up_time_metric.py` - **15 tests** 📚
**Purpose**: Learning curve and getting-started assessment

- **Scoring Components (5 tests)**
  - 🏆 Perfect score: Documentation + Examples + Dependencies
  - ❌ Zero score: No helpful materials
  - ⚖️ Partial scores: Weighted combination
  - 📖 Documentation-only scenarios
  - 🛠️ Technical-only scenarios (examples + deps)

- **Algorithm Validation (3 tests)**
  - 🧮 Weight constants sum to 100%
  - ⚖️ Proper weight distribution
  - 🔢 Boundary value testing

- **Error Handling (5 tests)**
  - 📊 Missing data handling
  - 🧩 Incomplete information scenarios
  - 🛡️ Input validation and type checking
  - 🚫 Null input handling

- **Exception Recovery (2 tests)**
  - 🤖 AI client failure recovery
  - 📁 Git client failure handling

#### `test_size_metric.py` - **10 tests** 💾
**Purpose**: Hardware compatibility assessment

- **Hardware Compatibility Tiers (4 tests)**
  - 🍓 Raspberry Pi compatible (< 100MB)
  - 🚀 Jetson Nano compatible (< 1GB)
  - 🖥️ Desktop PC compatible (< 10GB)
  - ☁️ AWS Server only (unlimited)

- **Edge Cases & Errors (6 tests)**
  - 📭 Empty repository handling
  - 🚫 Null response scenarios
  - 🔢 Invalid size data
  - 🧩 Missing size information
  - 0️⃣ Zero-size edge cases
  - ⚠️ Git client error recovery

#### Other Metric Tests (45 tests)

- **`test_bus_factor_metric.py`** (7 tests) 👥
  - Uses Herfindahl-Hirschman Index for contributor diversity
  - Perfect distribution → 0.8, Single author → 0.0

- **`test_code_quality_metric.py`** (9 tests) 🔧
  - Lint errors, test presence, code complexity analysis
  - Scoring based on error count and test coverage

- **`test_dataset_quality_metric.py`** (4 tests) 📈
  - HuggingFace popularity metrics with logarithmic scaling
  - Missing metadata and API failure handling

- **`test_performance_claims_metric.py`** (5 tests) 🏆
  - AI-powered benchmark extraction from documentation
  - JSON parsing and performance metric validation

- **`test_metric.py`** (2 tests) 🏗️
  - Abstract base class functionality
  - Input/output contract validation

- **`test_metrics_calculator.py`** (2 tests) 🎼
  - End-to-end metric calculation pipeline
  - Success and failure path integration testing

### 🖥️ **Application Layer Tests (7 tests)**

#### `test_main.py` - **6 tests** 🎯
**Purpose**: Command-line interface and orchestration

- **URL File Processing (2 tests)**
  - 📄 Parse URL files with new format (GitHub, HuggingFace, datasets)
  - ❌ File not found error handling

- **Async Processing (2 tests)**
  - ⚡ Async entry processing with NDJSON output
  - 🔗 Integration with metrics calculator

- **CLI Interface (2 tests)**
  - 🎛️ Command-line argument validation
  - 🔧 Main function orchestration with file input

#### `test_parallelism.py` - **1 test** 🚀
**Purpose**: Performance validation

- **Concurrency Requirements**
  - ⚡ Ensures concurrent processing is 1.5x faster than sequential
  - 📊 Real performance measurement with timing
  - 🎯 Validates Phase 1 performance goals

---

## 🆕 **Phase 2 Tests (53 tests) - REST API Scaffolding**

### 🏗️ **Backend Services**

#### `test_backend.py` - **16 tests** 🔧
**Purpose**: Core backend service testing infrastructure

- **Model Registry (3 tests)**
  - 📦 Model upload structure validation
  - 🏷️ Metadata validation and processing
  - 🔗 Scoring system integration

- **Database Operations (3 tests)**
  - 🗄️ Database connection mocking
  - 📝 CRUD operations for models and users
  - 👤 User management and authentication

- **File Operations (2 tests)**
  - 📤 File upload validation and processing
  - ☁️ AWS S3 integration testing

- **Authentication & Authorization (3 tests)**
  - 🔐 JWT token generation and validation
  - 🛡️ Permission and access control
  - 🚦 Rate limiting functionality

- **API Endpoints (3 tests)**
  - ❤️ Health check endpoints
  - 🔍 Model search functionality
  - 📥 Model ingestion from HuggingFace

- **Performance (2 tests)**
  - ⚡ Concurrent upload handling
  - 📊 Database query performance

#### `test_new_metrics.py` - **15 tests** 📊
**Purpose**: Phase 2 enhanced metrics

- **Reproducibility Metric (4 tests)**
  - ✅ Working demo code execution → Score: 1.0
  - 🔧 Partial working code (needs debugging) → Score: 0.5
  - ❌ No demo code available → Score: 0.0
  - 📖 Model card code extraction and testing

- **Reviewedness Metric (4 tests)**
  - 📈 High PR review coverage (85%) → Score: 0.85
  - 📉 No pull requests → Score: -1.0
  - 🚫 No GitHub repository → Score: -1.0
  - 🏆 Perfect review coverage → Score: 1.0

- **Treescore Metric (4 tests)**
  - 👨‍👩‍👧‍👦 Parent model dependency scoring
  - 🚫 No parent models → Score: 0.0
  - 👤 Single parent model inheritance
  - 🧩 Missing parent score handling

- **Integration Tests (3 tests)**
  - 🔗 All metrics working together
  - ⏱️ Latency tracking for new metrics
  - 🎯 Enhanced net score calculation

#### `test_api_endpoints.py` - **22 tests** 🌐
**Purpose**: REST API endpoint scaffolding

- **Model Registry API (5 tests)**
  - 📤 Model upload with metadata
  - ❌ Invalid data handling
  - 🔍 Model retrieval by ID
  - 🔎 Search with query parameters
  - ✏️ Model metadata updates
  - 🗑️ Model deletion

- **Package Registry API (3 tests)**
  - 📦 Package upload functionality
  - 📊 Package metrics retrieval
  - 🔍 Regex-based package search

- **Authentication API (5 tests)**
  - 📝 User registration
  - 🔐 Login and token management
  - ❌ Invalid credential handling
  - 🔄 Token refresh functionality
  - 🚪 User logout

- **Error Handling (4 tests)**
  - 🚦 Rate limiting (429 errors)
  - 💥 Server error handling (500 errors)
  - ✅ Input validation (422 errors)
  - 🔍 Not found errors (404)

- **Performance Testing (5 tests)**
  - ⚡ Concurrent model uploads
  - 📊 Large search result handling
  - ⏱️ Long-running metrics calculations
  - 🎯 Load testing scenarios

---

## 📈 **Test Coverage Analysis**

### Current Coverage: **42%** (868 missed / 1503 total lines)

**Includes both `src/` and `app/` directories**

#### High Coverage Areas ✅
- **Core Metrics Logic**: 55-86% (Well-tested algorithms)
- **Performance Claims**: 100% (AI integration working)
- **Size Metrics**: 100% (Hardware compatibility)
- **License Detection**: 97% (Strong foundation)

#### Medium Coverage Areas ⚠️
- **Git Client**: 70% (Core functionality covered)
- **GenAI Client**: 71% (Main features tested)
- **Metrics Calculator**: 56% (Integration paths)

#### Zero Coverage Areas ❌
- **Flask App Core**: 0% (app/core.py - 775 lines, 18 endpoints)
- **Flask App Setup**: 0% (app/app.py - application factory)
- **Flask Scoring**: 0% (app/scoring.py - metrics integration)
- **GitHub Fetchers**: 0% (Unused module)
- **Legacy Metrics**: 0% (Deprecated code)

### Coverage Improvement Strategy 🎯

1. **Flask App Testing**: Add tests for 18 REST API endpoints (775 lines untested)
2. **Integration Testing**: Test Flask + Phase 1 metrics integration
3. **Error Path Testing**: Add negative test cases for API endpoints
4. **Authentication Testing**: Test JWT tokens and permissions
5. **Database Testing**: Add tests for model/user persistence
6. **Performance Testing**: API response time validation

---

## 🛠️ **Test Configuration**

### pytest Configuration (`pyproject.toml`)
```toml
[tool.pytest.ini_options]
addopts = "-q --cov=src --cov=app --cov-report=term-missing"
asyncio_mode = "auto"  # Automatic async test support
markers = [
    "unit: Unit tests",
    "integration: Integration tests", 
    "api: API tests",
    "backend: Backend tests",
    "slow: Slow-running tests",
    "security: Security-related tests"
]
```

### Test Dependencies
- **pytest**: Test framework
- **pytest-asyncio**: Async test support
- **pytest-cov**: Coverage reporting
- **unittest.mock**: Mocking framework

### Shared Fixtures (`conftest.py`)
- **Mock API Clients**: Git, GenAI, HuggingFace
- **Database Fixtures**: Mock database and S3
- **Authentication**: Mock tokens and sessions
- **Validation Helpers**: Data validation utilities

---

## 🚀 **Development Workflow**

### Running Tests During Development

```bash
# Quick feedback loop
python -m pytest tests/test_backend.py -v --no-cov

# Test specific functionality
python -m pytest -k "test_license" -v

# Watch mode (requires pytest-watch)
ptw tests/ src/

# Performance benchmarking
python -m pytest -m "slow" -v
```

### Test-Driven Development (TDD)

1. **Write failing test** for new feature
2. **Implement minimal code** to pass
3. **Refactor** while keeping tests green
4. **Add integration tests** for complete flows

### Continuous Integration

The test suite is designed for CI/CD with:
- **Fast feedback**: Core tests run in < 5 seconds
- **Parallel execution**: Tests can run concurrently
- **Clear reporting**: Detailed failure information
- **Coverage tracking**: Automatic coverage reports

---

## 🎯 **Next Steps for Phase 2**

### Immediate Priorities
1. **Flask App Structure** - Implement the missing `app/` directory
2. **Database Schema** - Design models for registry, users, metrics
3. **API Implementation** - Build REST endpoints matching test scaffolding
4. **New Metrics** - Implement Reproducibility, Reviewedness, Treescore

### Test Integration Goals
- **Increase Coverage**: Target 60%+ overall coverage
- **Performance Validation**: Ensure API response times < 200ms
- **Security Testing**: Add authentication and authorization tests
- **Load Testing**: Validate concurrent user scenarios

---

## 📚 **Additional Resources**

- **Phase 1 Specification**: Original CLI tool requirements
- **Phase 2 Specification**: REST API and registry requirements  
- **API Documentation**: OpenAPI/Swagger specs (coming soon)
- **Deployment Guide**: AWS infrastructure setup
- **Contributing Guide**: Development standards and practices

---

**Last Updated**: October 20, 2025  
**Test Suite Version**: Phase 2 Scaffolding v1.0  
**Maintainer**: ECE461 Team