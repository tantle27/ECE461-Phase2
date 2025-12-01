# Simple ADA Testing Framework

## Overview
This is a simplified accessibility testing framework for ADA compliance using WCAG 2.1 AA standards. It provides basic automated tests for keyboard navigation, color contrast, and general accessibility.

## Quick Start

### 1. Install Dependencies
```bash
pip install selenium webdriver-manager pytest
```

### 2. Run Tests
```bash
# Run all simplified ADA tests
python simple_ada_runner.py --url http://localhost:5000

# Run specific test types
python simple_ada_runner.py --type keyboard --url http://localhost:5000
python simple_ada_runner.py --type contrast --url http://localhost:5000
python simple_ada_runner.py --type accessibility --url http://localhost:5000

# Using pytest directly
pytest tests/ada/test_simple_keyboard.py -v
pytest tests/ada/test_simple_contrast.py -v
pytest tests/ada/test_simple_accessibility.py -v
```

## Test Files

### Simple Keyboard Tests (`test_simple_keyboard.py`)
- **Tab Navigation**: Basic tab key navigation through focusable elements
- **Enter/Space Activation**: Tests keyboard activation of buttons and links
- **Focus Visibility**: Ensures focused elements are visible

### Simple Contrast Tests (`test_simple_contrast.py`)
- **Text Contrast**: Tests 4.5:1 contrast ratio for text elements
- **Button Contrast**: Tests contrast for button elements
- **Link Contrast**: Tests contrast for link elements

### Simple Accessibility Tests (`test_simple_accessibility.py`)
- **Alt Text**: Verifies images have alt text
- **Form Labels**: Ensures form inputs have labels
- **Heading Structure**: Basic heading hierarchy check
- **Button Names**: Verifies buttons have accessible names
- **Link Text**: Checks for meaningful link text

## Framework Structure

```
tests/ada/
├── __init__.py                     # Package initialization
├── ada_utils.py                    # Simple utilities
├── test_simple_keyboard.py         # Keyboard tests
├── test_simple_contrast.py         # Contrast tests
├── test_simple_accessibility.py    # General accessibility tests
└── README.md                       # This file
```

## Simple Usage Examples

### Basic Test Execution
```powershell
# Test your local application
python simple_ada_runner.py --url http://localhost:3000

# Test specific accessibility aspect
python simple_ada_runner.py --type keyboard --url http://localhost:3000
```

### Integration with CI/CD
```yaml
# GitHub Actions example
- name: Run ADA Tests
  run: |
    python simple_ada_runner.py --url http://localhost:5000
```

## Utilities

### SimpleContrastChecker
- `rgb_to_luminance(r, g, b)`: Calculate luminance
- `contrast_ratio(color1, color2)`: Calculate contrast ratio
- `parse_color(color_str)`: Parse color strings

### SimpleKeyboardTester
- `get_focusable_elements()`: Find focusable elements
- `press_tab()`: Simulate Tab key
- `press_enter()`: Simulate Enter key
- `press_space()`: Simulate Space key

## Configuration
Set environment variable `ADA_TEST_URL` to specify the URL to test (default: http://localhost:5000).

## Standards
Tests basic compliance with:
- WCAG 2.1 Level AA
- Keyboard accessibility
- Color contrast (4.5:1 ratio)
- Basic semantic HTML
