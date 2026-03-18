"""Message fetching and indexing logic."""

import asyncio
from datetime import datetime

from phdkit.log import Logger, LogOutput
from telethon import TelegramClient
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
                    f"Error indexing chat {chat_id} in session {session_config.name}: {e}"
                )

        logger.info(
            "Indexing",
            f"Finished indexing session {session_config.name}: {total_indexed} messages"
        )

    async def _index_chat(
        self, client: TelegramClient, session_config: SessionConfig, chat_id: int | str
    ) -> int:
        """Index all messages from a single chat (supports both numeric IDs and usernames)."""
        logger.info("Indexing Chat", f"Chat {chat_id} for session {session_config.name}")

        batch_size = 100
        messages_batch: list[MessageDocument] = []
        total_count = 0

        try:
            # Get chat entity to get chat title (works with both IDs and usernames)
            entity = await client.get_entity(chat_id)

            # get_entity can return a list if multiple inputs given, but we pass single value
            assert not isinstance(entity, list), "Expected single entity from get_entity"

            chat_title = getattr(entity, "title", None) or getattr(
                entity, "first_name", None
            )

            # Get the numeric chat ID for indexing
            # entity.id is always available for all entity types
            numeric_chat_id: int = entity.id

            async for message in client.iter_messages(entity):
                if not isinstance(message, Message):
                    continue

                # Only index messages with text (use .message for base compatibility)
                text_content = message.message if hasattr(message, "message") else None
                if not text_content:
                    continue

                # Get sender ID from from_id attribute
                sender_id = None
                if hasattr(message, "from_id") and message.from_id:
                    # from_id is a Peer object (PeerUser, PeerChat, PeerChannel)
                    sender_id = getattr(message.from_id, "user_id", None) or getattr(
                        message.from_id, "channel_id", None
                    ) or getattr(message.from_id, "chat_id", None)

                # Get sender name
                sender_name = None
                try:
                    # Use the patched get_sender method if available
                    if hasattr(message, "get_sender"):
                        sender = await message.get_sender() # type: ignore
                        if sender:
                            first_name = getattr(sender, "first_name", None)
                            if first_name:
                                last_name = getattr(sender, "last_name", None)
                                if last_name:
                                    sender_name = f"{first_name} {last_name}"
                                else:
                                    sender_name = first_name
                            elif hasattr(sender, "title"):
                                sender_name = sender.title
                except Exception:
                    # Sender might not be accessible
                    pass

                # Create document
                doc = MessageDocument(
                    id=f"{session_config.name}:{numeric_chat_id}:{message.id}",
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
                total_count += 1

                # Index in batches
                if len(messages_batch) >= batch_size:
                    self.search_manager.index_messages(messages_batch)
                    logger.info(
                        "Indexing Batch",
                        f"Indexed batch of {len(messages_batch)} messages from chat {chat_id}"
                    )
                    messages_batch = []

            # Index remaining messages
            if messages_batch:
                self.search_manager.index_messages(messages_batch)
                logger.info(
                    "Indexing Batch",
                    f"Indexed final batch of {len(messages_batch)} messages from chat {chat_id}"
                )

            logger.info("Indexing Complete", f"Chat {chat_id}: {total_count} messages")
            return total_count

        except Exception as e:
            logger.error("Indexing Error", f"Error indexing chat {chat_id}: {e}")
            # Still index any messages we collected
            if messages_batch:
                self.search_manager.index_messages(messages_batch)
            return total_count

    async def index_all_sessions(
        self, clients: dict[str, TelegramClient]
    ) -> None:
        """Index all messages from all sessions."""
        logger.info("Indexing All", "Starting full indexing of all sessions...")

        tasks = []
        for session_config in self.config.sessions:
            client = clients.get(session_config.name)
            if not client:
                logger.error("Session Error", f"Client not found for session: {session_config.name}")
                continue

            tasks.append(self.index_session(client, session_config))

        await asyncio.gather(*tasks)
        logger.info("Indexing All", "Completed indexing all sessions")
