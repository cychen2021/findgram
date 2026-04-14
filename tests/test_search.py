"""Tests for TantivySearchManager."""

import asyncio
import tempfile
from pathlib import Path

import pytest

from findgram.config import SearchConfig
from findgram.search import MessageDocument, TantivySearchManager


@pytest.fixture
def search_config(tmp_path):
    """Create a SearchConfig with a temporary index path."""
    return SearchConfig(index_path=str(tmp_path / "test_index"))


@pytest.fixture
def search_manager(search_config):
    """Create and start a TantivySearchManager."""
    manager = TantivySearchManager(search_config)
    manager.start()
    yield manager
    manager.stop()


def make_doc(
    id="s1:100:1",
    chat_id=100,
    message_id=1,
    session_name="s1",
    text="hello world",
    sender_id=42,
    sender_name="Alice",
    receiver_name="Bob",
    date=1700000000,
    chat_title="Test Chat",
):
    return MessageDocument(
        id=id,
        chat_id=chat_id,
        message_id=message_id,
        session_name=session_name,
        text=text,
        sender_id=sender_id,
        sender_name=sender_name,
        receiver_name=receiver_name,
        date=date,
        chat_title=chat_title,
    )


class TestTantivySearchManager:
    def test_start_creates_index(self, search_config):
        manager = TantivySearchManager(search_config)
        manager.start()
        assert manager.index is not None
        assert manager.writer is not None
        index_path = Path(search_config.index_path)
        assert index_path.exists()
        manager.stop()

    def test_index_and_search_basic(self, search_manager):
        doc = make_doc(text="finding telegram messages")
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages([doc])
        )
        results = search_manager.search("telegram")
        assert len(results) == 1
        assert results[0]["text"] == "finding telegram messages"

    def test_search_chinese_text(self, search_manager):
        doc = make_doc(id="s1:100:2", text="今天天气真好", message_id=2)
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages([doc])
        )
        results = search_manager.search("天气")
        assert len(results) == 1
        assert results[0]["text"] == "今天天气真好"

    def test_search_no_results(self, search_manager):
        doc = make_doc(text="hello world")
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages([doc])
        )
        results = search_manager.search("nonexistent")
        assert len(results) == 0

    def test_document_exists(self, search_manager):
        doc = make_doc(id="s1:100:5", text="test message")
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages([doc])
        )
        assert search_manager.document_exists("s1:100:5") is True
        assert search_manager.document_exists("s1:100:999") is False

    def test_get_document_count(self, search_manager):
        assert search_manager.get_document_count() == 0
        docs = [
            make_doc(id=f"s1:100:{i}", message_id=i, text=f"message {i}")
            for i in range(5)
        ]
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages(docs)
        )
        assert search_manager.get_document_count() == 5

    def test_search_with_session_filter(self, search_manager):
        docs = [
            make_doc(id="s1:100:1", session_name="s1", text="shared keyword"),
            make_doc(id="s2:200:2", session_name="s2", text="shared keyword", message_id=2, chat_id=200),
        ]
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages(docs)
        )
        results = search_manager.search("shared keyword", filters={"session_name": "s1"})
        assert len(results) == 1
        assert results[0]["session_name"] == "s1"

    def test_search_returns_correct_fields(self, search_manager):
        doc = make_doc(
            id="s1:100:1",
            chat_id=100,
            message_id=1,
            session_name="s1",
            text="test message content",
            sender_id=42,
            sender_name="Alice",
            receiver_name="Bob",
            date=1700000000,
            chat_title="Test Chat",
        )
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages([doc])
        )
        results = search_manager.search("test message")
        assert len(results) == 1
        r = results[0]
        assert r["id"] == "s1:100:1"
        assert r["chat_id"] == 100
        assert r["message_id"] == 1
        assert r["session_name"] == "s1"
        assert r["text"] == "test message content"
        assert r["sender_id"] == 42
        assert r["sender_name"] == "Alice"
        assert r["receiver_name"] == "Bob"
        assert r["date"] == 1700000000

    def test_index_single_message_searchable_immediately(self, search_manager):
        """Simulate live indexing: a single message should be searchable right after indexing."""
        doc = make_doc(id="s1:100:99", text="live indexed message", message_id=99)
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages([doc])
        )
        results = search_manager.search("live indexed")
        assert len(results) == 1
        assert results[0]["message_id"] == 99

    def test_incremental_indexing(self, search_manager):
        """Messages indexed in separate batches should all be searchable."""
        doc1 = make_doc(id="s1:100:1", text="first batch message", message_id=1)
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages([doc1])
        )

        doc2 = make_doc(id="s1:100:2", text="second batch message", message_id=2)
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages([doc2])
        )

        results = search_manager.search("batch message")
        assert len(results) == 2

    def test_search_results_sorted_by_date_desc(self, search_manager):
        docs = [
            make_doc(id="s1:100:1", text="keyword match", date=1000, message_id=1),
            make_doc(id="s1:100:2", text="keyword match", date=3000, message_id=2),
            make_doc(id="s1:100:3", text="keyword match", date=2000, message_id=3),
        ]
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages(docs)
        )
        results = search_manager.search("keyword match")
        dates = [r["date"] for r in results]
        assert dates == sorted(dates, reverse=True)

    def test_search_by_sender_name(self, search_manager):
        doc = make_doc(text="some random content", sender_name="UniqueNameXyz")
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages([doc])
        )
        results = search_manager.search("UniqueNameXyz")
        assert len(results) == 1

    def test_empty_batch_returns_zero(self, search_manager):
        result = asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages([])
        )
        assert result == 0.0

    def test_index_message_without_optional_fields(self, search_manager):
        doc = make_doc(sender_id=None, sender_name=None, receiver_name=None, chat_title=None)
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages([doc])
        )
        results = search_manager.search("hello world")
        assert len(results) == 1


