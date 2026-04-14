"""Bot handler for search queries."""

from datetime import datetime

from phdkit.log import Logger, LogOutput
from telethon import TelegramClient, events

from .config import Config
from .search import TantivySearchManager

logger = Logger(__name__, outputs=[LogOutput.stdout()])


class SearchBot:
    """Handles search queries from users."""

    def __init__(
        self,
        bot_client: TelegramClient,
        search_manager: TantivySearchManager,
        config: Config,
    ):
        self.bot_client = bot_client
        self.search_manager = search_manager
        self.config = config

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
                "\nFlags (add to query):\n"
                "toggle_on:full - Show full message text\n"
                "toggle_off:full - Show text preview\n"
                "context:N - Show N messages before/after each result\n"
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

    def _parse_query_flags(self, query: str) -> tuple[str, bool, int]:
        """Parse special flags from the query string.

        Returns (cleaned_query, full_text, context).
        Flags: toggle_on:full, toggle_off:full, context:N.
        """
        full_text = self.config.search.full_text
        context = self.config.search.context
        parts = query.split()
        cleaned = []
        for part in parts:
            if part == "toggle_on:full":
                full_text = True
            elif part == "toggle_off:full":
                full_text = False
            elif part.startswith("context:"):
                try:
                    context = max(0, int(part.split(":", 1)[1]))
                except ValueError:
                    cleaned.append(part)
            else:
                cleaned.append(part)
        return " ".join(cleaned), full_text, context

    async def _handle_search(self, event: events.NewMessage.Event, query: str) -> None:
        """Handle a search query."""
        query, full_text, context = self._parse_query_flags(query)
        logger.info("Search", f"Query: {query}, full_text: {full_text}, context: {context}")

        try:
            # Get the user's telegram_id
            user_id = event.sender_id
            logger.info("Search", f"User telegram_id: {user_id}")

            # Find which session this user belongs to
            user_session = None
            for session in self.config.sessions:
                logger.info(
                    "Search",
                    f"Checking session: {session.name} (telegram_id: {session.telegram_id})",
                )
                if session.telegram_id == user_id:
                    user_session = session.name
                    logger.info("Search", f"✓ Matched session: {user_session}")
                    break

            # Build filters
            filters = {}
            if user_session:
                filters["session_name"] = user_session
                logger.info("Search", f"Filtering results for session: {user_session}")
            else:
                logger.warning(
                    "Search",
                    f"User {user_id} not found in any session, searching all sessions",
                )

            # Perform search
            results = self.search_manager.search(
                query, limit=10, filters=filters if filters else None
            )

            if not results:
                await event.respond("No results found.")
                return

            # Format results
            response = f"🔍 Found {len(results)} results for: {query}\n\n"

            for i, result in enumerate(results, 1):
                # Fetch context messages if requested
                if context > 0:
                    context_msgs = self.search_manager.fetch_context(result, context)
                else:
                    context_msgs = [result]

                for msg in context_msgs:
                    is_match = (
                        msg.get("message_id") == result["message_id"]
                        and msg.get("session_name") == result.get("session_name")
                    )

                    date = datetime.fromtimestamp(msg["date"])
                    date_str = date.strftime("%Y-%m-%d %H:%M")
                    sender_name = msg.get("sender_name") or "Unknown"

                    text = msg.get("text") or ""
                    if not full_text and len(text) > 200:
                        text = text[:197] + "..."

                    if is_match:
                        receiver_name = (
                            msg.get("receiver_name")
                            or msg.get("chat_title")
                            or "Unknown"
                        )
                        if sender_name == receiver_name:
                            who_info = sender_name
                        else:
                            who_info = f"{sender_name} → {receiver_name}"

                        response += f"📅 {date_str}\n👤 {who_info}\n\n{text}\n"
                    else:
                        response += f"  │ {date_str} {sender_name}: {text}\n"

                # Add separator between results, but not after the last one
                if i < len(results):
                    response += "\n─ ─ ─ ─ ─ ─ ─ ─ ─ ─\n\n"

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
