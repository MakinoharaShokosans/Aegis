"""Sample python module for fallback and heuristic splitting."""

from dataclasses import dataclass


@dataclass
class Document:
    doc_id: str
    text: str


def format_document(doc: Document) -> str:
    """Format document to readable text."""
    return f"[{doc.doc_id}] {doc.text}"
