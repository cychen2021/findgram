# findgram

A powerful Telegram bot for searching your message history across multiple accounts with excellent Chinese language support.

## Features

- **Multi-Account Search**: Search across multiple Telegram accounts simultaneously
- **Excellent Chinese Support**: Powered by MeiliSearch for superior Chinese language tokenization and search
- **Fast Full-Text Search**: Lightning-fast search across your entire message history
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
- [MeiliSearch](https://www.meilisearch.com/) (automatically installed if not found)
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

### 4. MeiliSearch Setup

MeiliSearch will be automatically downloaded and installed when you first run findgram if it's not already available in your PATH or current directory.

Alternatively, you can manually install and run MeiliSearch:

```bash
# Manual installation (optional)
curl -L https://install.meilisearch.com | sh

# Run MeiliSearch manually (optional)
./meilisearch --master-key="your-master-key-here"
```

**Note**: If you don't manually run MeiliSearch, findgram will start it automatically with the configured settings.

## Configuration

Configuration files are stored in `~/.config/findgram/` (or your XDG_CONFIG_HOME directory).

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

# MeiliSearch configuration
[meilisearch]
memory_limit = "512MB"  # Adjust based on your server capacity

# Define each account you want to search
[[sessions]]
name = "personal"           # Friendly name for this account
telegram_id = 123456789     # Your Telegram user ID
included_chats = [
    -1001234567890,         # Group chat ID (negative for groups)
    987654321,              # Direct chat with user ID
    -1009876543210,         # Another group
]

[[sessions]]
name = "work"
telegram_id = 987654321
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

On first run, you'll be prompted to authenticate each session (account) configured in `config.toml`.

### Search your messages

1. Open Telegram and find your bot
2. Send a search query to the bot
3. Receive results from all configured accounts and chats

**Example searches:**
- `keyword` - Search for exact keyword
- `multiple words` - Search for messages containing all words
- `中文搜索` - Search in Chinese

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

## Configuration Directory Structure

```
~/.config/findgram/
├── secrets.toml         # Bot token and sensitive credentials
├── config.toml          # Application configuration
└── sessions/            # Session files (auto-generated)
    ├── personal.session
    └── work.session
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
rm ~/.config/findgram/sessions/*.session
```

### "MeiliSearch connection error"

Ensure MeiliSearch is running:
```bash
./meilisearch --master-key="your-master-key"
```

### "Rate limit exceeded"

Telegram has rate limits. The bot will automatically handle this, but initial indexing of large chat histories may take time.

### Chinese search not working well

Verify MeiliSearch is running with the correct configuration. MeiliSearch provides excellent Chinese language support out of the box.

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
- Powered by [MeiliSearch](https://www.meilisearch.com/) for search capabilities
- Built with [Telethon](https://github.com/LonamiWebs/Telethon) for Telegram API
