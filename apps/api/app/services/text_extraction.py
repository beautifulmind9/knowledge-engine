import csv
import json
from pathlib import Path

from bs4 import BeautifulSoup


TEXT_OUTPUT_FOLDER = Path("storage/extracted_text")


class UnsupportedExtractionTypeError(Exception):
    pass


def extract_text_from_file(file_path: str, file_type: str) -> str:
    path = Path(file_path)
    extension = file_type.lower()

    if extension in [".txt", ".md"]:
        return path.read_text(encoding="utf-8", errors="ignore")

    if extension in [".html", ".htm"]:
        html = path.read_text(encoding="utf-8", errors="ignore")
        soup = BeautifulSoup(html, "html.parser")

        for tag in soup(["script", "style"]):
            tag.decompose()

        return soup.get_text(separator="\n", strip=True)

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

    raise UnsupportedExtractionTypeError(
        f"Text extraction is not implemented yet for {extension} files."
    )


def save_extracted_text(source_id: str, text: str) -> str:
    TEXT_OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    output_path = TEXT_OUTPUT_FOLDER / f"{source_id}.txt"
    output_path.write_text(text, encoding="utf-8")

    return str(output_path)
