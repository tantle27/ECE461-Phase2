#!/usr/bin/env python3
"""
Verify that the Lambda deployment package has all required dependencies.
Run this before deploying to catch packaging issues early.
"""

import sys
import importlib

REQUIRED_MODULES = [
    ("flask", "flask"),
    ("awsgi", None),
    ("boto3", None),
    ("botocore", None),
    ("git", "git"),  # GitPython
    ("huggingface_hub", None),
]

def check_module(package_name, import_name=None):
    """Check if a module can be imported and has expected attributes."""
    actual_import = import_name or package_name
    try:
        mod = importlib.import_module(actual_import)
        print(f"✓ {package_name:30s} - OK")
        
        # Special checks
        if actual_import == "awsgi":
            if hasattr(mod, 'response'):
                print(f"  └─ awsgi.response available")
            else:
                print(f"  └─ ✗ WARNING: awsgi.response NOT FOUND")
                print(f"  └─ Available: {[x for x in dir(mod) if not x.startswith('_')]}")
                return False
        return True
    except ImportError as e:
        print(f"✗ {package_name:30s} - MISSING ({e})")
        return False

def main():
    print("=" * 60)
    print("Lambda Dependency Check")
    print("=" * 60)
    
    all_ok = True
    for pkg_spec in REQUIRED_MODULES:
        if isinstance(pkg_spec, tuple):
            pkg, imp = pkg_spec
        else:
            pkg = imp = pkg_spec
        
        if not check_module(pkg, imp):
            all_ok = False
    
    print("=" * 60)
    if all_ok:
        print("✓ All dependencies OK - safe to deploy")
        return 0
    else:
        print("✗ Some dependencies missing or incomplete")
        print("  Run: pip install -r requirements.txt")
        return 1

if __name__ == "__main__":
    sys.exit(main())
