# findgram

A Telegram bot for searching message history across multiple accounts with excellent Chinese language support and modern tooling.

## Project Overview

findgram is a modernized alternative to [SearchGram](https://github.com/tgbot-collection/SearchGram) that provides:
- Full-text search across Telegram message history
- Multi-account support (multiple sessions)
- Superior Chinese language search capabilities via Tantivy + jieba
- Modern Python toolchain using uv for dependency management
- Structured logging via [phdkit](https://github.com/cychen2021/phdkit.git)

## Architecture

### Core Components

1. **Telegram Client (Telethon)**
   - Handles Telegram API interactions
   - Manages multiple user sessions (accounts)
   - Fetches message history from configured chats

2. **Search Engine (Tantivy + jieba)**
   - Tantivy provides fast, embedded full-text search
   - jieba handles Chinese text tokenization for better search accuracy
   - Indexes messages from all configured sessions
   - Low memory footprint compared to external search engines

3. **Bot Interface (Telethon)**
   - Receives search queries from users
   - Returns formatted search results
   - Uses bot token for authentication

4. **Logging (phdkit)**
   - Custom logging framework maintained by project author
   - Structured logging for better debugging

## Technology Stack

- **Python**: 3.13+ (required)
- **Package Manager**: uv
- **Key Dependencies**:
  - `telethon>=1.42.0` - Telegram API client
  - `tantivy>=0.25.1` - Embedded search engine library
  - `jieba>=0.42.1` - Chinese text segmentation
  - `phdkit>=0.1.3` - Logging framework
  - `click>=8.3.1` - CLI interface
  - `rich>=14.3.3` - Terminal formatting

## Configuration

### File Locations

**Configuration files** (stored in XDG_CONFIG_HOME, typically `~/.config/findgram/`):

- `secrets.toml` - Sensitive credentials
- `config.toml` - Application configuration

**Data files** (stored in XDG_DATA_HOME, typically `~/.local/share/findgram/`):

- `tantivy_index/` - Tantivy search index with indexed messages
- `sessions/` - Telegram session files

### Configuration Schema

**secrets.toml**:
```toml
app_token = "your-bot-token-here"
```

**config.toml**:
```toml
app_id = 12345
app_hash = "your-app-hash"

# Search engine configuration (optional)
[search]
# index_path = "/custom/path/to/index"  # If omitted, uses default data directory
# context = 0  # Number of messages before/after each search hit (default: 0, like grep -C)

# Session configuration (one per account)
[[sessions]]
name = "account1"
telegram_id = 123456789
included_chats = [
    -1001234567890,  # Group chat ID (numeric)
    987654321,       # User ID (numeric)
    "@username",     # Username (string) - supports @ prefix or plain username
]

[[sessions]]
name = "account2"
telegram_id = 987654321
included_chats = [
    -1009876543210,
    "@channelname",  # Channel username
]
```

## Development

### Setup

1. **Install uv** (if not already installed):
   ```bash
   curl -LsSf https://astral.sh/uv/install.sh | sh
   ```

2. **Clone and setup**:
   ```bash
   git clone <repository-url>
   cd findgram
   uv sync  # Creates venv and installs dependencies
   ```

3. **Configure the bot**:
   - Create `~/.config/findgram/secrets.toml`
   - Create `~/.config/findgram/config.toml`
   - See Configuration section above for schema

4. **Run**:
   ```bash
   uv run findgram
   ```

### Code Organization

```
findgram/
├── src/
│   └── findgram/
│       └── main.py      # Application entry point
├── pyproject.toml       # Project metadata and dependencies
├── uv.lock             # Dependency lock file
├── README.md           # User documentation
├── CLAUDE.md           # Developer documentation
└── LICENSE             # MIT license
```

## Key Differences from SearchGram

1. **Multi-Account Support**: Native support for searching across multiple Telegram accounts simultaneously
2. **Modern Toolchain**: Uses uv instead of pip/poetry for faster, more reliable dependency management
3. **Better Chinese Support**: Uses Tantivy with jieba tokenization for excellent Chinese text segmentation
4. **Embedded Search Engine**: Tantivy is a library (no external process), reducing memory overhead
5. **Structured Logging**: Uses phdkit for better debugging and monitoring
6. **Python 3.13+**: Takes advantage of latest Python features and performance improvements

## Development Conventions

### Code Style

- Follow PEP 8 style guidelines
- Use type hints where applicable
- Keep functions focused and modular
- Format code with: `uv run format.py`

### Dependencies

- All dependencies managed through `pyproject.toml`
- Use `uv add <package>` to add new dependencies
- Use `uv lock` to update lock file after changes

### Testing

- Run tests with: `uv run pytest` (when tests are added)
- Ensure all tests pass before committing

### Commits

- Follow conventional commit format: `type: description`
- Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`

## Bot Operations

### Message Indexing Flow

1. Bot authenticates with configured sessions
2. Fetches message history from specified chats
3. Text is tokenized using jieba (for Chinese language support)
4. Indexes messages into Tantivy
5. Maintains real-time updates for new messages

### Search Flow

1. User sends search query to bot
2. Query text is tokenized using jieba
3. Bot searches Tantivy index with tokenized terms
4. Results aggregated across all sessions
5. Formatted results returned to user with context

## Telegram API Setup

To use this bot, you need:

1. **Bot Token**: Create a bot via [@BotFather](https://t.me/botfather) on Telegram
2. **API Credentials**: Get `app_id` and `app_hash` from [https://my.telegram.org](https://my.telegram.org)
3. **User Sessions**: Authorize each account you want to search (handled on first run)

## Search Engine Setup

The search engine uses **Tantivy with jieba tokenization**:

1. **Tantivy**: A fast, embedded full-text search library (no separate process needed)
   - Index is stored in `~/.local/share/findgram/tantivy_index/` by default
   - Can be customized via `[search] index_path` in config.toml
   - Low memory footprint compared to external search engines

2. **jieba**: Chinese text segmentation library
   - Automatically initialized on startup
   - Provides excellent tokenization for Chinese text
   - Works seamlessly with Tantivy's search capabilities

## Troubleshooting

### Session Files

- Session files stored in `~/.local/share/findgram/sessions/`
- Delete session files to re-authenticate an account

### Search Issues

- Check if index directory exists and is writable
- Review logs for indexing errors
- If search quality is poor, consider re-indexing messages
- For Chinese text, jieba tokenization should happen automatically

### Telegram API Errors

- Ensure `app_id` and `app_hash` are correct
- Check rate limits haven't been exceeded
- Verify bot token is valid

## Contributing

When contributing code:
1. Ensure code follows project conventions
2. Update documentation if adding features
3. Test with multiple accounts if changing session handling
4. Verify Chinese language search still works correctly
