"""Bot handler for search queries."""

from datetime import datetime

from phdkit.log import Logger, LogOutput
from telethon import TelegramClient, events

from .search import MeiliSearchManager

logger = Logger(__name__, outputs=[LogOutput.stdout()])


class SearchBot:
    """Handles search queries from users."""

    def __init__(self, bot_client: TelegramClient, search_manager: MeiliSearchManager):
        self.bot_client = bot_client
        self.search_manager = search_manager

    def setup_handlers(self) -> None:
        """Setup message handlers for the bot."""

        @self.bot_client.on(events.NewMessage(pattern="/start"))
        async def start_handler(event: events.NewMessage.Event) -> None:
            """Handle /start command."""
            await event.respond(
                "👋 Welcome to findgram!\n\n"
                "Send me any text to search through your Telegram messages.\n\n"
                "Commands:\n"
                "/start - Show this help message\n"
                "/search <query> - Search for messages\n"
                "\nJust send any text to search!"
            )

        @self.bot_client.on(events.NewMessage(pattern="/search (.+)"))
        async def search_command_handler(event: events.NewMessage.Event) -> None:
            """Handle /search command."""
            query = event.pattern_match.group(1)
            await self._handle_search(event, query)

        @self.bot_client.on(events.NewMessage(incoming=True))
        async def message_handler(event: events.NewMessage.Event) -> None:
            """Handle regular messages as search queries."""
            # Ignore commands
            if event.message.text and event.message.text.startswith("/"):
                return

            query = event.message.text
            if query:
                await self._handle_search(event, query)

    async def _handle_search(self, event: events.NewMessage.Event, query: str) -> None:
        """Handle a search query."""
        logger.info("Search", f"Query: {query}")

        try:
            # Perform search
            results = self.search_manager.search(query, limit=10)

            if not results:
                await event.respond("No results found.")
                return

            # Format results
            response = f"🔍 Found {len(results)} results for: {query}\n\n"

            for i, result in enumerate(results, 1):
                # Format date
                date = datetime.fromtimestamp(result["date"])
                date_str = date.strftime("%Y-%m-%d %H:%M")

                # Format sender info
                sender_info = ""
                if result.get("sender_name"):
                    sender_info = f"👤 {result['sender_name']}\n"

                # Format chat info
                chat_info = ""
                if result.get("chat_title"):
                    chat_info = f"💬 {result['chat_title']}\n"

                # Get text preview (limit to 200 chars)
                text = result["text"]
                if len(text) > 200:
                    text = text[:197] + "..."

                response += (
                    f"{i}. {chat_info}"
                    f"{sender_info}"
                    f"📅 {date_str}\n"
                    f"💭 {text}\n"
                    f"📍 Session: {result['session_name']}\n\n"
                )

            # Split response if too long (Telegram limit is 4096 chars)
            if len(response) > 4096:
                # Send in chunks
                chunks = []
                current_chunk = ""
                for line in response.split("\n\n"):
                    if len(current_chunk) + len(line) + 2 > 4096:
                        chunks.append(current_chunk)
                        current_chunk = line
                    else:
                        if current_chunk:
                            current_chunk += "\n\n" + line
                        else:
                            current_chunk = line

                if current_chunk:
                    chunks.append(current_chunk)

                for chunk in chunks:
                    await event.respond(chunk)
            else:
                await event.respond(response)

        except Exception as e:
            logger.error("Search Error", str(e))
            await event.respond(f"Error searching: {str(e)}")

    async def run(self) -> None:
        """Run the bot."""
        logger.info("Bot Running", "Waiting for messages...")
        await self.bot_client.run_until_disconnected()
