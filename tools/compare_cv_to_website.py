#!/usr/bin/env python3
"""Create a review-only comparison between master_cv.docx and the website.

The script uses only the Python standard library. It never changes HTML files,
commits, or pushes. Its output is a Markdown checklist for human review.
"""

from __future__ import annotations

import argparse
import difflib
import html
import re
import sys
import unicodedata
import zipfile
from dataclasses import dataclass
from datetime import datetime
from functools import lru_cache
from html.parser import HTMLParser
from pathlib import Path
from xml.etree import ElementTree as ET


WORD_NS = "http://schemas.openxmlformats.org/wordprocessingml/2006/main"
W = f"{{{WORD_NS}}}"

SECTION_ROUTES = {
    "RESEARCH INTERESTS": ("index.html", "research/index.html"),
    "TEACHING EXPERIENCE": ("index.html",),
    "AWARDS AND HONORS": ("index.html",),
    "FUNDING": ("research/index.html", "research/project.html"),
    "JOURNAL PUBLICATIONS": ("publication/index.html", "research/publication.html"),
    "BOOK CHAPTERS": ("publication/index.html", "research/publication.html"),
    "REFEREED CONFERENCE PUBLICATIONS": (
        "publication/index.html",
        "research/publication.html",
    ),
    "REFEREED CONFERENCE ABSTRACTS AND RESEARCH POSTERS": (
        "research/report.html",
        "research/publication.html",
    ),
    "PROFESSIONAL SERVICE": ("index.html",),
    "STUDENTS ADVISING AND MENTORING": ("research/people.html",),
}

WEBSITE_REVIEW_FILES = (
    "index.html",
    "publication/index.html",
    "research/index.html",
    "research/people.html",
    "research/project.html",
    "research/publication.html",
    "research/report.html",
)


@dataclass(frozen=True)
class HtmlBlock:
    tag: str
    text: str


