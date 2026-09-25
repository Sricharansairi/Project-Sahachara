"""
MITRA Phase 2 — Test Runner Script
Runs all Phase 2 tests and prints a formatted report.
Usage: python run_phase2_tests.py
"""
import subprocess
import sys
import os
import time

BACKEND_DIR = os.path.join(os.path.dirname(__file__), "..", "backend")
TEST_FILE = os.path.join(os.path.dirname(__file__), "phase2", "test_phase2.py")

BANNER = """
╔══════════════════════════════════════════════════════════════════════╗
║         PROJECT SAHACHARA — PHASE 2 TESTING GATE                   ║
║         Cloud Brain: FastAPI + NVIDIA NIM                           ║
╚══════════════════════════════════════════════════════════════════════╝
"""

print(BANNER)
print(f"Backend dir : {BACKEND_DIR}")
print(f"Test file   : {TEST_FILE}")
print(f"Timestamp   : {time.strftime('%Y-%m-%d %H:%M:%S')}")
print("=" * 72)

# Set PYTHONPATH so app package is importable
env = os.environ.copy()
env["PYTHONPATH"] = BACKEND_DIR

result = subprocess.run(
    [
        sys.executable, "-m", "pytest",
        TEST_FILE,
        "-v",
        "--tb=short",
        "-s",
        "--asyncio-mode=auto",
        "--no-header",
    ],
    env=env,
    cwd=BACKEND_DIR,
)

print("\n" + "=" * 72)
if result.returncode == 0:
    print("  🏆 PHASE 2 TESTING GATE: ALL TESTS PASSED ✅")
else:
    print(f"  ❌ PHASE 2 TESTING GATE: FAILURES DETECTED (exit code {result.returncode})")
print("=" * 72)

sys.exit(result.returncode)
