"""文档解析与分块：Markdown / TXT（YAML front matter 元数据）。

PDF / Word 解析（Docling / PyMuPDF）在 P6 扩展，接口保持 parse_document(path)。
"""

from dataclasses import dataclass, field
from pathlib import Path

MAX_CHUNK_CHARS = 600
CHUNK_OVERLAP = 80


@dataclass
class ParsedDocument:
    title: str
    document_type: str
    equipment_type: str | None
    equipment_model: str | None
    version: str | None
    source_file: str
    sections: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class Chunk:
    index: int
    content: str
    section: str
    source_file: str


def _parse_front_matter(text: str) -> tuple[dict[str, str], str]:
    if not text.startswith("---"):
        return {}, text
    parts = text.split("---", 2)
    if len(parts) < 3:
        return {}, text
    meta: dict[str, str] = {}
    for line in parts[1].strip().splitlines():
        if ":" in line:
            key, _, value = line.partition(":")
            meta[key.strip()] = value.strip()
    return meta, parts[2].strip()


def _split_sections(body: str) -> list[tuple[str, str]]:
    sections: list[tuple[str, str]] = []
    current_heading = ""
    current_lines: list[str] = []
    for line in body.splitlines():
        if line.startswith("## "):
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = line[3:].strip()
            current_lines = []
        elif line.startswith("# "):
            if current_lines:
                sections.append((current_heading, "\n".join(current_lines).strip()))
            current_heading = line[2:].strip()
            current_lines = []
        else:
            current_lines.append(line)
    if current_lines:
        sections.append((current_heading, "\n".join(current_lines).strip()))
    return [(heading, text) for heading, text in sections if text]


def parse_document(path: Path) -> ParsedDocument:
    text = path.read_text(encoding="utf-8")
    meta, body = _parse_front_matter(text)
    sections = _split_sections(body)
    return ParsedDocument(
        title=meta.get("title") or path.stem,
        document_type=meta.get("document_type") or "other",
        equipment_type=meta.get("equipment_type") or None,
        equipment_model=meta.get("equipment_model") or None,
        version=meta.get("version") or None,
        source_file=path.name,
        sections=sections,
    )


def _split_long_text(text: str) -> list[str]:
    if len(text) <= MAX_CHUNK_CHARS:
        return [text]
    pieces: list[str] = []
    start = 0
    while start < len(text):
        end = min(start + MAX_CHUNK_CHARS, len(text))
        pieces.append(text[start:end])
        if end >= len(text):
            break
        start = end - CHUNK_OVERLAP
    return pieces


def chunk_document(doc: ParsedDocument) -> list[Chunk]:
    chunks: list[Chunk] = []
    for heading, text in doc.sections:
        paragraphs = [p.strip() for p in text.split("\n\n") if p.strip()]
        buffer = ""
        for paragraph in paragraphs:
            candidate = f"{buffer}\n\n{paragraph}".strip() if buffer else paragraph
            if len(candidate) <= MAX_CHUNK_CHARS:
                buffer = candidate
                continue
            if buffer:
                chunks.append(_make_chunk(chunks, buffer, heading, doc.source_file))
            if len(paragraph) > MAX_CHUNK_CHARS:
                for piece in _split_long_text(paragraph):
                    chunks.append(_make_chunk(chunks, piece, heading, doc.source_file))
                buffer = ""
            else:
                buffer = paragraph
        if buffer:
            chunks.append(_make_chunk(chunks, buffer, heading, doc.source_file))
    return chunks


def _make_chunk(existing: list[Chunk], content: str, heading: str, source: str) -> Chunk:
    return Chunk(
        index=len(existing),
        content=content.strip(),
        section=heading,
        source_file=source,
    )
