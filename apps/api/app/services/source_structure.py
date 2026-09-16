from bisect import bisect_right
from pathlib import Path

from pypdf import PdfReader


def _flatten_pdf_outline(reader: PdfReader, items=None, level: int = 0) -> list[dict]:
    """Return usable PDF outline destinations in document order."""
    if items is None:
        try:
            items = reader.outline
        except Exception:
            return []

    sections: list[dict] = []
    for item in items or []:
        if isinstance(item, list):
            sections.extend(_flatten_pdf_outline(reader, item, level + 1))
            continue

        title = str(getattr(item, "title", "") or "").strip()
        if not title:
            continue
        try:
            page_number = reader.get_destination_page_number(item) + 1
        except Exception:
            continue
        sections.append(
            {
                "title": title,
                "page_number": page_number,
                "level": level,
            }
        )
    return sections


def assign_outline_sections_to_chunks(
    chunks: list[dict],
    page_word_counts: list[int],
    sections: list[dict],
) -> tuple[list[dict], dict]:
    """Annotate existing word-indexed chunks using page-based outline metadata.

    Chunk text is left untouched. The mapping uses the same whitespace word
    accounting as PDF text extraction, so this can safely enrich provenance
    without re-chunking or re-running AI interpretation.
    """
    page_ends: list[int] = []
    total = 0
    for count in page_word_counts:
        total += max(int(count or 0), 0)
        page_ends.append(total)

    ordered_sections = sorted(
        (section for section in sections if section.get("title") and section.get("page_number")),
        key=lambda section: int(section["page_number"]),
    )

    annotated = 0
    distinct_sections: set[str] = set()
    for chunk in chunks:
        if not page_ends:
            chunk["chapter_or_section"] = None
            continue

        start_word = max(int(chunk.get("start_word_index") or 0), 0)
        page_index = min(bisect_right(page_ends, start_word), len(page_ends) - 1)
        page_number = page_index + 1

        current = None
        for section in ordered_sections:
            if int(section["page_number"]) > page_number:
                break
            current = section

        chunk["source_page_start"] = page_number
        if current:
            title = str(current["title"])
            chunk["chapter_or_section"] = title
            distinct_sections.add(title)
            annotated += 1
        else:
            chunk["chapter_or_section"] = None

    return chunks, {
        "outline_entry_count": len(ordered_sections),
        "annotated_chunk_count": annotated,
        "unannotated_chunk_count": len(chunks) - annotated,
        "section_count": len(distinct_sections),
        "sections": sorted(distinct_sections),
    }


def annotate_pdf_chunks_with_outline(file_path: str | Path, chunks: list[dict]) -> tuple[list[dict], dict]:
    """Read a PDF once and enrich chunks from its embedded outline/bookmarks."""
    reader = PdfReader(str(file_path))
    sections = _flatten_pdf_outline(reader)
    page_word_counts = [len(((page.extract_text() or "").strip()).split()) for page in reader.pages]
    return assign_outline_sections_to_chunks(chunks, page_word_counts, sections)
