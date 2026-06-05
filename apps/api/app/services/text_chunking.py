import json
from pathlib import Path


CHUNK_OUTPUT_FOLDER = Path("storage/chunks")


def chunk_text(source_id: str, text: str, chunk_size: int = 1200, overlap: int = 200):
    words = text.split()

    if not words:
        return []

    step_size = chunk_size - overlap

    if step_size <= 0:
        raise ValueError("chunk_size must be greater than overlap")

    chunks = []

    for index, start in enumerate(range(0, len(words), step_size), start=1):
        end = start + chunk_size
        chunk_words = words[start:end]

        if not chunk_words:
            continue

        chunk_text_value = " ".join(chunk_words)

        chunks.append(
            {
                "id": f"chunk_{source_id}_{index:03}",
                "source_id": source_id,
                "chunk_index": index,
                "text": chunk_text_value,
                "word_count": len(chunk_words),
                "character_count": len(chunk_text_value),
                "start_word_index": start,
                "end_word_index": start + len(chunk_words)
            }
        )

    return chunks


def save_chunks(source_id: str, chunks):
    CHUNK_OUTPUT_FOLDER.mkdir(parents=True, exist_ok=True)

    output_path = CHUNK_OUTPUT_FOLDER / f"{source_id}.json"
    output_path.write_text(
        json.dumps(chunks, indent=2, ensure_ascii=False),
        encoding="utf-8"
    )

    return str(output_path)


def load_chunks(chunks_path: str):
    path = Path(chunks_path)

    if not path.exists():
        return []

    return json.loads(path.read_text(encoding="utf-8"))
