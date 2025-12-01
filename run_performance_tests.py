#!/usr/bin/env python3
"""
Simple script to run optimized load tests and generate performance graphs
Usage: python run_performance_tests.py
"""

import subprocess
import sys
import os
from pathlib import Path

def start_flask_server():
    """Start the Flask server in the background."""
    print("🚀 Starting Flask server...")
    try:
        # Start Flask server
        server_process = subprocess.Popen(
            [sys.executable, "-m", "flask", "run", "--host=0.0.0.0", "--port=5000"],
            cwd=Path.cwd(),
            env={**os.environ, "FLASK_APP": "app.app"},
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        return server_process
    except Exception as e:
        print(f"❌ Failed to start Flask server: {e}")
        return None

def run_load_tests():
    """Run the optimized load tests."""
    print("📊 Running optimized load tests...")
    try:
        result = subprocess.run(
            [sys.executable, "load_test_optimized.py"],
            cwd=Path.cwd(),
            capture_output=True,
            text=True
        )
        
        if result.returncode == 0:
            print("✅ Load tests completed successfully!")
            print(result.stdout)
        else:
            print("❌ Load tests failed!")
            print("STDOUT:", result.stdout)
            print("STDERR:", result.stderr)
            
        return result.returncode == 0
        
    except Exception as e:
        print(f"❌ Error running load tests: {e}")
        return False

def main():
    """Main execution function."""
    print("🎯 ECE461-Phase2 Optimized Performance Testing")
    print("=" * 50)
    
    # Step 1: Start Flask server
    server_process = start_flask_server()
    if not server_process:
        print("❌ Cannot proceed without Flask server")
        return 1
    
    try:
        # Wait a moment for server to start
        import time
        time.sleep(3)
        
        # Step 2: Run load tests
        success = run_load_tests()
        
        if success:
            print("\n🎉 Performance testing completed!")
            print("📊 Check the 'performance_graphs' directory for visualizations")
            print("📋 Check 'performance_results.json' for detailed metrics")
            return 0
        else:
            print("\n❌ Performance testing failed")
            return 1
            
    finally:
        # Cleanup: Stop Flask server
        print("\n🛑 Stopping Flask server...")
        server_process.terminate()
        try:
            server_process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_process.kill()

if __name__ == "__main__":
    sys.exit(main())