class TestFetchContext:
    def test_fetch_context_basic(self, search_manager):
        """Context returns adjacent messages sorted by message_id."""
        docs = [
            make_doc(id=f"s1:100:{i}", message_id=i, text=f"msg {i}", date=1700000000 + i)
            for i in range(1, 6)
        ]
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages(docs)
        )
        # Hit is message 3, preceding=2, subsequent=2 → should get messages 1-5
        hit = {"chat_id": 100, "session_name": "s1", "message_id": 3}
        result = search_manager.fetch_context(hit, preceding=2, subsequent=2)
        msg_ids = [r["message_id"] for r in result]
        assert msg_ids == [1, 2, 3, 4, 5]

    def test_fetch_context_with_gaps(self, search_manager):
        """Gaps in message_ids are handled naturally."""
        docs = [
            make_doc(id=f"s1:100:{i}", message_id=i, text=f"msg {i}", date=1700000000 + i)
            for i in [1, 2, 5, 6, 7]
        ]
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages(docs)
        )
        # Hit is message 5, preceding=2, subsequent=2 → range [3, 7], existing: 5, 6, 7
        hit = {"chat_id": 100, "session_name": "s1", "message_id": 5}
        result = search_manager.fetch_context(hit, preceding=2, subsequent=2)
        msg_ids = [r["message_id"] for r in result]
        assert msg_ids == [5, 6, 7]

    def test_fetch_context_cross_chat_isolation(self, search_manager):
        """Context only returns messages from the same chat."""
        docs = [
            make_doc(id="s1:100:1", chat_id=100, message_id=1, text="chat A msg 1"),
            make_doc(id="s1:100:2", chat_id=100, message_id=2, text="chat A msg 2"),
            make_doc(id="s1:100:3", chat_id=100, message_id=3, text="chat A msg 3"),
            make_doc(id="s1:200:2", chat_id=200, message_id=2, text="chat B msg 2"),
        ]
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages(docs)
        )
        hit = {"chat_id": 100, "session_name": "s1", "message_id": 2}
        result = search_manager.fetch_context(hit, preceding=1, subsequent=1)
        msg_ids = [r["message_id"] for r in result]
        assert msg_ids == [1, 2, 3]
        assert all(r["chat_id"] == 100 for r in result)

    def test_fetch_context_cross_session_isolation(self, search_manager):
        """Context only returns messages from the same session."""
        docs = [
            make_doc(id="s1:100:1", session_name="s1", message_id=1, text="s1 msg 1"),
            make_doc(id="s1:100:2", session_name="s1", message_id=2, text="s1 msg 2"),
            make_doc(id="s2:100:2", session_name="s2", chat_id=100, message_id=2, text="s2 msg 2"),
        ]
        asyncio.get_event_loop().run_until_complete(
            search_manager.index_messages(docs)
        )
        hit = {"chat_id": 100, "session_name": "s1", "message_id": 2}
        result = search_manager.fetch_context(hit, preceding=1, subsequent=1)
        assert all(r["session_name"] == "s1" for r in result)

    def test_fetch_context_zero_returns_only_hit(self, search_manager):
        """preceding=0, subsequent=0 returns the hit as-is without querying."""
        hit = {"chat_id": 100, "session_name": "s1", "message_id": 5, "text": "matched"}
        result = search_manager.fetch_context(hit, preceding=0, subsequent=0)
        assert result == [hit]
