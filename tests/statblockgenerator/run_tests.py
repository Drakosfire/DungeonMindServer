#!/usr/bin/env python3
"""
Test runner for StatBlock Generator with OpenAI Structured Outputs
Automatically loads environment variables and provides easy test execution
"""

import os
import sys
import subprocess
from pathlib import Path
from dotenv import load_dotenv


def load_environment():
    """Load environment variables from available env files"""
    # Get the DungeonMindServer root directory
    server_root = Path(__file__).parent.parent.parent
    
    env_loaded = False
    env_file_used = None
    
    # Try to load environment variables in order of preference
    env_files = [
        server_root / ".env.development",
        server_root / ".env.production", 
        server_root / "env.development",
        server_root / "env.production",
        server_root / ".env"
    ]
    
    for env_file in env_files:
        if env_file.exists():
            load_dotenv(env_file)
            env_loaded = True
            env_file_used = env_file
            break
    
    return env_loaded, env_file_used


def check_dependencies():
    """Check if required dependencies are available"""
    try:
        import pytest
        import pydantic
        import openai
        return True
    except ImportError as e:
        print(f"Missing dependency: {e}")
        print("Please install required packages:")
        print("pip install pytest pydantic openai python-dotenv")
        return False


def run_tests(test_type="unit", verbose=True):
    """Run tests with specified configuration"""
    
    # Load environment
    env_loaded, env_file = load_environment()
    if env_loaded:
        print(f"✓ Loaded environment from: {env_file}")
    else:
        print("⚠ No environment file found - live tests will be skipped")
    
    # Check OpenAI API key
    openai_key = os.getenv("OPENAI_API_KEY")
    if openai_key:
        print(f"✓ OpenAI API key available: {openai_key[:8]}...")
    else:
        print("⚠ No OpenAI API key - live tests will be skipped")
    
    # Check dependencies
    if not check_dependencies():
        return False
    
    # Build pytest command
    cmd = ["python", "-m", "pytest"]
    
    # Add test directory
    test_dir = Path(__file__).parent
    cmd.append(str(test_dir))
    
    # Configure output
    if verbose:
        cmd.extend(["-v", "-s"])  # Verbose output with prints
    
    # Configure test selection based on type
    if test_type == "unit":
        cmd.extend(["-m", "not slow and not integration"])
        print("🧪 Running unit tests (fast)")
    
    elif test_type == "integration":
        cmd.extend(["-m", "integration"])
        print("🔗 Running integration tests")
    
    elif test_type == "live":
        if not openai_key:
            print("❌ Cannot run live tests without OpenAI API key")
            return False
        cmd.extend(["-m", "slow or live"])
        print("🌐 Running live tests (requires API key)")
    
    elif test_type == "all":
        print("🚀 Running all tests")
    
    elif test_type == "fast":
        cmd.extend(["-m", "not slow"])
        print("⚡ Running fast tests only")
    
    else:
        # Specific test file or pattern
        cmd = ["python", "-m", "pytest", test_type]
        if verbose:
            cmd.extend(["-v", "-s"])
        print(f"🎯 Running specific tests: {test_type}")
    
    # Add useful options
    cmd.extend([
        "--tb=short",  # Shorter traceback format
        "--strict-markers",  # Ensure all markers are defined
        "-ra"  # Show short test summary for all tests
    ])
    
    print(f"Command: {' '.join(cmd)}")
    print("-" * 60)
    
    # Run tests
    try:
        result = subprocess.run(cmd, cwd=test_dir.parent.parent)
        return result.returncode == 0
    except KeyboardInterrupt:
        print("\n⚠ Tests interrupted by user")
        return False
    except Exception as e:
        print(f"❌ Error running tests: {e}")
        return False


def print_help():
    """Print usage help"""
    print("""
StatBlock Generator Test Runner

Usage:
    python run_tests.py [test_type]

Test Types:
    unit        - Run only unit tests (fast, no API calls)
    integration - Run integration tests 
    live        - Run live tests with real OpenAI API calls (requires API key)
    fast        - Run all fast tests (unit + integration, no live API)
    all         - Run all tests including live API calls
    <file>      - Run specific test file or pattern

Examples:
    python run_tests.py                    # Run unit tests (default)
    python run_tests.py unit               # Run unit tests only
    python run_tests.py live               # Run live API tests
    python run_tests.py all                # Run everything
    python run_tests.py test_models.py     # Run specific test file

Environment:
    The script will automatically load environment variables from:
    1. env.development
    2. env.production  
    3. .env
    
    For live tests, you need OPENAI_API_KEY in your environment file.
""")


def main():
    """Main entry point"""
    if len(sys.argv) > 1:
        if sys.argv[1] in ["-h", "--help", "help"]:
            print_help()
            return
        
        test_type = sys.argv[1]
    else:
        test_type = "unit"  # Default to unit tests
    
    print("🧙‍♂️ StatBlock Generator Test Runner")
    print("=" * 60)
    
    success = run_tests(test_type)
    
    print("=" * 60)
    if success:
        print("✅ All tests passed!")
    else:
        print("❌ Some tests failed or were skipped")
        sys.exit(1)


if __name__ == "__main__":
    main()
