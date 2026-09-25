"""
pytest conftest for Phase 2 tests.
Sets asyncio mode and adds backend/ to sys.path.
"""
import sys
import os

# Ensure backend app is importable
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "..", "backend"))
