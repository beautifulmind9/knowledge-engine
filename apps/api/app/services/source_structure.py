from bisect import bisect_right
from pathlib import Path
import re

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


def _ordered_sections(sections: list[dict]) -> list[dict]:
    return sorted(
        (section for section in sections if section.get("title") and section.get("page_number")),
        key=lambda section: int(section["page_number"]),
    )


def _section_for_page(page_number: int, sections: list[dict]) -> str | None:
    current = None
    for section in sections:
        if int(section["page_number"]) > page_number:
            break
        current = section
    return str(current["title"]) if current else None


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

    ordered_sections = _ordered_sections(sections)

    annotated = 0
    distinct_sections: set[str] = set()
    for chunk in chunks:
        if not page_ends:
            chunk["chapter_or_section"] = None
            continue

        start_word = max(int(chunk.get("start_word_index") or 0), 0)
        page_index = min(bisect_right(page_ends, start_word), len(page_ends) - 1)
        page_number = page_index + 1

        chunk["source_page_start"] = page_number
        title = _section_for_page(page_number, ordered_sections)
        if title:
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


def _normalize_evidence(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"[^a-z0-9]+", " ", value.lower()).strip()


def _evidence_fragments(evidence: str | None) -> list[str]:
    """Return only long exact-match fragments suitable for deterministic lookup."""
    if not evidence:
        return []

    raw_parts = re.split(r"(?:\.{3,}|…)", evidence)
    parts = [
        _normalize_evidence(part)
        for part in raw_parts
        if len(_normalize_evidence(part).split()) >= 5
    ]
    if parts:
        return parts

    normalized = _normalize_evidence(evidence)
    return [normalized] if len(normalized.split()) >= 5 else []


def assign_outline_sections_to_assets_from_evidence(
    assets: list[dict],
    page_texts: list[str],
    sections: list[dict],
) -> dict:
    """Refine asset sections only when exact evidence resolves to one outline section.

    A chunk may cross an outline boundary, so its starting section is only a
    coarse fallback. This pass searches long evidence fragments against PDF page
    text and changes an asset label only when every matched fragment resolves to
    the same embedded-outline section. Ambiguous or paraphrased evidence is left
    untouched rather than guessed.
    """
    ordered_sections = _ordered_sections(sections)
    normalized_pages = [_normalize_evidence(text) for text in page_texts]

    matched = 0
    updated = 0
    ambiguous = 0
    unmatched = 0

    for asset in assets:
        fragments = _evidence_fragments(asset.get("evidence"))
        candidate_sections: set[str] = set()
        had_match = False

        for fragment in fragments:
            hit_pages = [
                index + 1
                for index, page_text in enumerate(normalized_pages)
                if fragment and fragment in page_text
            ]
            if not hit_pages:
                continue

            had_match = True
            fragment_sections = {
                section
                for page in hit_pages
                if (section := _section_for_page(page, ordered_sections))
            }
            candidate_sections.update(fragment_sections)

        if not had_match or not candidate_sections:
            unmatched += 1
            continue
        if len(candidate_sections) != 1:
            ambiguous += 1
            continue

        matched += 1
        resolved = next(iter(candidate_sections))
        if asset.get("chapter_or_section") != resolved:
            asset["chapter_or_section"] = resolved
            updated += 1

    return {
        "evidence_matched_asset_count": matched,
        "evidence_updated_asset_count": updated,
        "evidence_ambiguous_asset_count": ambiguous,
        "evidence_unmatched_asset_count": unmatched,
    }


def annotate_pdf_assets_with_outline_from_evidence(
    file_path: str | Path,
    assets: list[dict],
) -> dict:
    """Refine stored asset sections from exact source evidence without AI calls."""
    reader = PdfReader(str(file_path))
    sections = _flatten_pdf_outline(reader)
    page_texts = [(page.extract_text() or "").strip() for page in reader.pages]
    return assign_outline_sections_to_assets_from_evidence(assets, page_texts, sections)


def annotate_pdf_chunks_with_outline(file_path: str | Path, chunks: list[dict]) -> tuple[list[dict], dict]:
    """Read a PDF once and enrich chunks from its embedded outline/bookmarks."""
    reader = PdfReader(str(file_path))
    sections = _flatten_pdf_outline(reader)
    page_word_counts = [len(((page.extract_text() or "").strip()).split()) for page in reader.pages]
    return assign_outline_sections_to_chunks(chunks, page_word_counts, sections)
