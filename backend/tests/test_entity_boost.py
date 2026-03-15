"""Tests for Phase 6 entity-direct query boosting (LightRAG-style)."""
from __future__ import annotations

import json
import sqlite3
import uuid
from unittest.mock import MagicMock, patch

import pytest

from memory.hybrid import SearchResult
from memory.manager import MemoryIndexManager
from memory.schema import SCHEMA_SQL


# ── Fixtures ──────────────────────────────────────────────────────────────────

@pytest.fixture
def db():
    conn = sqlite3.connect(":memory:", check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON")
    with conn:
        conn.executescript(SCHEMA_SQL)
    yield conn
    conn.close()


@pytest.fixture
def manager(db):
    mock_emb = MagicMock()
    mock_emb.provider_id = "mock"
    mock_emb.model = "mock"
    mock_llm = MagicMock()
    mock_vs = MagicMock()
    return MemoryIndexManager(
        db=db,
        embedding_provider=mock_emb,
        llm_provider=mock_llm,
        vector_store=mock_vs,
        entity_boost_enabled=True,
    )


def _seed_project(db) -> str:
    project_id = str(uuid.uuid4())
    with db:
        db.execute(
            "INSERT INTO projects (id, name) VALUES (?, ?)",
            (project_id, "Test Project"),
        )
    return project_id


def _seed_document(db, project_id: str) -> str:
    doc_id = str(uuid.uuid4())
    with db:
        db.execute(
            "INSERT INTO documents (id, filename, source_type, size_bytes, project_id)"
            " VALUES (?, 'test.txt', 'upload', 0, ?)",
            (doc_id, project_id),
        )
    return doc_id


def _seed_chunk(db, doc_id: str, text: str = "Sample text.") -> str:
    chunk_id = f"{doc_id}__p1__c0"
    with db:
        db.execute(
            "INSERT INTO chunks (id, doc_id, page_number, chunk_index, text, token_count)"
            " VALUES (?, ?, 1, 0, ?, 10)",
            (chunk_id, doc_id, text),
        )
    return chunk_id


def _seed_entity(db, project_id: str, entity_name: str, chunk_ids: list[str]) -> str:
    entity_id = str(uuid.uuid4())
    with db:
        db.execute(
            "INSERT INTO project_entities"
            " (id, project_id, entity_name, entity_type, synonyms, source_chunk_ids, occurrence_count)"
            " VALUES (?, ?, ?, 'concept', '[]', ?, 1)",
            (entity_id, project_id, entity_name, json.dumps(chunk_ids)),
        )
    return entity_id


# ── Tests ─────────────────────────────────────────────────────────────────────

def test_entity_boost_returns_chunks_for_named_entity(db, manager):
    """_entity_boost_candidates returns SearchResults when a NER hit matches project entities."""
    project_id = _seed_project(db)
    doc_id = _seed_document(db, project_id)
    chunk_id = _seed_chunk(db, doc_id, "Apple is a technology company.")
    _seed_entity(db, project_id, "apple", [chunk_id])

    # Patch spaCy to return a predictable NER result
    mock_ent = MagicMock()
    mock_ent.text = "Apple"
    mock_doc = MagicMock()
    mock_doc.ents = [mock_ent]
    mock_doc.noun_chunks = []
    mock_nlp = MagicMock(return_value=mock_doc)

    with patch("memory.manager._get_spacy_nlp", return_value=mock_nlp):
        results = manager._entity_boost_candidates("Tell me about Apple", project_id)

    assert len(results) == 1
    assert results[0].chunk_id == chunk_id


def test_entity_boost_returns_empty_when_no_project_entities(db, manager):
    """_entity_boost_candidates returns [] when no entities are stored for the project."""
    project_id = _seed_project(db)
    # No entities seeded

    mock_ent = MagicMock()
    mock_ent.text = "Google"
    mock_doc = MagicMock()
    mock_doc.ents = [mock_ent]
    mock_doc.noun_chunks = []
    mock_nlp = MagicMock(return_value=mock_doc)

    with patch("memory.manager._get_spacy_nlp", return_value=mock_nlp):
        results = manager._entity_boost_candidates("Tell me about Google", project_id)

    assert results == []


def test_entity_boost_returns_empty_when_spacy_unavailable(db, manager):
    """_entity_boost_candidates returns [] gracefully when spaCy is not available."""
    project_id = _seed_project(db)
    doc_id = _seed_document(db, project_id)
    chunk_id = _seed_chunk(db, doc_id)
    _seed_entity(db, project_id, "tensorflow", [chunk_id])

    with patch("memory.manager._get_spacy_nlp", return_value=None):
        results = manager._entity_boost_candidates("Tell me about TensorFlow", project_id)

    assert results == []


def test_high_level_entity_traversal_follows_relations(db, manager):
    """_entity_high_level_candidates follows one-hop relations and surfaces related chunks."""
    project_id = _seed_project(db)
    doc_id = _seed_document(db, project_id)

    chunk_a = _seed_chunk(db, doc_id, "PyTorch is a deep learning framework.")
    chunk_b_id = f"{doc_id}__p1__c1"
    with db:
        db.execute(
            "INSERT INTO chunks (id, doc_id, page_number, chunk_index, text, token_count)"
            " VALUES (?, ?, 1, 1, 'TensorFlow is also a deep learning framework.', 10)",
            (chunk_b_id, doc_id),
        )

    entity_a_id = _seed_entity(db, project_id, "pytorch", [chunk_a])
    entity_b_id = _seed_entity(db, project_id, "tensorflow", [chunk_b_id])

    # Create a relation between entity_a and entity_b
    rel_id = str(uuid.uuid4())
    with db:
        db.execute(
            "INSERT INTO project_entity_relations"
            " (id, project_id, entity_a_id, relation, entity_b_id, source_chunk_ids, confidence)"
            " VALUES (?, ?, ?, 'mentioned_alongside', ?, ?, 0.9)",
            (rel_id, project_id, entity_a_id, entity_b_id, json.dumps([chunk_b_id])),
        )

    results = manager._entity_high_level_candidates(
        "What deep learning frameworks exist?", project_id, [entity_a_id]
    )

    assert len(results) >= 1
    returned_ids = {r.chunk_id for r in results}
    assert chunk_b_id in returned_ids


def test_high_level_entity_returns_empty_for_no_relations(db, manager):
    """_entity_high_level_candidates returns [] when no relations exist."""
    project_id = _seed_project(db)
    doc_id = _seed_document(db, project_id)
    chunk_id = _seed_chunk(db, doc_id)
    entity_id = _seed_entity(db, project_id, "pytorch", [chunk_id])

    # No relations seeded
    results = manager._entity_high_level_candidates(
        "What is PyTorch?", project_id, [entity_id]
    )

    assert results == []