class VisibleHtmlParser(HTMLParser):
    """Collect visible paragraph and list-item text without dependencies."""

    CAPTURE_TAGS = {"p", "li"}
    IGNORE_TAGS = {"script", "style", "svg", "nav"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.ignore_depth = 0
        self.active: list[tuple[str, list[str]]] = []
        self.blocks: list[HtmlBlock] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        if tag in self.IGNORE_TAGS:
            self.ignore_depth += 1
            return
        if self.ignore_depth == 0 and tag in self.CAPTURE_TAGS:
            self.active.append((tag, []))

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self.IGNORE_TAGS:
            self.ignore_depth = max(0, self.ignore_depth - 1)
            return
        if self.ignore_depth or tag not in self.CAPTURE_TAGS:
            return
        for index in range(len(self.active) - 1, -1, -1):
            active_tag, pieces = self.active[index]
            if active_tag == tag:
                text = clean_display_text(" ".join(pieces))
                if text:
                    self.blocks.append(HtmlBlock(tag, text))
                del self.active[index]
                break

    def handle_data(self, data: str) -> None:
        if self.ignore_depth:
            return
        for _, pieces in self.active:
            pieces.append(data)


def clean_display_text(value: str) -> str:
    value = html.unescape(value)
    value = value.replace("\u00a0", " ")
    return re.sub(r"\s+", " ", value).strip()


@lru_cache(maxsize=None)
def normalize(value: str) -> str:
    value = unicodedata.normalize("NFKD", clean_display_text(value))
    value = value.replace("’", "'").replace("–", "-").replace("—", "-")
    value = value.lower()
    value = re.sub(r"[^a-z0-9]+", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def paragraph_text(paragraph: ET.Element) -> str:
    pieces: list[str] = []
    for node in paragraph.iter():
        if node.tag == W + "t":
            pieces.append(node.text or "")
        elif node.tag in {W + "tab", W + "br", W + "cr"}:
            pieces.append(" ")
    return clean_display_text("".join(pieces))


def extract_docx_paragraphs(path: Path) -> list[str]:
    try:
        with zipfile.ZipFile(path) as archive:
            root = ET.fromstring(archive.read("word/document.xml"))
    except (OSError, KeyError, zipfile.BadZipFile, ET.ParseError) as exc:
        raise ValueError(f"Unable to read DOCX file {path}: {exc}") from exc

    body = root.find(W + "body")
    if body is None:
        return []

    paragraphs: list[str] = []
    for child in body:
        if child.tag == W + "p":
            text = paragraph_text(child)
            if text:
                paragraphs.append(text)
        elif child.tag == W + "tbl":
            for paragraph in child.iter(W + "p"):
                text = paragraph_text(paragraph)
                if text:
                    paragraphs.append(text)
    return paragraphs


def is_section_heading(text: str) -> bool:
    letters = [char for char in text if char.isalpha()]
    return bool(letters) and text == text.upper() and 3 <= len(text) <= 90


def split_sections(paragraphs: list[str]) -> dict[str, list[str]]:
    sections: dict[str, list[str]] = {}
    current: str | None = None
    for text in paragraphs:
        if is_section_heading(text):
            current = text
            sections.setdefault(current, [])
        elif current is not None:
            sections[current].append(text)
    return sections


def read_html_blocks(path: Path) -> list[HtmlBlock]:
    parser = VisibleHtmlParser()
    parser.feed(path.read_text(encoding="utf-8"))
    return parser.blocks


def candidate_text(text: str, *, allow_short: bool = False) -> bool:
    normalized = normalize(text)
    words = normalized.split()
    if len(normalized) < 14 or len(words) < (2 if allow_short else 3):
        return False
    if len(words) <= 4 and not any(char.isdigit() for char in text):
        if not any(mark in text for mark in (",", ";", "-", "—", "–", ":")):
            return False
    return True


def similarity(left: str, right: str) -> float:
    a, b = normalize(left), normalize(right)
    if not a or not b:
        return 0.0
    if a in b or b in a:
        shorter, longer = sorted((len(a), len(b)))
        return min(1.0, 0.90 + 0.10 * (shorter / longer))
    a_tokens, b_tokens = set(a.split()), set(b.split())
    overlap = len(a_tokens & b_tokens)
    left_coverage = overlap / max(1, len(a_tokens))
    right_coverage = overlap / max(1, len(b_tokens))
    token_score = min(left_coverage, right_coverage) * 0.92

    # SequenceMatcher is relatively expensive for a long CV. Only run it for
    # pairs that already share enough vocabulary to be plausible matches.
    if max(left_coverage, right_coverage) < 0.35:
        return token_score
    ratio = difflib.SequenceMatcher(None, a, b, autojunk=False).ratio()
    return max(ratio, token_score)


def best_match(text: str, blocks: list[tuple[str, str]]) -> tuple[float, str]:
    best_score = 0.0
    best_source = ""
    for source, block in blocks:
        score = similarity(text, block)
        if score > best_score:
            best_score = score
            best_source = source
    return best_score, best_source


def markdown_escape(text: str) -> str:
    return text.replace("|", "\\|")


def build_report(
    cv_path: Path,
    site_root: Path,
    threshold: float,
    max_per_section: int,
    max_per_page: int,
) -> str:
    paragraphs = extract_docx_paragraphs(cv_path)
    sections = split_sections(paragraphs)

    html_by_file: dict[str, list[HtmlBlock]] = {}
    missing_files: list[str] = []
    for relative in WEBSITE_REVIEW_FILES:
        path = site_root / relative
        if path.exists():
            html_by_file[relative] = read_html_blocks(path)
        else:
            missing_files.append(relative)

    cv_candidates: list[tuple[str, str, tuple[str, ...], float, str]] = []
    for section, routes in SECTION_ROUTES.items():
        route_blocks = [
            (route, block.text)
            for route in routes
            for block in html_by_file.get(route, [])
        ]
        unmatched: list[tuple[str, float, str]] = []
        for text in sections.get(section, []):
            if not candidate_text(text):
                continue
            score, source = best_match(text, route_blocks)
            if score < threshold:
                unmatched.append((text, score, source))
        for text, score, source in unmatched[:max_per_section]:
            cv_candidates.append((section, text, routes, score, source))

    cv_blocks = [("master_cv.docx", text) for text in paragraphs if candidate_text(text, allow_short=True)]
    web_candidates: list[tuple[str, str, float]] = []
    for relative, blocks in html_by_file.items():
        page_unmatched: list[tuple[str, float]] = []
        seen: set[str] = set()
        for block in blocks:
            text = block.text
            key = normalize(text)
            if key in seen or not candidate_text(text, allow_short=relative.endswith("people.html")):
                continue
            seen.add(key)
            score, _ = best_match(text, cv_blocks)
            if score < threshold:
                page_unmatched.append((text, score))
        for text, score in page_unmatched[:max_per_page]:
            web_candidates.append((relative, text, score))

    generated = datetime.now().astimezone().strftime("%Y-%m-%d %H:%M %Z")
    lines = [
        "# CV–Website Comparison",
        "",
        f"Generated: {generated}",
        f"CV: `{cv_path}`",
        f"Website: `{site_root}`",
        f"Approximate-match threshold: `{threshold:.2f}`",
        "",
        "> Review only: this report may contain intentional differences or false positives.",
        "> The comparison tool did not edit any website file.",
        "",
        "## CV content that may be missing or different on the website",
        "",
    ]

    if cv_candidates:
        lines.extend(["| ID | CV section | Suggested page(s) | Candidate | Closest match |", "|---|---|---|---|---|"])
        for number, (section, text, routes, score, source) in enumerate(cv_candidates, 1):
            closest = f"{source} ({score:.0%})" if source else f"none ({score:.0%})"
            lines.append(
                f"| C{number:02d} | {markdown_escape(section)} | "
                f"{markdown_escape(', '.join(routes))} | {markdown_escape(text)} | "
                f"{markdown_escape(closest)} |"
            )
    else:
        lines.append("No candidates found at the current threshold.")

    lines.extend(["", "## Website content that may be missing or different in the CV", ""])
    if web_candidates:
        lines.extend(["| ID | Website page | Candidate | Closest CV match |", "|---|---|---|---|"])
        for number, (relative, text, score) in enumerate(web_candidates, 1):
            lines.append(
                f"| W{number:02d} | {markdown_escape(relative)} | "
                f"{markdown_escape(text)} | {score:.0%} |"
            )
    else:
        lines.append("No candidates found at the current threshold.")

    if missing_files:
        lines.extend(["", "## Missing website files", ""])
        lines.extend(f"- `{item}`" for item in missing_files)

    lines.extend(
        [
            "",
            "## Next step",
            "",
            "Review the IDs, then ask Codex to apply only the approved items and show a local preview.",
            "See `UPDATE_WEBSITE.md` for the complete workflow.",
            "",
        ]
    )
    return "\n".join(lines)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate a review-only Markdown comparison of a Word CV and this website."
    )
    parser.add_argument("--cv", type=Path, required=True, help="Path to master_cv.docx")
    parser.add_argument("--site", type=Path, default=Path("."), help="Website root")
    parser.add_argument("--output", type=Path, help="Write Markdown here; otherwise print it")
    parser.add_argument(
        "--threshold",
        type=float,
        default=0.88,
        help="Approximate-match threshold from 0 to 1 (default: 0.88)",
    )
    parser.add_argument("--max-per-section", type=int, default=8)
    parser.add_argument("--max-per-page", type=int, default=6)
    args = parser.parse_args()
    if not 0 <= args.threshold <= 1:
        parser.error("--threshold must be between 0 and 1")
    if args.max_per_section < 1 or args.max_per_page < 1:
        parser.error("candidate limits must be positive")
    return args


def main() -> int:
    args = parse_args()
    cv_path = args.cv.expanduser().resolve()
    site_root = args.site.expanduser().resolve()
    if not cv_path.is_file():
        print(f"error: CV not found: {cv_path}", file=sys.stderr)
        return 2
    if not site_root.is_dir():
        print(f"error: website directory not found: {site_root}", file=sys.stderr)
        return 2

    try:
        report = build_report(
            cv_path,
            site_root,
            args.threshold,
            args.max_per_section,
            args.max_per_page,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2

    if args.output:
        output = args.output.expanduser()
        if not output.is_absolute():
            output = Path.cwd() / output
        output.write_text(report, encoding="utf-8")
        print(f"Comparison report written to {output.resolve()}")
        print("Next: review the C## and W## items, then follow UPDATE_WEBSITE.md.")
    else:
        print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
