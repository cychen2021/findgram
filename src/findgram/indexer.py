"""Message fetching and indexing logic."""

import asyncio

from phdkit.log import Logger, LogOutput
from telethon import TelegramClient
from telethon.errors import FloodWaitError
from telethon.tl.types import Message

from .config import Config, SessionConfig
from .search import MessageDocument, MeiliSearchManager

logger = Logger(__name__, outputs=[LogOutput.stdout()])


class MessageIndexer:
    """Fetches messages from Telegram and indexes them."""

    def __init__(
        self,
        config: Config,
        search_manager: MeiliSearchManager,
    ):
        self.config = config
        self.search_manager = search_manager

    async def index_session(
        self, client: TelegramClient, session_config: SessionConfig
    ) -> None:
        """Index all messages for a single session."""
        logger.info("Indexing", f"Starting indexing for session: {session_config.name}")

        total_indexed = 0

        for chat_id in session_config.included_chats:
            try:
                count = await self._index_chat(client, session_config, chat_id)
                total_indexed += count
            except Exception as e:
                logger.error(
                    "Indexing Error",
                    f"Error indexing chat {chat_id} in session {session_config.name}: {e}",
                )

        logger.info(
            "Indexing",
            f"Finished indexing session {session_config.name}: {total_indexed} messages",
        )

    async def _index_chat(
        self, client: TelegramClient, session_config: SessionConfig, chat_id: int | str
    ) -> int:
        """Index all messages from a single chat (supports both numeric IDs and usernames)."""
        logger.info("Indexing Chat", f"[{session_config.name}] Starting chat {chat_id}")

        batch_size = 100
        messages_batch: list[MessageDocument] = []
        processed_count = 0
        indexed_count = 0
        first_message_id = None
        current_message_id = None
        index = None  # MeiliSearch index object

        # AIMD (Additive Increase Multiplicative Decrease) rate limiting
        delay = 0.1  # Start with 100ms delay
        min_delay = 0.1
        max_delay = 120.0  # Max 2 minutes
        additive_increase = 0.1  # Decrease by 100ms on success
        multiplicative_decrease = 2.0  # Double delay on rate limit

        try:
            # Get initial document count for this session
            logger.info(
                "Indexing Chat",
                f"[{session_config.name}] Getting document count from MeiliSearch",
            )
            initial_doc_count = self.search_manager.get_document_count()
            logger.info(
                "Indexing Chat",
                f"[{session_config.name}] Current index has {initial_doc_count} documents",
            )

            # Get index object once and reuse it to avoid repeated HTTP calls
            logger.info(
                "Indexing Chat",
                f"[{session_config.name}] Getting MeiliSearch index object",
            )
            index = self.search_manager.get_index()
            logger.info(
                "Indexing Chat",
                f"[{session_config.name}] Index object obtained",
            )

            # Get chat entity to get chat title (works with both IDs and usernames)
            logger.info(
                "Indexing Chat",
                f"[{session_config.name}] Fetching entity for {chat_id}",
            )
            entity = await client.get_entity(chat_id)
            logger.info(
                "Indexing Chat", f"[{session_config.name}] Entity fetched successfully"
            )

            # get_entity can return a list if multiple inputs given, but we pass single value
            assert not isinstance(entity, list), (
                "Expected single entity from get_entity"
            )

            chat_title = getattr(entity, "title", None) or getattr(
                entity, "first_name", None
            )

            # Get the numeric chat ID for indexing
            # entity.id is always available for all entity types
            numeric_chat_id: int = entity.id

            logger.info(
                "Indexing Chat",
                f"[{session_config.name}] Starting message iteration for {chat_id}",
            )

            message_count = 0
            consecutive_timeouts = 0
            max_consecutive_timeouts = 11

            # Wrap iterator to add timeout per message
            message_iterator = client.iter_messages(entity)

            while True:
                try:
                    # Log before attempting to fetch
                    if message_count % 100 == 0 and message_count > 0:
                        logger.info(
                            "Fetch Debug",
                            f"[{session_config.name}] About to fetch message #{message_count + 1}",
                        )

                    # 10 second timeout per message fetch
                    message = await asyncio.wait_for(
                        message_iterator.__anext__(), timeout=10.0
                    )

                    # Log after successful fetch
                    if message_count % 100 == 0 and message_count > 0:
                        logger.info(
                            "Fetch Debug",
                            f"[{session_config.name}] Successfully fetched message #{message_count + 1}",
                        )

                    consecutive_timeouts = 0  # Reset on success
                except asyncio.TimeoutError:
                    consecutive_timeouts += 1
                    logger.warning(
                        "Timeout Warning",
                        f"[{session_config.name}] Message fetch timeout (10s) at message {message_count} (timeout #{consecutive_timeouts})",
                    )
                    if consecutive_timeouts >= max_consecutive_timeouts:
                        logger.error(
                            "Timeout Error",
                            f"[{session_config.name}] Too many consecutive timeouts ({max_consecutive_timeouts}), stopping iteration for {chat_id}",
                        )
                        break
                    delay = min(max_delay, delay * multiplicative_decrease)
                    logger.info(
                        "Rate Limit",
                        f"[{session_config.name}] Backing off with delay: {delay:.2f}s",
                    )
                    await asyncio.sleep(delay)
                    continue
                except StopAsyncIteration:
                    # Iterator finished normally
                    break
                try:
                    message_count += 1

                    # Log every 500 messages to track progress
                    if message_count % 500 == 0:
                        logger.info(
                            "Iteration Progress",
                            f"[{session_config.name}] Fetched {message_count} messages from Telegram API",
                        )

                    # Track message IDs for progress estimation (newest to oldest)
                    if first_message_id is None:
                        first_message_id = message.id
                    current_message_id = message.id

                    if not isinstance(message, Message):
                        continue

                    # Only index messages with text (use .message for base compatibility)
                    text_content = (
                        message.message if hasattr(message, "message") else None
                    )
                    if not text_content:
                        continue

                    processed_count += 1

                    # Create document ID
                    doc_id = f"{session_config.name}:{numeric_chat_id}:{message.id}"

                    # Get sender ID from from_id attribute (fast, no API call)
                    sender_id = None
                    if hasattr(message, "from_id") and message.from_id:
                        # from_id is a Peer object (PeerUser, PeerChat, PeerChannel)
                        sender_id = (
                            getattr(message.from_id, "user_id", None)
                            or getattr(message.from_id, "channel_id", None)
                            or getattr(message.from_id, "chat_id", None)
                        )

                    # Skip fetching sender name - it can be slow and cause rate limiting
                    # We already have sender_id which is more reliable
                    sender_name = None

                    # Create document
                    doc = MessageDocument(
                        id=doc_id,
                        chat_id=numeric_chat_id,
                        message_id=message.id,
                        session_name=session_config.name,
                        text=text_content,
                        sender_id=sender_id,
                        sender_name=sender_name,
                        date=int(message.date.timestamp()) if message.date else 0,
                        chat_title=chat_title,
                    )

                    messages_batch.append(doc)
                    indexed_count += 1

                    # Index in batches
                    if len(messages_batch) >= batch_size:
                        logger.info(
                            "Batch Debug",
                            f"[{session_config.name}] About to index batch of {len(messages_batch)} messages",
                        )
                        self.search_manager.index_messages(messages_batch, index=index)
                        logger.info(
                            "Batch Debug",
                            f"[{session_config.name}] Batch submitted to MeiliSearch",
                        )
                        # Estimate progress using message IDs (they decrease as we go back in time)
                        if (
                            first_message_id
                            and current_message_id
                            and first_message_id > 0
                        ):
                            progress_pct = (
                                (first_message_id - current_message_id)
                                / first_message_id
                            ) * 100
                            logger.info(
                                "Indexing Progress",
                                f"[{session_config.name}] Chat {chat_id}: Processed {processed_count} text messages (~{progress_pct:.1f}% complete) - indexed {indexed_count} (delay: {delay:.2f}s)",
                            )
                        else:
                            logger.info(
                                "Indexing Progress",
                                f"[{session_config.name}] Chat {chat_id}: Processed {processed_count} text messages - indexed {indexed_count} (delay: {delay:.2f}s)",
                            )
                        messages_batch = []

                        # Apply AIMD delay
                        logger.info(
                            "Batch Debug",
                            f"[{session_config.name}] Sleeping for {delay:.2f}s before next batch",
                        )
                        await asyncio.sleep(delay)
                        logger.info(
                            "Batch Debug",
                            f"[{session_config.name}] Sleep completed, continuing iteration",
                        )

                        # Additive increase - gradually speed up if no errors
                        delay = max(min_delay, delay - additive_increase)

                except FloodWaitError as e:
                    # Telegram rate limit hit - back off
                    wait_time = e.seconds
                    logger.warning(
                        "Rate Limit",
                        f"[{session_config.name}] FloodWaitError: waiting {wait_time}s",
                    )
                    await asyncio.sleep(wait_time)
                    # Multiplicative decrease - slow down significantly
                    delay = min(max_delay, delay * multiplicative_decrease)
                    logger.info("Rate Limit", f"Increased delay to {delay:.2f}s")
                except Exception as e:
                    logger.error(
                        "Message Error",
                        f"[{session_config.name}] Error processing message {current_message_id}: {e}",
                    )
                    # Moderate increase on other errors
                    delay = min(max_delay, delay * 1.5)
                    continue

            logger.info(
                "Indexing Chat",
                f"[{session_config.name}] Finished iterating messages for {chat_id}, total fetched: {message_count}",
            )

            # Index remaining messages
            if messages_batch:
                logger.info(
                    "Indexing Chat",
                    f"[{session_config.name}] Indexing final batch of {len(messages_batch)} messages",
                )
                self.search_manager.index_messages(messages_batch, index=index)

            # Get final document count to see how many were actually new
            # Note: There may be a delay before MeiliSearch finishes indexing
            await asyncio.sleep(0.5)  # Give MeiliSearch time to process
            final_doc_count = self.search_manager.get_document_count()
            new_docs = final_doc_count - initial_doc_count
            already_indexed = indexed_count - new_docs

            logger.info(
                "Indexing Complete",
                f"[{session_config.name}] Chat {chat_id}: Processed {processed_count} text messages - {new_docs} new, {already_indexed} already indexed",
            )
            return indexed_count

        except FloodWaitError as e:
            logger.error(
                "Rate Limit",
                f"[{session_config.name}] Chat-level FloodWaitError for {chat_id}: need to wait {e.seconds}s",
            )
            # Still index any messages we collected
            if messages_batch and index is not None:
                try:
                    self.search_manager.index_messages(messages_batch, index=index)
                except Exception:
                    pass  # Best effort
            return indexed_count
        except Exception as e:
            logger.error(
                "Indexing Error",
                f"[{session_config.name}] Error indexing chat {chat_id}: {type(e).__name__}: {e}",
            )
            import traceback

            logger.error("Traceback", traceback.format_exc())
            # Still index any messages we collected
            if messages_batch and index is not None:
                try:
                    self.search_manager.index_messages(messages_batch, index=index)
                except Exception:
                    pass  # Best effort
            return indexed_count

    async def index_all_sessions(self, clients: dict[str, TelegramClient]) -> None:
        """Index all messages from all sessions."""
        logger.info("Indexing All", "Starting full indexing of all sessions...")

        tasks = []
        for session_config in self.config.sessions:
            client = clients.get(session_config.name)
            if not client:
                logger.error(
                    "Session Error",
                    f"Client not found for session: {session_config.name}",
                )
                continue

            tasks.append(self.index_session(client, session_config))

        await asyncio.gather(*tasks)
        logger.info("Indexing All", "Completed indexing all sessions")
