"""Main entry point for findgram."""

import asyncio
import signal
import sys

import click
from phdkit.log import Logger, LogOutput

from .bot import SearchBot
from .config import load_config
from .indexer import MessageIndexer
from .search import MeiliSearchManager
from .telegram_client import BotClient, SessionManager

logger = Logger(__name__, outputs=[LogOutput.stdout()])


class FindgramApp:
    """Main application controller."""

    def __init__(self):
        self.config = load_config()
        self.search_manager = MeiliSearchManager(self.config.meilisearch)
        self.session_manager = SessionManager(self.config)
        self.bot_client = BotClient(self.config)
        self.should_stop = False

    async def setup(self) -> None:
        """Setup all components."""
        logger.info("Setup", "Starting findgram...")

        # Start MeiliSearch
        self.search_manager.start()

        # Initialize sessions
        await self.session_manager.initialize_sessions()

        # Start bot client
        await self.bot_client.start()

        logger.info("Setup", "Setup completed")

    async def index_messages(self) -> None:
        """Index all messages from all sessions."""
        logger.info("Indexing", "Starting message indexing...")

        indexer = MessageIndexer(self.config, self.search_manager)
        await indexer.index_all_sessions(self.session_manager.get_all_clients())

        logger.info("Indexing", "Message indexing completed")

    async def run_bot(self) -> None:
        """Run the search bot."""
        logger.info("Bot", "Starting search bot...")

        bot = SearchBot(self.bot_client.get_client(), self.search_manager)
        bot.setup_handlers()

        # Run bot
        await bot.run()

    async def cleanup(self) -> None:
        """Cleanup resources."""
        logger.info("Cleanup", "Cleaning up...")

        await self.session_manager.disconnect_all()
        await self.bot_client.stop()
        self.search_manager.stop()

        logger.info("Cleanup", "Cleanup completed")


@click.group()
def cli():
    """findgram - Search your Telegram messages with ease."""
    pass


@cli.command()
@click.option(
    "--no-index",
    is_flag=True,
    help="Skip message indexing (use existing index)",
)
def run(no_index: bool):
    """Run the bot (index messages and start bot)."""

    async def main_async():
        app = FindgramApp()

        # Setup signal handlers
        def signal_handler(_sig, _frame):
            logger.info("Signal", "Received shutdown signal")
            asyncio.create_task(app.cleanup())
            sys.exit(0)

        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)

        try:
            await app.setup()

            if not no_index:
                await app.index_messages()
            else:
                logger.info("Indexing", "Skipping message indexing (--no-index)")

            await app.run_bot()
        except Exception as e:
            logger.error("Bot Error", str(e))
            await app.cleanup()
            sys.exit(1)

    asyncio.run(main_async())


@cli.command()
def index():
    """Index messages from all configured sessions."""

    async def main_async():
        app = FindgramApp()

        try:
            await app.setup()
            await app.index_messages()
            await app.cleanup()
        except Exception as e:
            logger.error("Indexing Error", str(e))
            await app.cleanup()
            sys.exit(1)

    asyncio.run(main_async())


@cli.command()
def config_info():
    """Show configuration information."""
    try:
        config = load_config()

        click.echo("Configuration loaded successfully:")
        click.echo(f"  APP_ID: {config.app_id}")
        click.echo(f"  APP_HASH: {config.app_hash[:10]}...")
        click.echo(f"\nMeiliSearch:")
        click.echo(f"  Host: {config.meilisearch.host}")
        click.echo(f"  Memory Limit: {config.meilisearch.memory_limit}")
        click.echo(f"\nSessions ({len(config.sessions)}):")
        for session in config.sessions:
            click.echo(f"  - {session.name}")
            click.echo(f"    Telegram ID: {session.telegram_id}")
            click.echo(f"    Included Chats: {len(session.included_chats)}")

    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
