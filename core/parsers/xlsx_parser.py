"""XLSX syllabus parser using openpyxl.

Each worksheet is treated as a candidate event-source table.
"""

import io
from pathlib import Path
from typing import Union

from openpyxl import load_workbook

from core.parsers import ParsedDoc


def parse_xlsx(source: Union[Path, bytes, io.BytesIO]) -> ParsedDoc:
    """Parse an XLSX file; return all non-empty sheet content as tables."""
    if isinstance(source, bytes):
        source = io.BytesIO(source)
    elif isinstance(source, Path):
        source = source.open("rb")

    wb = load_workbook(source, data_only=True)
    result = ParsedDoc()
    lines: list[str] = []

    for sheet in wb.worksheets:
        rows: list[list[str]] = []
        for row in sheet.iter_rows(values_only=True):
            cells = [str(c).strip() if c is not None else "" for c in row]
            if any(cells):
                rows.append(cells)
                joined = "\t".join(c for c in cells if c)
                if joined:
                    lines.append(joined)
        if rows:
            result.tables.append(rows)

    result.full_text = "\n".join(lines)
    result.paragraphs = [ln for ln in lines if ln]
    return result
