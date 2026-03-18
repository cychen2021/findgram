"""Telegram client management for multiple sessions."""

from pathlib import Path

from phdkit.log import Logger, LogOutput
from telethon import TelegramClient
from telethon.sessions import StringSession

from .config import Config, SessionConfig, get_data_dir

logger = Logger(__name__, outputs=[LogOutput.stdout()])


class SessionManager:
    """Manages multiple Telegram sessions."""

    def __init__(self, config: Config):
        self.config = config
        self.clients: dict[str, TelegramClient] = {}
        self.session_dir = get_data_dir() / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)

    async def initialize_sessions(self) -> None:
        """Initialize all configured sessions."""
        for session_config in self.config.sessions:
            await self._initialize_session(session_config)

    async def _initialize_session(self, session_config: SessionConfig) -> None:
        """Initialize a single session."""
        session_file = self.session_dir / f"{session_config.name}.session"

        logger.info("Session Init", f"Initializing session: {session_config.name}")

        client = TelegramClient(
            str(session_file),
            self.config.app_id,
            self.config.app_hash,
        )

        await client.start(phone=str(session_config.telegram_id))

        if not await client.is_user_authorized():
            raise RuntimeError(
                f"Session {session_config.name} is not authorized. "
                "Please run the bot first to authorize the session."
            )

        self.clients[session_config.name] = client
        logger.info("Session Init", f"Session {session_config.name} initialized successfully")

    async def disconnect_all(self) -> None:
        """Disconnect all clients."""
        for name, client in self.clients.items():
            logger.info("Session Disconnect", f"Disconnecting session: {name}")
            await client.disconnect()

    def get_client(self, session_name: str) -> TelegramClient:
        """Get a client by session name."""
        if session_name not in self.clients:
            raise ValueError(f"Session {session_name} not found")
        return self.clients[session_name]

    def get_all_clients(self) -> dict[str, TelegramClient]:
        """Get all clients."""
        return self.clients


class BotClient:
    """Telegram bot client for handling search queries."""

    def __init__(self, config: Config):
        self.config = config
        self.client: TelegramClient | None = None
        self.session_dir = get_data_dir() / "sessions"
        self.session_dir.mkdir(parents=True, exist_ok=True)

    async def start(self) -> None:
        """Start the bot client."""
        session_file = self.session_dir / "bot.session"

        logger.info("Bot Client", "Starting bot client...")

        self.client = TelegramClient(
            str(session_file),
            self.config.app_id,
            self.config.app_hash,
        )

        await self.client.start(bot_token=self.config.app_token)
        logger.info("Bot Client", "Bot client started successfully")

    async def stop(self) -> None:
        """Stop the bot client."""
        if self.client:
            logger.info("Bot Client", "Stopping bot client...")
            await self.client.disconnect()

    def get_client(self) -> TelegramClient:
        """Get the bot client."""
        if not self.client:
            raise RuntimeError("Bot client not started")
        return self.client
