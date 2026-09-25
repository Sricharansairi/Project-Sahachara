"""
MITRA Phase 3 — Test Runner Script
Runs all Phase 3 tests and prints a formatted report.
Usage: python run_phase3_tests.py
"""
import subprocess
import sys
import os
import time

TEST_FILE = os.path.join(os.path.dirname(__file__), "phase3", "test_phase3.py")

BANNER = """
╔══════════════════════════════════════════════════════════════════════╗
║         PROJECT SAHACHARA — PHASE 3 TESTING GATE                   ║
║         Authentication & Screen Capture Engine                      ║
╚══════════════════════════════════════════════════════════════════════╝
"""

print(BANNER)
print(f"Test file   : {TEST_FILE}")
print(f"Timestamp   : {time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 72)

env = os.environ.copy()
env["PYTHONUTF8"] = "1"

result = subprocess.run(
    [sys.executable, TEST_FILE],
    env=env,
    cwd=os.path.dirname(TEST_FILE),
)

print("\n" + "=" * 72)
if result.returncode == 0:
    print("  🏆 PHASE 3 TESTING GATE: ALL 9/9 GATES PASSED ✅")
else:
    print(f"  ❌ PHASE 3 TESTING GATE: FAILURES DETECTED (exit code {result.returncode})")
print("=" * 72)

sys.exit(result.returncode)
