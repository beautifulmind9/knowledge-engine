import csv
import json
from pathlib import Path

from bs4 import BeautifulSoup
from ebooklib import epub
from pypdf import PdfReader


from app.db.persistence import STORAGE_ROOT

TEXT_OUTPUT_FOLDER = STORAGE_ROOT / "extracted_text"


class UnsupportedExtractionTypeError(Exception):
    pass


def clean_html_to_text(html_content: str) -> str:
    soup = BeautifulSoup(html_content, "html.parser")

    for tag in soup(["script", "style", "head"]):
        tag.decompose()

    # Preserve explicit document structure as hints for the chunker.
    for tag in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6"]):
        tag.replace_with("#" * int(tag.name[1]) + " " + tag.get_text(" ", strip=True))

    return soup.get_text(separator="\n", strip=True)


def extract_text_from_pdf(file_path: str) -> str:
    reader = PdfReader(file_path)
    pages = []

    for page in reader.pages:
        text = page.extract_text() or ""
        text = text.strip()

        if text:
            pages.append(text)

    extracted_text = "\n\n".join(pages)

    if not extracted_text.strip():
        raise UnsupportedExtractionTypeError(
            "This PDF does not contain extractable text. OCR is not implemented yet."
        )

    return extracted_text


def extract_text_from_epub(file_path: str) -> str:
    book = epub.read_epub(file_path)
    sections = []

    items = [book.get_item_with_id(entry[0]) for entry in book.spine if entry[1] != "no"]
    if not items:
        items = list(book.get_items())
    for item in items:
        media_type = getattr(item, "media_type", None)

        if media_type != "application/xhtml+xml":
            continue

        try:
            html_content = item.get_content().decode("utf-8", errors="ignore")
        except AttributeError:
            continue

        text = clean_html_to_text(html_content)

        if text:
            sections.append(text)

    return "\n\n".join(sections)


def extract_text_from_file(file_path: str, file_type: str) -> str:
    path = Path(file_path)
    extension = file_type.lower()
    if extension in {".epub", ".docx"}:
        from zipfile import ZipFile
        with ZipFile(path) as archive:
            if sum(i.file_size for i in archive.infolist()) > 100 * 1024 * 1024 or len(archive.infolist()) > 10000:
                raise UnsupportedExtractionTypeError("Archive exceeds the local parsing limit.")

    if extension in [".txt", ".md"]:
        return path.read_text(encoding="utf-8", errors="ignore")

    if extension in [".html", ".htm"]:
        html = path.read_text(encoding="utf-8", errors="ignore")
        return clean_html_to_text(html)

    if extension == ".json":
        data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
        return json.dumps(data, indent=2, ensure_ascii=False)

    if extension == ".csv":
        rows = []

        with path.open("r", encoding="utf-8", errors="ignore", newline="") as csvfile:
            reader = csv.reader(csvfile)

            for row in reader:
                rows.append(" | ".join(row))

        return "\n".join(rows)

    if extension == ".docx":
        from docx import Document
        from docx.text.paragraph import Paragraph
        document = Document(str(path))
        blocks = []
        for block in document.iter_inner_content():
            if isinstance(block, Paragraph):
                style = block.style.name if block.style else ""
                level = style.removeprefix("Heading ")
                prefix = "#" * int(level) + " " if style.startswith("Heading ") and level.isdigit() and 1 <= int(level) <= 6 else ""
                blocks.append(prefix + block.text)
            else:
                blocks.extend(" | ".join(cell.text for cell in row.cells) for row in block.rows)
        return "\n".join(blocks)

    if extension == ".pdf":
        return extract_text_from_pdf(str(path))

    if extension == ".epub":
        return extract_text_from_epub(str(path))

    raise UnsupportedExtractionTypeError(
        f"Text extraction is not implemented yet for {extension} files."
    )


def save_extracted_text(source_id: str, text: str) -> str:
    TEXT_OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    output_path = TEXT_OUTPUT_FOLDER / f"{source_id}.txt"
    output_path.write_text(text, encoding="utf-8")

    return str(output_path)
