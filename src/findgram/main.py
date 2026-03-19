"""Main entry point for findgram."""

import asyncio
import signal
import sys

import click
from phdkit.log import Logger, LogOutput

from .bot import SearchBot
from .config import load_config
from .indexer import MessageIndexer
from .search import TantivySearchManager
from .telegram_client import BotClient, SessionManager

logger = Logger(__name__, outputs=[LogOutput.stdout()])


class FindgramApp:
    """Main application controller."""

    def __init__(self):
        self.config = load_config()
        self.search_manager = TantivySearchManager(self.config.search)
        self.session_manager = SessionManager(self.config)
        self.bot_client = BotClient(self.config)
        self.should_stop = False

    async def setup(self) -> None:
        """Setup all components."""
        logger.info("Setup", "Starting findgram...")

        # Start Tantivy search manager
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

        bot = SearchBot(self.bot_client.get_client(), self.search_manager, self.config)
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

            # Start indexing in background if requested
            indexing_task = None
            if not no_index:
                logger.info(
                    "Indexing",
                    "Starting message indexing in background (bot is ready for searches)...",
                )
                indexing_task = asyncio.create_task(app.index_messages())
            else:
                logger.info("Indexing", "Skipping message indexing (--no-index)")

            # Run bot (this will block until shutdown)
            # Bot can search as soon as any session finishes indexing
            logger.info(
                "Bot",
                "Bot is ready! You can search as sessions finish indexing.",
            )
            await app.run_bot()

            # If we get here, bot was stopped - wait for indexing to complete
            if indexing_task and not indexing_task.done():
                logger.info(
                    "Indexing", "Waiting for background indexing to complete..."
                )
                await indexing_task

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
        click.echo(f"\nSearch Engine: Tantivy + jieba")
        index_path = config.search.index_path or "(default data directory)"
        click.echo(f"  Index Path: {index_path}")
        click.echo(f"\nSessions ({len(config.sessions)}):")
        for session in config.sessions:
            click.echo(f"  - {session.name}")
            click.echo(f"    Telegram ID: {session.telegram_id}")
            click.echo(f"    Included Chats: {len(session.included_chats)}")

    except Exception as e:
        click.echo(f"Error loading configuration: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option(
    "--yes",
    is_flag=True,
    help="Skip confirmation prompt",
)
def reset_index(yes: bool):
    """Reset the search index (deletes all indexed messages)."""
    import shutil
    from pathlib import Path

    try:
        config = load_config()

        # Get index path
        if config.search.index_path:
            index_path = Path(config.search.index_path)
        else:
            from .config import get_data_dir

            index_path = get_data_dir() / "tantivy_index"

        # Check if index exists
        if not index_path.exists():
            click.echo(f"Index does not exist at: {index_path}")
            click.echo("Nothing to reset.")
            return

        # Confirm deletion
        if not yes:
            click.echo(f"This will delete the search index at: {index_path}")
            click.echo(
                "All indexed messages will be removed and you'll need to re-index."
            )
            if not click.confirm("Are you sure you want to continue?"):
                click.echo("Aborted.")
                return

        # Delete the index directory
        click.echo(f"Deleting index at: {index_path}")
        shutil.rmtree(index_path)
        click.echo("✓ Index reset successfully!")
        click.echo("\nRun 'findgram index' or 'findgram run' to re-index messages.")

    except Exception as e:
        click.echo(f"Error resetting index: {e}", err=True)
        sys.exit(1)


def main():
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
