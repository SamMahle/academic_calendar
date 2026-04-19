from dataclasses import dataclass, field


@dataclass
class ParsedDoc:
    """Normalized output from any syllabus parser."""
    paragraphs: list[str] = field(default_factory=list)
    headings: list[tuple[int, str]] = field(default_factory=list)  # (level, text)
    tables: list[list[list[str]]] = field(default_factory=list)    # [table][row][col]
    full_text: str = ""
    is_scan: bool = False       # True when PDF has negligible text yield
    scan_page_count: int = 0    # Number of pages that looked like scans
