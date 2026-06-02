from pathlib import Path
import shutil

input_folder = Path("outputs")
chunk_root = Path("outputs/chunks")

chunk_size = 1200
overlap = 200

# Recreate the chunks folder so old chunks do not mix with new chunks
if chunk_root.exists():
    shutil.rmtree(chunk_root)

chunk_root.mkdir(parents=True, exist_ok=True)

text_files = list(input_folder.glob("*.txt"))

print(f"Found {len(text_files)} text file(s)")
print(f"Chunk size: {chunk_size} words")
print(f"Overlap: {overlap} words")

for text_file in text_files:
    print(f"\nChunking: {text_file.name}")

    text = text_file.read_text(encoding="utf-8")
    words = text.split()

    step_size = chunk_size - overlap

    chunks = []

    for start in range(0, len(words), step_size):
        end = start + chunk_size
        chunk_words = words[start:end]

        if not chunk_words:
            continue

        chunks.append(chunk_words)

    book_folder = chunk_root / text_file.stem
    book_folder.mkdir(parents=True, exist_ok=True)

    for index, chunk_words in enumerate(chunks, start=1):
        chunk_text = " ".join(chunk_words)
        chunk_file = book_folder / f"chunk_{index:03}.txt"
        chunk_file.write_text(chunk_text, encoding="utf-8")

    print(f"Total words: {len(words)}")
    print(f"Created {len(chunks)} chunk(s)")