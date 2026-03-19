"""Tests for MessageIndexer - focusing on live message handler logic."""

import asyncio
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from findgram.config import Config, SearchConfig, SessionConfig
from findgram.indexer import MessageIndexer
from findgram.search import MessageDocument, TantivySearchManager


@pytest.fixture
def search_manager(tmp_path):
    config = SearchConfig(index_path=str(tmp_path / "test_index"))
    manager = TantivySearchManager(config)
    manager.start()
    yield manager
    manager.stop()


@pytest.fixture
def session_config():
    return SessionConfig(
        name="test_session",
        telegram_id=12345,
        included_chats=[-1001234567890, 98765, "@testuser"],
    )


@pytest.fixture
def config(session_config):
    return Config(
        app_id=1,
        app_hash="test",
        app_token="test",
        sessions=[session_config],
        search=SearchConfig(),
    )


class TestRegisterNewMessageHandler:
    def test_handler_registered_with_resolved_ids(self, config, search_manager, session_config):
        """Handler should be registered on the client with resolved numeric IDs."""
        indexer = MessageIndexer(config, search_manager)
        client = MagicMock()
        handlers = []

        def capture_on(event):
            def decorator(func):
                handlers.append((event, func))
                return func
            return decorator

        client.on = capture_on

        resolved_ids = [1234567890, 98765, 11111]
        indexer._register_new_message_handler(client, session_config, resolved_ids)
        assert len(handlers) == 1
        event_builder, callback = handlers[0]
        # The event builder should have been created with the resolved IDs
        assert event_builder.chats == resolved_ids

    def test_index_session_collects_resolved_ids(self, config, search_manager, session_config):
        """index_session should collect resolved numeric IDs and pass them to the handler."""
        indexer = MessageIndexer(config, search_manager)

        # Track calls to _register_new_message_handler
        register_calls = []
        original_register = indexer._register_new_message_handler

        def mock_register(client, sc, resolved_ids):
            register_calls.append(resolved_ids)

        indexer._register_new_message_handler = mock_register

        # Mock _index_chat to return (count, numeric_id)
        async def mock_index_chat(client, sc, chat_id):
            # Simulate resolving different chat types
            if isinstance(chat_id, str):
                return 10, 11111  # resolved username
            elif chat_id < 0:
                return 20, abs(chat_id) % 10000000000  # strip -100 prefix
            else:
                return 5, chat_id  # already numeric

        indexer._index_chat = mock_index_chat

        client = MagicMock()
        asyncio.get_event_loop().run_until_complete(
            indexer.index_session(client, session_config)
        )

        assert len(register_calls) == 1
        resolved_ids = register_calls[0]
        assert len(resolved_ids) == 3
        assert 11111 in resolved_ids  # from "@testuser"
        assert 1234567890 in resolved_ids  # from -1001234567890
        assert 98765 in resolved_ids  # from 98765

    def test_index_session_skips_handler_when_no_chats_resolved(self, config, search_manager, session_config):
        """If all chats fail to resolve, no handler should be registered."""
        indexer = MessageIndexer(config, search_manager)

        register_calls = []

        def mock_register(client, sc, resolved_ids):
            register_calls.append(resolved_ids)

        indexer._register_new_message_handler = mock_register

        async def mock_index_chat(client, sc, chat_id):
            raise Exception("Failed to resolve")

        indexer._index_chat = mock_index_chat

        client = MagicMock()
        asyncio.get_event_loop().run_until_complete(
            indexer.index_session(client, session_config)
        )

        # Handler should NOT be registered since all chats failed
        assert len(register_calls) == 0

    def test_index_session_partial_failure(self, config, search_manager, session_config):
        """If some chats fail, handler is still registered with successfully resolved chats."""
        indexer = MessageIndexer(config, search_manager)

        register_calls = []

        def mock_register(client, sc, resolved_ids):
            register_calls.append(resolved_ids)

        indexer._register_new_message_handler = mock_register

        call_count = 0

        async def mock_index_chat(client, sc, chat_id):
            nonlocal call_count
            call_count += 1
            if call_count == 2:  # fail on second chat
                raise Exception("Failed")
            return 5, 99999 + call_count

        indexer._index_chat = mock_index_chat

        client = MagicMock()
        asyncio.get_event_loop().run_until_complete(
            indexer.index_session(client, session_config)
        )

        assert len(register_calls) == 1
        assert len(register_calls[0]) == 2  # 2 out of 3 succeeded


class TestIndexChatReturnValue:
    def test_returns_tuple_with_numeric_id(self, config, search_manager, session_config):
        """_index_chat should return (count, numeric_chat_id) tuple."""
        indexer = MessageIndexer(config, search_manager)

        @dataclass
        class FakeEntity:
            id: int = 1234567890
            title: str = "Test"

        client = AsyncMock()
        client.get_entity = AsyncMock(return_value=FakeEntity())
        client.get_me = AsyncMock(return_value=FakeEntity(id=12345))

        # Create an empty async iterator
        async def empty_iter():
            return
            yield  # Make it a generator

        client.iter_messages = MagicMock(return_value=empty_iter())

        result = asyncio.get_event_loop().run_until_complete(
            indexer._index_chat(client, session_config, -1001234567890)
        )

        assert isinstance(result, tuple)
        count, numeric_id = result
        assert numeric_id == 1234567890
