"""Evidence / RAG contract.

The Evidence agent answers "what does relevant real technical evidence say?" and
never decides anything. Applicability is mandatory: an ISS ventilation figure may
not transfer to a different vehicle, and ground-test combustion data does not
transfer to microgravity.
"""

from pydantic import BaseModel, Field


class EvidenceCitation(BaseModel):
    """A citation without a locator is rejected at corpus ingest."""

    source_id: str
    title: str
    locator: str  # page / section / table — must be specific
    retrieved_on: str = ""
    url: str = ""


class EvidenceChunk(BaseModel):
    id: str
    text: str
    citation: EvidenceCitation
    keywords: list[str] = Field(default_factory=list)


class EvidenceAnswer(BaseModel):
    query: str
    claim: str
    citation: EvidenceCitation
    applicability: str  # when this transfers to the scenario at hand, and when not
    limits: str = ""

    @property
    def ref_id(self) -> str:
        return f"evidence:{self.citation.source_id}"
