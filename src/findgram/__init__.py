"""findgram - Search your Telegram messages with ease."""

__version__ = "0.1.0"

from .bot import SearchBot
from .config import Config, load_config
from .indexer import MessageIndexer
from .search import TantivySearchManager, MessageDocument
from .telegram_client import BotClient, SessionManager

__all__ = [
    "Config",
    "load_config",
    "TantivySearchManager",
    "MessageDocument",
    "SessionManager",
    "BotClient",
    "MessageIndexer",
    "SearchBot",
]
