import hashlib
import logging
import re
from collections.abc import Iterator
from dataclasses import dataclass
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urlsplit

from pypdf import PdfReader
from pypdf.errors import PdfReadError

logger = logging.getLogger(__name__)

_METADATA_PATTERN = re.compile(r"^(TITLE|SOURCE_URL):\s*(.*)$", re.MULTILINE)
_SENTENCE_BOUNDARY = re.compile(r"(?<=[.!?।॥])\s+|\n+")


class _ReadableHTMLParser(HTMLParser):
    _IGNORED_TAGS = {"script", "style", "noscript", "svg", "nav", "footer"}
    _BREAK_TAGS = {"br", "p", "div", "li", "h1", "h2", "h3", "h4", "tr"}

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.title_parts: list[str] = []
        self.source_url: str | None = None
        self._ignored_depth = 0
        self._inside_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attributes = dict(attrs)
        if tag in self._IGNORED_TAGS:
            self._ignored_depth += 1
        if tag == "title":
            self._inside_title = True
        if tag == "link" and "canonical" in (attributes.get("rel") or "").split():
            self.source_url = attributes.get("href")
        if tag in self._BREAK_TAGS:
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in self._IGNORED_TAGS and self._ignored_depth:
            self._ignored_depth -= 1
        if tag == "title":
            self._inside_title = False
        if tag in self._BREAK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._inside_title:
            self.title_parts.append(data)
        if not self._ignored_depth and not self._inside_title:
            self.parts.append(data)


@dataclass(frozen=True)
class SourceDocument:
    title: str
    source_url: str | None
    text: str
    document_key: str


def _document_key(source_url: str | None, text: str) -> str:
    normalized = " ".join(text.split())
    return hashlib.sha256(f"{source_url or ''}\0{normalized}".encode()).hexdigest()


def extract_document(path: Path) -> SourceDocument:
    title = path.stem.replace("_", " ")
    source_url = None
    if path.suffix.lower() == ".pdf":
        reader = PdfReader(path)
        if reader.metadata and reader.metadata.title:
            title = reader.metadata.title.strip() or title
        text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
    else:
        content = path.read_text(encoding="utf-8-sig")
        is_html = path.suffix.lower() in {".html", ".htm"} or bool(
            re.search(r"<(?:!doctype\s+html|html\b)", content[:500], re.IGNORECASE)
        )
        parser = None
        if is_html:
            parser = _ReadableHTMLParser()
            parser.feed(content)
            content = "\n".join(part.strip() for part in parser.parts if part.strip())
        metadata = {
            match.group(1): match.group(2).strip()
            for match in _METADATA_PATTERN.finditer(content[:2000])
        }
        title = (
            metadata.get("TITLE")
            or (" ".join(parser.title_parts).strip() if parser else None)
            or title
        )
        source_url = metadata.get("SOURCE_URL") or (parser.source_url if parser else None)
        if source_url:
            parsed_url = urlsplit(source_url)
            if parsed_url.scheme not in {"http", "https"} or not parsed_url.netloc:
                source_url = None
        text = _METADATA_PATTERN.sub("", content, count=2).strip()

    text = re.sub(r"[ \t]+\n", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text).strip()
    if not text:
        raise ValueError("Document contains no extractable text.")
    return SourceDocument(title, source_url, text, _document_key(source_url, text))


def load_documents(pages_directory: Path, pdfs_directory: Path) -> Iterator[SourceDocument]:
    candidates = []
    for directory, suffixes in (
        (pages_directory, {".txt", ".html", ".htm"}),
        (pdfs_directory, {".pdf"}),
        (pdfs_directory.parent, {".pdf"}),
    ):
        if directory.exists():
            candidates.extend(
                path for path in directory.rglob("*") if path.is_file() and path.suffix.lower() in suffixes
            )

    seen = set()
    for path in sorted(set(candidates)):
        try:
            document = extract_document(path)
        except (OSError, UnicodeError, ValueError) as error:
            logger.warning("Skipping unreadable document %s (%s)", path.name, type(error).__name__)
            continue
        except (PdfReadError, KeyError) as error:
            logger.warning("Skipping unreadable PDF %s (%s)", path.name, type(error).__name__)
            continue
        if document.document_key in seen:
            logger.info("Skipping duplicate document %s", path.name)
            continue
        seen.add(document.document_key)
        yield document


def chunk_text(text: str, *, max_chars: int = 1200, overlap_chars: int = 150) -> list[str]:
    if max_chars <= 0 or overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("Chunk size must be positive and overlap must be smaller than chunk size.")

    sentences = [sentence.strip() for sentence in _SENTENCE_BOUNDARY.split(text) if sentence.strip()]
    chunks = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                chunks.append(current)
                current = ""
            words = sentence.split()
            parts = []
            part = ""
            for word in words:
                candidate = f"{part} {word}".strip()
                if len(word) > max_chars:
                    if part:
                        parts.append(part)
                        part = ""
                    parts.extend(
                        word[start : start + max_chars]
                        for start in range(0, len(word), max_chars)
                    )
                elif part and len(candidate) > max_chars:
                    parts.append(part)
                    overlap_words = []
                    available_overlap = max(
                        0,
                        min(overlap_chars, max_chars - len(word) - 1),
                    )
                    for previous_word in reversed(part.split()):
                        candidate_overlap = " ".join([previous_word, *overlap_words])
                        if len(candidate_overlap) > available_overlap:
                            break
                        overlap_words.insert(0, previous_word)
                    part = " ".join([*overlap_words, word])
                else:
                    part = candidate
            if part:
                parts.append(part)
            chunks.extend(parts[:-1])
            current = parts[-1] if parts else ""
            continue

        candidate = f"{current} {sentence}".strip()
        if current and len(candidate) > max_chars:
            chunks.append(current)
            available_overlap = max(0, max_chars - len(sentence) - 1)
            overlap_length = min(overlap_chars, available_overlap)
            overlap = current[-overlap_length:].strip() if overlap_length else ""
            if overlap:
                overlap = overlap.split(" ", maxsplit=1)[-1]
            current = f"{overlap} {sentence}".strip()
        else:
            current = candidate
    if current:
        chunks.append(current)
    return chunks
