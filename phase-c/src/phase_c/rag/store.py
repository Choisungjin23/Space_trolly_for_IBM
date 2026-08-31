"""Local evidence store.

No external service and no embedding model: a keyword/overlap ranker over a
small curated corpus. The corpus is the asset here, not the retrieval
algorithm — every chunk is a source verified during Phase A calibration.

Ingest rejects any citation without a specific locator, so a citation can always
be checked by a human.
"""

import json
import re
from pathlib import Path

from phase_c.contracts.evidence import EvidenceChunk

CORPUS_DIR = Path(__file__).parent / "corpus"

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


class EvidenceStore:
    def __init__(self, chunks: list[EvidenceChunk]) -> None:
        self.chunks = chunks
        self._index = {
            chunk.id: _tokens(chunk.text) | _tokens(" ".join(chunk.keywords))
            for chunk in chunks
        }

    @classmethod
    def from_corpus(cls, directory: Path | None = None) -> "EvidenceStore":
        directory = directory or CORPUS_DIR
        chunks: list[EvidenceChunk] = []
        for path in sorted(directory.glob("*.json")):
            for raw in json.loads(path.read_text(encoding="utf-8")):
                chunk = EvidenceChunk.model_validate(raw)
                if not chunk.citation.locator.strip():
                    raise ValueError(
                        f"Evidence chunk {chunk.id!r} has no locator; a citation "
                        "must be checkable by a human."
                    )
                chunks.append(chunk)
        return cls(chunks)

    def search(
        self,
        query: str,
        *,
        limit: int = 3,
        document_types: set[str] | None = None,
    ) -> list[EvidenceChunk]:
        wanted = _tokens(query)
        if not wanted:
            return []
        scored = []
        for chunk in self.chunks:
            if document_types is not None and chunk.document_type not in document_types:
                continue
            overlap = len(wanted & self._index[chunk.id])
            if overlap:
                # Favour keyword hits, which are curated, over incidental prose.
                keyword_hits = len(wanted & _tokens(" ".join(chunk.keywords)))
                scored.append((overlap + 2 * keyword_hits, chunk.id, chunk))
        scored.sort(key=lambda row: (-row[0], row[1]))
        return [chunk for _, _, chunk in scored[:limit]]

    def get(self, chunk_id: str) -> EvidenceChunk:
        for chunk in self.chunks:
            if chunk.id == chunk_id:
                return chunk
        raise KeyError(chunk_id)

    def get_by_source_id(self, source_id: str) -> EvidenceChunk:
        for chunk in self.chunks:
            if chunk.citation.source_id == source_id:
                return chunk
        raise KeyError(source_id)
