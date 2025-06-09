# Discord MCP Server (Python)

A Model Context Protocol (MCP) server for Discord integration that enables LLMs to read messages, discover channels, and send messages across multiple Discord servers using web scraping.

## Features

- **Channel Discovery**: Find channels by keywords or regex patterns across servers
- **Message Reading**: Read recent messages with time filtering and pagination
- **Cross-Server Support**: Monitor multiple Discord servers simultaneously
- **Web Scraping**: Access Discord servers you don't own (bypasses API limitations)
- **Community Monitoring**: Monitor and analyze Discord community discussions
- **Headless Operation**: Runs in headless mode by default for production use

## Why Web Scraping?

This implementation uses Playwright web scraping instead of Discord's API because:
- Discord's API only allows reading from servers where you have bot permissions
- Web scraping enables reading from any public Discord server you can access
- Perfect for monitoring external communities and public Discord servers

## Installation & Setup

### Prerequisites

Install dependencies and browser binaries:

```bash
git clone https://github.com/elyxlz/discord-mcp
cd discord-mcp
uv sync
uv run playwright install
```

### Configuration

Create a `.env` file in your project directory:

```env
# Required: Your Discord account credentials
DISCORD_EMAIL=your_email@example.com
DISCORD_PASSWORD=your_password

# Optional: Browser settings
DISCORD_HEADLESS=true                             # Default: true (headless mode)

# Optional: Server and message limits
DISCORD_GUILD_IDS=guild_id1,guild_id2,guild_id3  # Limit to specific servers
MAX_MESSAGES_PER_CHANNEL=200                      # Default: 200
DEFAULT_HOURS_BACK=24                             # Default: 24 hours
```

### Security Notes

- **Use App Passwords**: If you have 2FA enabled, create an app password
- **Dedicated Account**: Consider using a dedicated Discord account for scraping
- **Rate Limiting**: The scraper includes delays to avoid being detected
- **Headless Mode**: Always use `DISCORD_HEADLESS=true` in production

### Running the Server

```bash
# Production (headless)
uv run discord-mcp

# Development (with browser visible for debugging)
DISCORD_HEADLESS=false uv run discord-mcp

# Using uvx directly
uvx --from git+https://github.com/elyxlz/discord-mcp discord-mcp
```

## MCP Integration

### Claude Desktop

Add to your Claude Desktop config (`~/Library/Application Support/Claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "discord": {
      "command": "uvx",
      "args": [
        "--from", 
        "git+https://github.com/elyxlz/discord-mcp",
        "discord-mcp"
      ],
      "env": {
        "DISCORD_EMAIL": "your_email@example.com",
        "DISCORD_PASSWORD": "your_password",
        "DISCORD_HEADLESS": "true"
      }
    }
  }
}
```

### Other MCP Clients

The server communicates via stdin/stdout following the MCP protocol. Start it and connect via your preferred MCP client.

## Available Tools

### Server Management
- **`get_servers`** - List all accessible Discord servers

### Channel Discovery
- **`discover_channels`** - Find channels by keyword matching
- **`search_channels`** - Find channels using regex patterns
- **`get_announcement_channels`** - Auto-discover announcement channels
- **`get_feedback_channels`** - Auto-discover feedback/discussion channels

### Message Operations
- **`read_messages`** - Read recent messages from a channel
- **`read_channel_batch`** - Read messages from multiple channels
- **`send_message`** - Send messages to Discord channels

## Usage Examples

### Discover Announcement Channels

```json
{
  "tool": "get_announcement_channels",
  "arguments": {}
}
```

### Monitor Specific Keywords

```json
{
  "tool": "discover_channels",
  "arguments": {
    "keywords": ["announcement", "news", "updates", "release"]
  }
}
```

### Read Recent Messages

```json
{
  "tool": "read_messages",
  "arguments": {
    "channel_id": "1234567890123456789",
    "hours_back": 24,
    "max_messages": 100
  }
}
```

### Batch Read Multiple Channels

```json
{
  "tool": "read_channel_batch",
  "arguments": {
    "channel_ids": ["1234567890123456789", "9876543210987654321"],
    "hours_back": 24,
    "summary_only": true
  }
}
```

### Send Community Summary

```json
{
  "tool": "send_message",
  "arguments": {
    "channel_id": "your_channel_id",
    "content": "## Community Update\n\nLatest announcements and discussions from monitored channels..."
  }
}
```

## Troubleshooting

### Browser Issues

```bash
# Install missing system dependencies (Linux)
sudo apt install -y libnss3 libxss1 libasound2

# Reinstall browsers
uv run playwright install --force
```

### Login Problems

- Verify email/password are correct
- Use app password if 2FA is enabled
- Check for Discord captcha requirements
- Try with `DISCORD_HEADLESS=false` to debug visually

### Rate Limiting

- The scraper includes built-in delays
- Reduce `MAX_MESSAGES_PER_CHANNEL` if hitting limits
- Monitor Discord for any account warnings

## Development

### Code Quality

```bash
# Type checking
uv run pyright

# Formatting
uvx ruff format .

# Linting with auto-fix
uvx ruff check --fix --unsafe-fixes .
```

### Testing

```bash
# Test with visible browser (for debugging)
DISCORD_HEADLESS=false uv run python -c "
from src.discord_mcp.client import DiscordWebClient
from src.discord_mcp.config import load_config
import asyncio

async def test():
    config = load_config()
    client = DiscordWebClient(config.email, config.password, False)
    guilds = await client.get_guilds()
    print(f'Found {len(guilds)} guilds')
    await client.close()

asyncio.run(test())
"
```

## Legal & Ethical Considerations

- Ensure compliance with Discord's Terms of Service
- Only access publicly available information
- Respect rate limits and avoid aggressive scraping
- Use for legitimate community monitoring and research purposes
- Consider reaching out to communities directly when appropriate

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes
4. Ensure all quality checks pass (`uv run pyright`, `uvx ruff check`)
5. Submit a pull request

## License

MIT License - see LICENSE file for details.