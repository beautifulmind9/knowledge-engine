"""Conservative, local source identity evidence from document metadata and text."""
from pathlib import Path
import re


_GENERIC_TITLES = {"untitled", "document", "scan", "scanned document", "cover"}
_BYLINE = re.compile(r"^(?:by|author|written by|prepared by)\s*[:\-]?\s+(.+)$", re.I)


def _clean(value):
    if isinstance(value, (list, tuple)):
        value = value[0] if value else ""
    value = re.sub(r"\s+", " ", str(value or "")).strip()
    return value[:500] if value else ""


def embedded_identity(path: str | Path, extension: str) -> tuple[str, str]:
    """Read only structured title/author metadata; malformed metadata is ignored."""
    try:
        if extension == ".pdf":
            from pypdf import PdfReader
            metadata = PdfReader(str(path)).metadata
            return _clean(metadata.title if metadata else ""), _clean(metadata.author if metadata else "")
        if extension == ".docx":
            from docx import Document
            props = Document(str(path)).core_properties
            return _clean(props.title), _clean(props.author)
        if extension == ".epub":
            from ebooklib import epub
            book = epub.read_epub(str(path))
            titles = book.get_metadata("DC", "title")
            creators = book.get_metadata("DC", "creator")
            return _clean(titles[0][0] if titles else ""), _clean(creators[0][0] if creators else "")
    except Exception:
        # Metadata is optional. A parser's metadata failure must not fail reading.
        return "", ""
    return "", ""


def visible_identity(text: str) -> tuple[str, str, str | None]:
    """Recognize only a title-page-like opening and explicitly marked bylines."""
    lines = [re.sub(r"\s+", " ", line).strip() for line in text.splitlines()]
    lines = [line for line in lines[:30] if line]
    if not lines:
        return "", "", None
    title = ""
    marked_title = False
    for line in lines[:8]:
        heading = re.match(r"^#{1,6}\s+(.+)$", line)
        labeled = re.match(r"^(?:title|work)\s*:\s*(.+)$", line, re.I)
        candidate = (heading or labeled).group(1).strip() if heading or labeled else ""
        if candidate and candidate.casefold() not in _GENERIC_TITLES and not candidate.endswith((".", ";")):
            title = candidate[:500]
            marked_title = True
            break
    author = ""
    for line in lines[:12]:
        match = _BYLINE.match(line)
        if match:
            candidate = _clean(match.group(1))
            # Avoid treating a sentence or a list of names as a byline.
            if len(candidate) <= 120 and not candidate.endswith((".", ";")):
                author = candidate
            break
    # Plain text title pages have no markup. Accept their opening line only
    # when an explicit byline independently establishes title-page structure.
    if not title and author and lines:
        candidate = lines[0]
        if candidate.casefold() not in _GENERIC_TITLES and len(candidate) <= 180 and len(candidate.split()) <= 18 and not candidate.endswith((".", ";")):
            title = candidate[:500]
    if author:
        return title, author, "material_text"
    # A single standalone name directly below a plain opening title is a
    # plausible title-page author candidate, but extracted text cannot prove
    # the role. Keep it explicitly reviewable rather than asserting authorship.
    if not marked_title and not title and len(lines) >= 2:
        first, second = lines[0], lines[1]
        name_words = second.split()
        looks_like_name = (2 <= len(name_words) <= 3 and len(second) <= 100
                           and all(re.match(r"^[A-ZÀ-ÖØ-Þ][\w'’.-]*$", word) for word in name_words))
        another_name_follows = len(lines) > 2 and 2 <= len(lines[2].split()) <= 3 and all(
            re.match(r"^[A-ZÀ-ÖØ-Þ][\w'’.-]*$", word) for word in lines[2].split()
        )
        if (first.casefold() not in _GENERIC_TITLES and len(first) <= 180 and len(first.split()) <= 18
                and not first.endswith((".", ";")) and looks_like_name and not another_name_follows):
            return first[:500], second[:500], "material_text_suggested"
    # Names without an explicit byline or narrow title-page layout are never
    # promoted to authorship.
    return title, "", None


def resolve_identity(path: str | Path, extension: str, text: str) -> dict:
    metadata_title, metadata_author = embedded_identity(path, extension)
    text_title, text_author, text_author_origin = visible_identity(text)
    # A clear opening title-page heading wins a conflict with embedded metadata;
    # metadata can be stale after a document has been repurposed.
    title, title_origin = (text_title, "material_text") if text_title else (metadata_title, "document_metadata")
    # An explicit byline is stronger than a metadata creator field. Other names
    # in prose are not authorship evidence.
    author, author_origin = (text_author, text_author_origin) if text_author and (text_author_origin == "material_text" or not metadata_author) else (metadata_author, "document_metadata")
    return {
        "title": title,
        "title_origin": title_origin if title else None,
        "author": author,
        "author_origin": author_origin if author else None,
        "author_review_required": author_origin == "material_text_suggested",
        "title_conflict": bool(text_title and metadata_title and text_title.casefold() != metadata_title.casefold()),
    }
