"""
MITRA Backend — Intelligent Clipboard Augmenter

Features:
- Content classification: raw text, table/delimited data, code, URL
- Sub-800ms transformations:
  - Clean and format to Markdown table (P5-T10)
  - Summarize to bullet points
  - Convert to JSON
  - Translate
"""
from __future__ import annotations

import csv
import io
import json
import re
import time
from typing import Any, Literal
import structlog

logger = structlog.get_logger(__name__)

ClipboardType = Literal["table", "code", "url", "raw_text"]


class ClipboardAugmenter:
    """Classifies and augments copied clipboard text."""

    def classify(self, content: str) -> ClipboardType:
        """Classify clipboard content type."""
        text = content.strip()
        if not text:
            return "raw_text"

        # URL check
        if re.match(r"^https?://[^\s]+$", text):
            return "url"

        # Code check (common language keywords, braces, semicolons, def/class/function)
        code_indicators = [
            r"def\s+\w+\(",
            r"function\s+\w+\(",
            r"class\s+\w+[:\{]",
            r"#include\s+<",
            r"import\s+[\w\s,]+from",
            r"pub\s+fn\s+\w+",
            r"console\.log\(",
        ]
        if any(re.search(p, text) for p in code_indicators):
            return "code"

        # Table check (CSV commas, pipes, tabs, or aligned columns with multiple lines)
        lines = [line.strip() for line in text.splitlines() if line.strip()]
        if len(lines) >= 2:
            # Check for comma-separated or tab-separated structure
            if all(line.count(",") >= 1 for line in lines[:3]):
                return "table"
            if all(line.count("\t") >= 1 for line in lines[:3]):
                return "table"
            if all(line.count("|") >= 2 for line in lines[:3]):
                return "table"

        return "raw_text"

    def clean_and_format_table(self, text: str) -> dict[str, Any]:
        """
        Convert messy tabular text (CSV, tab-separated, whitespace-aligned)
        into clean GitHub-flavored markdown table in < 800ms.
        """
        start_time = time.perf_counter()
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
        if not lines:
            return {"markdown_table": "", "elapsed_ms": 0.0}

        # Detect delimiter: comma, tab, pipe, or multiple spaces
        sample = lines[0]
        if "," in sample:
            delimiter = ","
        elif "\t" in sample:
            delimiter = "\t"
        elif "|" in sample:
            delimiter = "|"
        else:
            delimiter = None

        rows = []
        if delimiter:
            for line in lines:
                if delimiter == "|":
                    cells = [c.strip() for c in line.split("|") if c.strip()]
                else:
                    reader = csv.reader(io.StringIO(line), delimiter=delimiter)
                    cells = [c.strip() for row in reader for c in row if c.strip()]
                if cells:
                    rows.append(cells)
        else:
            for line in lines:
                cells = re.split(r"\s{2,}|\t", line.strip())
                if cells:
                    rows.append([c.strip() for c in cells])

        if not rows:
            return {"markdown_table": text, "elapsed_ms": (time.perf_counter() - start_time) * 1000.0}

        # Normalize number of columns
        max_cols = max(len(r) for r in rows)
        normalized = []
        for r in rows:
            padded = r + [""] * (max_cols - len(r))
            normalized.append(padded)

        # Build Markdown table
        header = normalized[0]
        divider = ["---"] * max_cols
        body = normalized[1:]

        table_md = "| " + " | ".join(header) + " |\n"
        table_md += "| " + " | ".join(divider) + " |\n"
        for r in body:
            table_md += "| " + " | ".join(r) + " |\n"

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        logger.info("clipboard.table_formatted", rows=len(rows), elapsed_ms=elapsed_ms)
        return {
            "markdown_table": table_md.strip(),
            "elapsed_ms": elapsed_ms,
            "row_count": len(rows),
            "col_count": max_cols,
        }

    def summarize_to_bullets(self, text: str) -> dict[str, Any]:
        """Summarize text into key bullets."""
        start_time = time.perf_counter()
        sentences = [s.strip() for s in re.split(r"[.!?]+", text) if len(s.strip()) > 10]
        bullets = [f"- {s}" for s in sentences[:3]]
        if not bullets:
            bullets = [f"- {text[:100]}..."]
        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "bullets": bullets,
            "text": "\n".join(bullets),
            "elapsed_ms": elapsed_ms,
        }

    def convert_to_json(self, text: str) -> dict[str, Any]:
        """Convert unstructured text/CSV into JSON."""
        start_time = time.perf_counter()
        lines = [l.strip() for l in text.strip().splitlines() if l.strip()]
        result_data: Any = {}

        if len(lines) > 1 and ("," in lines[0] or "\t" in lines[0]):
            delimiter = "," if "," in lines[0] else "\t"
            reader = csv.DictReader(io.StringIO(text), delimiter=delimiter)
            result_data = list(reader)
        else:
            # Key-value extraction
            kv = {}
            for line in lines:
                if ":" in line:
                    k, v = line.split(":", 1)
                    kv[k.strip()] = v.strip()
            result_data = kv or {"content": text}

        elapsed_ms = (time.perf_counter() - start_time) * 1000.0
        return {
            "json_data": result_data,
            "json_string": json.dumps(result_data, indent=2),
            "elapsed_ms": elapsed_ms,
        }


# Singleton instance
clipboard_augmenter = ClipboardAugmenter()
