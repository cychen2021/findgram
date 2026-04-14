"""Tantivy integration for message indexing and searching."""

import asyncio
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import jieba
import tantivy
from phdkit.log import Logger, LogOutput

from .config import SearchConfig, get_data_dir

logger = Logger(__name__, outputs=[LogOutput.stdout()])


@dataclass
class MessageDocument:
    """Represents a message document for indexing."""

    id: str
    chat_id: int  # Always numeric ID
    message_id: int
    session_name: str
    text: str
    sender_id: int | None
    sender_name: str | None
    receiver_name: str | None
    date: int  # Unix timestamp
    chat_title: str | None


class TantivySearchManager:
    """Manages Tantivy index and message searching with jieba tokenization."""

    def __init__(self, config: SearchConfig):
        self.config = config
        self.index: tantivy.Index | None = None
        self.writer: tantivy.IndexWriter | None = None
        self._executor = ThreadPoolExecutor(max_workers=1)

        # Initialize jieba (load dictionary once)
        jieba.initialize()

    def _get_index_path(self) -> Path:
        """Get the path to the Tantivy index directory."""
        if self.config.index_path:
            return Path(self.config.index_path)
        else:
            return get_data_dir() / "tantivy_index"

    def start(self) -> None:
        """Initialize or open the Tantivy index."""
        index_path = self._get_index_path()
        index_path.mkdir(parents=True, exist_ok=True)

        logger.info("Tantivy", f"Opening index at {index_path}")

        # Define schema
        schema_builder = tantivy.SchemaBuilder()
        schema_builder.add_text_field("id", stored=True, tokenizer_name="raw")
        schema_builder.add_integer_field("chat_id", stored=True, indexed=True)
        schema_builder.add_integer_field("message_id", stored=True, indexed=True)
        schema_builder.add_text_field("session_name", stored=True, tokenizer_name="raw")
        schema_builder.add_text_field(
            "text", stored=False, tokenizer_name="default"
        )  # Tokenized for search only
        schema_builder.add_text_field(
            "text_original", stored=True, tokenizer_name="raw"
        )  # Original text for display
        schema_builder.add_integer_field("sender_id", stored=True, indexed=True)
        schema_builder.add_text_field("sender_name", stored=True, tokenizer_name="raw")
        schema_builder.add_text_field(
            "receiver_name", stored=True, tokenizer_name="raw"
        )
        schema_builder.add_integer_field("date", stored=True, indexed=True)
        schema_builder.add_text_field(
            "chat_title", stored=True, tokenizer_name="default"
        )
        schema = schema_builder.build()

        # Try to open existing index
        try:
            self.index = tantivy.Index(schema, str(index_path))
            logger.info("Tantivy", "Opened existing index")
        except Exception:
            # Create new index if it doesn't exist
            self.index = tantivy.Index(schema, str(index_path), reuse=False)
            logger.info("Tantivy", "Created new index")

        # Create writer with 128MB heap
        self.writer = self.index.writer(heap_size=128_000_000)
        logger.info("Tantivy", "Index writer created")

    def stop(self) -> None:
        """Cleanup resources."""
        self._executor.shutdown(wait=True)

        if self.writer:
            # Commit any pending changes
            try:
                self.writer.commit()
            except Exception as e:
                logger.warning("Tantivy", f"Error committing on shutdown: {e}")

        logger.info("Tantivy", "Search manager stopped")

    def get_index(self):
        """Get the Tantivy index object (for compatibility with old interface)."""
        if not self.index:
            raise RuntimeError("Tantivy index not initialized")
        return self.index

    def refresh_client(self) -> None:
        """Refresh index (reload for search - for compatibility with old interface)."""
        if not self.index:
            raise RuntimeError("Tantivy index not initialized")
        self.index.reload()
        logger.info("Tantivy", "Index reloaded")

    def get_document_count(self) -> int:
        """Get the total number of documents in the index."""
        if not self.index:
            raise RuntimeError("Tantivy index not initialized")

        try:
            searcher = self.index.searcher()
            return searcher.num_docs
        except Exception as e:
            logger.warning("Tantivy", f"Error getting document count: {e}")
            return 0

    def _tokenize_chinese(self, text: str) -> str:
        """Tokenize Chinese text using jieba."""
        # jieba.cut returns an iterator of words
        words = jieba.cut_for_search(text)
        return " ".join(words)

    async def index_messages(
        self, messages: list[MessageDocument], index=None, timeout: int = 30
    ) -> float:
        """Index a batch of messages.

        Args:
            messages: List of messages to index
            index: Ignored (for compatibility with old interface)
            timeout: Timeout in seconds (not currently used)

        Returns:
            Response time in seconds for the indexing operation.
        """
        if not self.writer:
            raise RuntimeError("Tantivy writer not initialized")

        if not messages:
            return 0.0

        start_time = time.time()

        logger.info("Tantivy", f"Indexing {len(messages)} documents...")

        # Index documents in thread pool
        loop = asyncio.get_event_loop()

        def do_indexing():
            for msg in messages:
                # Tokenize text with jieba for better Chinese support
                tokenized_text = self._tokenize_chinese(msg.text)

                doc = tantivy.Document()
                doc.add_text("id", msg.id)
                doc.add_integer("chat_id", msg.chat_id)
                doc.add_integer("message_id", msg.message_id)
                doc.add_text("session_name", msg.session_name)
                doc.add_text("text", tokenized_text)  # Tokenized for search
                doc.add_text("text_original", msg.text)  # Original text for display

                if msg.sender_id is not None:
                    doc.add_integer("sender_id", msg.sender_id)

                if msg.sender_name:
                    doc.add_text("sender_name", msg.sender_name)

                if msg.receiver_name:
                    doc.add_text("receiver_name", msg.receiver_name)

                doc.add_integer("date", msg.date)

                if msg.chat_title:
                    tokenized_title = self._tokenize_chinese(msg.chat_title)
                    doc.add_text("chat_title", tokenized_title)

                self.writer.add_document(doc)

            # Commit the batch
            self.writer.commit()

        await loop.run_in_executor(self._executor, do_indexing)

        response_time = time.time() - start_time

        logger.info("Tantivy", f"Indexed {len(messages)} docs in {response_time:.3f}s")

        # Reload index so new documents are searchable
        self.index.reload()

        return response_time

    def document_exists(self, doc_id: str) -> bool:
        """Check if a document with the given ID exists in the index."""
        if not self.index:
            return False
        try:
            searcher = self.index.searcher()
            query = self.index.parse_query(f'"{doc_id}"', ["id"])
            result = searcher.search(query, 1)
            return len(result.hits) > 0
        except Exception:
            return False

    def _doc_to_dict(self, doc) -> dict[str, Any]:
        """Convert a Tantivy document to a dict."""
        doc_dict: dict[str, Any] = {}
        field_names = [
            "id",
            "chat_id",
            "message_id",
            "session_name",
            "text_original",
            "sender_id",
            "sender_name",
            "receiver_name",
            "date",
            "chat_title",
        ]
        for field_name in field_names:
            try:
                values = doc.get_all(field_name)
                if values:
                    value = values[0]
                    if field_name in ["chat_id", "message_id", "sender_id", "date"]:
                        doc_dict[field_name] = value
                    elif field_name == "text_original":
                        doc_dict["text"] = str(value) if value is not None else None
                    else:
                        doc_dict[field_name] = (
                            str(value) if value is not None else None
                        )
            except Exception:
                pass
        return doc_dict

    def search(
        self, query: str, limit: int = 20, filters: dict[str, Any] | None = None
    ) -> list[dict[str, Any]]:
        """Search for messages.

        Args:
            query: Search query string
            limit: Maximum number of results to return
            filters: Optional filters (e.g., {"chat_id": 123, "session_name": "account1"})

        Returns:
            List of matching documents
        """
        if not self.index:
            raise RuntimeError("Tantivy index not initialized")

        searcher = self.index.searcher()

        # Tokenize query with jieba, preserving user-intended grouping:
        # Split by whitespace first, tokenize each part, AND tokens within each part,
        # then OR the parts together.
        # e.g. "印度气候 日本气候" → "(印度 AND 气候) OR (日本 AND 气候)"
        parts = query.split()
        tokenized_parts = []
        for part in parts:
            tokens = list(jieba.cut_for_search(part))
            # Keep only tokens containing at least one alphanumeric or CJK character
            # to avoid passing punctuation/symbols to Tantivy's query parser
            tokens = [
                t.strip()
                for t in tokens
                if t.strip()
                and any(c.isalnum() or "\u4e00" <= c <= "\u9fff" for c in t)
            ]
            if tokens:
                tokenized_parts.append("(" + " AND ".join(tokens) + ")")

        if not tokenized_parts:
            tokenized_query = query
        elif len(tokenized_parts) == 1:
            tokenized_query = tokenized_parts[0]
        else:
            tokenized_query = " OR ".join(tokenized_parts)

        # Build query string for searching text, sender_name, and chat_title fields
        query_str = f"text:({tokenized_query}) OR sender_name:({tokenized_query}) OR chat_title:({tokenized_query})"

        logger.info("Search Query", f"Base query string: {query_str}")

        # Parse the base query
        parsed_query = self.index.parse_query(
            query_str, ["text", "sender_name", "chat_title"]
        )

        # Apply filters if provided - use post-filtering on results
        if filters:
            logger.info("Search Filters", f"Applying filters: {filters}")

        # Search with a higher limit if we need to filter
        search_limit = limit * 10 if filters else limit
        search_result = searcher.search(parsed_query, search_limit)

        # Convert results to dict format (compatible with old interface)
        results = []
        for score, doc_address in search_result.hits:
            doc = searcher.doc(doc_address)
            doc_dict = self._doc_to_dict(doc)

            # Apply post-filtering if filters provided
            if filters:
                match = True

                if "session_name" in filters:
                    if doc_dict.get("session_name") != filters["session_name"]:
                        logger.info(
                            "Search Filter",
                            f"Filtering out: session_name={doc_dict.get('session_name')} != {filters['session_name']}",
                        )
                        match = False

                if "chat_id" in filters and match:
                    if doc_dict.get("chat_id") != filters["chat_id"]:
                        match = False

                if "sender_id" in filters and match:
                    if doc_dict.get("sender_id") != filters["sender_id"]:
                        match = False

                if not match:
                    continue

            results.append(doc_dict)

            # Stop if we have enough results
            if len(results) >= limit:
                break

        # Sort by date descending (newest first)
        results.sort(key=lambda x: x.get("date", 0), reverse=True)

        return results

    def fetch_context(
        self, hit: dict[str, Any], context_size: int
    ) -> list[dict[str, Any]]:
        """Fetch context messages surrounding a search hit.

        Args:
            hit: A search result dict with chat_id, session_name, message_id.
            context_size: Number of messages before and after to fetch.

        Returns:
            List of message dicts sorted by message_id ascending,
            including the original hit itself.
        """
        if not self.index or context_size <= 0:
            return [hit]

        schema = self.index.schema
        searcher = self.index.searcher()

        msg_id = hit["message_id"]
        query = tantivy.Query.boolean_query([
            (tantivy.Occur.Must, tantivy.Query.term_query(
                schema, "chat_id", hit["chat_id"]
            )),
            (tantivy.Occur.Must, tantivy.Query.term_query(
                schema, "session_name", hit["session_name"],
                index_option="position"
            )),
            (tantivy.Occur.Must, tantivy.Query.range_query(
                schema, "message_id", tantivy.FieldType.Integer,
                msg_id - context_size, msg_id + context_size,
                include_lower=True, include_upper=True,
            )),
        ])

        search_result = searcher.search(query, 2 * context_size + 1)

        results = []
        for _score, doc_address in search_result.hits:
            doc = searcher.doc(doc_address)
            results.append(self._doc_to_dict(doc))

        results.sort(key=lambda x: x.get("message_id", 0))
        return results
