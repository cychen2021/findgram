# findgram

A powerful Telegram bot for searching your message history across multiple accounts with excellent Chinese language support.

## Features

- **Multi-Account Search**: Search across multiple Telegram accounts simultaneously
- **Excellent Chinese Support**: Uses Tantivy with jieba for superior Chinese language tokenization and search
- **Fast Full-Text Search**: Lightning-fast embedded search across your entire message history
- **Low Memory Footprint**: Tantivy is an embedded library, no separate process needed
- **Modern Toolchain**: Built with Python 3.13+ and uv for reliable dependency management
- **Flexible Configuration**: Easy TOML-based configuration for accounts, chats, and search parameters
- **Privacy-Focused**: Self-hosted search - your data stays on your infrastructure

## Why findgram?

findgram is inspired by [SearchGram](https://github.com/tgbot-collection/SearchGram) but provides:
- Native multi-account support
- Better Chinese language search capabilities
- Modern Python toolchain (uv instead of pip/poetry)
- Cleaner configuration structure
- Enhanced logging with [phdkit](https://github.com/cychen2021/phdkit.git)

## Requirements

- Python 3.13 or higher
- Telegram account(s) to search
- Telegram Bot Token from [@BotFather](https://t.me/botfather)
- Telegram API credentials (APP_ID and APP_HASH) from [my.telegram.org](https://my.telegram.org)

## Installation

### 1. Install uv (Python package manager)

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 2. Clone the repository

```bash
git clone <repository-url>
cd findgram
```

### 3. Install dependencies

```bash
uv sync
```

### 4. Search Engine

findgram uses **Tantivy** (an embedded search library) with **jieba** for Chinese tokenization:
- No separate process to install or manage
- Low memory footprint
- Excellent Chinese language support through jieba
- Index is automatically created in `~/.local/share/findgram/tantivy_index/`

## Configuration

Configuration files are stored in `~/.config/findgram/` (or your XDG_CONFIG_HOME directory).

Data files (sessions, search database) are stored in `~/.local/share/findgram/` (or your XDG_DATA_HOME directory).

### 1. Create secrets.toml

Create `~/.config/findgram/secrets.toml` with your bot token:

```toml
app_token = "1234567890:ABCdefGHIjklMNOpqrsTUVwxyz"
```

Get your bot token from [@BotFather](https://t.me/botfather) on Telegram.

### 2. Create config.toml

Create `~/.config/findgram/config.toml`:

```toml
# Telegram API credentials from https://my.telegram.org
app_id = 12345678
app_hash = "abcdef1234567890abcdef1234567890"

# Search configuration (optional)
[search]
# index_path = "/custom/path"  # Custom index location (optional)
# preceding_context = 0         # Messages before each search hit (0-10)
# subsequent_context = 0        # Messages after each search hit (0-10)

# Define each account you want to search
[[sessions]]
name = "personal"           # Friendly name for this account
telegram_id = 123456789     # Your Telegram user ID (for reference only)
included_chats = [
    -1001234567890,         # Group chat ID (negative for groups)
    987654321,              # Direct chat with user ID
    -1009876543210,         # Another group
]

[[sessions]]
name = "work"
telegram_id = 987654321     # Your Telegram user ID (for reference only)
included_chats = [
    -1002468135790,
    "@workchannel",         # Channel username
]
```

**How to get chat IDs:**
- For groups: Forward a message to [@userinfobot](https://t.me/userinfobot)
- For users: Use [@userinfobot](https://t.me/userinfobot)
- Group IDs are negative numbers

## Usage

### Start the bot

```bash
uv run findgram
```

On first run, you'll be prompted to authenticate each session (account) configured in `config.toml`. You'll need to provide:
- Your phone number (with country code, e.g., +1234567890)
- The verification code sent to your Telegram app

### Search your messages

1. Open Telegram and find your bot
2. Send a search query to the bot
3. Receive results from all configured accounts and chats

**Example searches:**
- `keyword` - Search for exact keyword
- `multiple words` - Search for messages containing all words
- `中文搜索` - Search in Chinese

**Search flags** (add to your query):
- `toggle_on:full` - Show full message text instead of preview
- `toggle_off:full` - Show text preview (200 chars)
- `context:N` - Show N messages before and after each result (max 10)
- `context:M,N` - Show M messages before / N after each result
- `context:,N` or `context:N,` - One-sided context (before or after only)

## Project Structure

```
findgram/
├── src/
│   └── findgram/
│       ├── __init__.py          # Package initialization
│       ├── main.py              # Application entry point
│       ├── config.py            # Configuration management
│       ├── telegram_client.py   # Telegram client wrapper
│       ├── bot.py               # Bot interface
│       ├── indexer.py           # Message indexing
│       └── search.py            # Search functionality
├── pyproject.toml               # Project metadata and dependencies
├── uv.lock                      # Dependency lock file
├── README.md                    # This file
├── CLAUDE.md                    # Developer documentation
└── LICENSE                      # MIT license
```

## Directory Structure

**Configuration** (`~/.config/findgram/`):
```
~/.config/findgram/
├── secrets.toml         # Bot token and sensitive credentials
└── config.toml          # Application configuration
```

**Data** (`~/.local/share/findgram/`):
```
~/.local/share/findgram/
├── sessions/            # Telegram session files (auto-generated)
│   ├── personal.session
│   ├── work.session
│   └── bot.session
└── tantivy_index/       # Tantivy search index with indexed messages
```

## Getting Telegram Credentials

### Bot Token

1. Open Telegram and search for [@BotFather](https://t.me/botfather)
2. Send `/newbot` and follow the prompts
3. Copy the bot token provided

### API Credentials (APP_ID and APP_HASH)

1. Visit [https://my.telegram.org](https://my.telegram.org)
2. Log in with your phone number
3. Go to "API development tools"
4. Create a new application
5. Copy the `app_id` and `app_hash`

### User ID

1. Search for [@userinfobot](https://t.me/userinfobot) on Telegram
2. Start the bot
3. It will show your user ID

## Troubleshooting

### "Session file not found"

Delete the session file and restart. The bot will prompt you to re-authenticate:
```bash
rm ~/.local/share/findgram/sessions/*.session
```

### "Index not found" or search errors

If you encounter indexing or search errors:

1. Check if `~/.local/share/findgram/tantivy_index/` exists and is writable
2. Try deleting the index directory and re-indexing
3. Check the logs for specific error messages

### "Rate limit exceeded"

Telegram has rate limits. The bot will automatically handle this, but initial indexing of large chat histories may take time.

### Chinese search not working well

The bot uses jieba for Chinese tokenization, which provides excellent support for Chinese text. If search quality is poor:
- Consider re-indexing your messages
- Check that messages are being indexed correctly in the logs

## Contributing

Contributions are welcome! Please:
1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Submit a pull request

## License

MIT License - see LICENSE file for details

## Author

Chuyang Chen (chuyangchen2018@outlook.com)

## Acknowledgments

- Inspired by [SearchGram](https://github.com/tgbot-collection/SearchGram)
- Uses [phdkit](https://github.com/cychen2021/phdkit.git) for logging
- Powered by [Tantivy](https://github.com/quickwit-oss/tantivy) for search capabilities
- Uses [jieba](https://github.com/fxsjy/jieba) for Chinese text segmentation
- Built with [Telethon](https://github.com/LonamiWebs/Telethon) for Telegram API
