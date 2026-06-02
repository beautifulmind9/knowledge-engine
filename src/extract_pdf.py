from pathlib import Path
from pypdf import PdfReader

print("Knowledge Engine Started")

pdf_folder = Path("data/pdfs")
output_folder = Path("outputs")

output_folder.mkdir(exist_ok=True)

pdf_files = list(pdf_folder.glob("*.pdf"))

print(f"Found {len(pdf_files)} PDF(s)")

for pdf_path in pdf_files:
    print(f"Reading: {pdf_path.name}")

    reader = PdfReader(pdf_path)
    text = ""

    for page in reader.pages:
        page_text = page.extract_text()
        if page_text:
            text += page_text + "\n"

    output_file = output_folder / f"{pdf_path.stem}.txt"

    output_file.write_text(text, encoding="utf-8")

    print(f"Saved text to: {output_file}")
    print(f"Extracted {len(text.split())} words")