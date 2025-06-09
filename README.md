# Discord MCP Server (Python)

A Model Context Protocol (MCP) server for Discord integration that enables LLMs to read messages, discover channels, send messages, and monitor communities across multiple Discord servers using web scraping.

## Features

- **Server Discovery**: List all Discord servers you have access to
- **Channel Discovery**: Get channels from specific Discord servers  
- **Message Reading**: Read recent messages with time filtering and pagination
- **Message Sending**: Send messages to Discord channels
- **Cross-Server Support**: Monitor multiple Discord servers simultaneously
- **Web Scraping**: Access Discord servers using Playwright browser automation
- **Chronological Ordering**: Messages returned newest-first with proper time ordering
- **Headless Operation**: Runs in headless mode by default for production use

## Why Web Scraping?

This implementation uses Playwright web scraping instead of Discord's API because:
- Discord's API only allows reading from servers where you have bot permissions
- Web scraping enables reading from any Discord server you can access as a user
- Perfect for monitoring external communities and public Discord servers
- No need for bot creation or server permissions

## Installation & Setup

### Prerequisites

1. **Python 3.10+** with `uv` package manager
2. **Browser dependencies** for Playwright

```bash
git clone <this-repository>
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

# Optional: Browser settings (defaults shown)
DISCORD_HEADLESS=true
```

### Security Notes

- **Use App Passwords**: If you have 2FA enabled, create an app password
- **Dedicated Account**: Consider using a dedicated Discord account for automation
- **Rate Limiting**: The server includes delays to avoid being detected
- **Headless Mode**: Always use `DISCORD_HEADLESS=true` in production

## Running the Server

```bash
# Production (headless)
uv run python main.py

# Development (with browser visible for debugging)
DISCORD_HEADLESS=false uv run python main.py

# Direct execution
python main.py
```

## MCP Integration

### Claude Desktop

Add to your Claude Desktop config (`~/.claude/claude_desktop_config.json` on macOS):

```json
{
  "mcpServers": {
    "discord": {
      "command": "uv",
      "args": ["run", "python", "main.py"],
      "cwd": "/path/to/discord-mcp",
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

### `get_servers`
List all Discord servers you have access to.

**Arguments:** None

**Returns:** List of servers with `id` and `name`

### `get_channels(server_id)`
List all channels in a specific Discord server.

**Arguments:**
- `server_id` (string): Discord server ID

**Returns:** List of channels with `id`, `name`, and `type`

### `read_messages(server_id, channel_id, hours_back?, max_messages?)`
Read recent messages from a specific channel in chronological order (newest first).

**Arguments:**
- `server_id` (string): Discord server ID  
- `channel_id` (string): Discord channel ID
- `hours_back` (integer, optional): Hours to look back (1-8760, default: 24)
- `max_messages` (integer, optional): Maximum messages to return (1-1000, default: 100)

**Returns:** List of messages with `id`, `content`, `author_name`, `timestamp`, `attachments`

### `send_message(server_id, channel_id, content)`
Send a message to a specific Discord channel.

**Arguments:**
- `server_id` (string): Discord server ID
- `channel_id` (string): Discord channel ID  
- `content` (string): Message content (1-2000 characters)

**Returns:** Object with `message_id` and `status`

## Usage Examples

### List Your Discord Servers

```json
{
  "tool": "get_servers",
  "arguments": {}
}
```

### Get All Channels in a Server

```json
{
  "tool": "get_channels", 
  "arguments": {
    "server_id": "1234567890123456789"
  }
}
```

### Read Recent Messages (Newest First)

```json
{
  "tool": "read_messages",
  "arguments": {
    "server_id": "1234567890123456789",
    "channel_id": "9876543210987654321",
    "hours_back": 24,
    "max_messages": 20
  }
}
```

### Send a Message

```json
{
  "tool": "send_message",
  "arguments": {
    "server_id": "1234567890123456789", 
    "channel_id": "9876543210987654321",
    "content": "Hello from the MCP server!"
  }
}
```

## Message Ordering

Messages are returned in **chronological order (newest first)**:
- `max_messages: 1` returns the most recent message
- `max_messages: 10` returns the 10 most recent messages  
- More messages means going further back in time

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
# Run all integration tests
uv run pytest -v tests/

# Run specific test
uv run pytest -v tests/test_integration.py::test_mcp_read_messages_tool

# Run with visible browser (for debugging)
DISCORD_HEADLESS=false uv run pytest -v -s tests/
```

### Architecture

The codebase follows a clean, functional architecture:

- **`main.py`** - Entry point that starts the MCP server
- **`src/discord_mcp/server.py`** - FastMCP server with tool definitions
- **`src/discord_mcp/client.py`** - Playwright-based Discord client  
- **`src/discord_mcp/config.py`** - Configuration management
- **`src/discord_mcp/messages.py`** - Message reading and filtering logic
- **`tests/`** - Integration tests for all MCP tools

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
- Check `discord_mcp_debug.log` for detailed logs

### Rate Limiting

- The server includes built-in delays between operations
- Reduce `max_messages` if hitting limits
- Monitor Discord for any account warnings
- Tests run sequentially to avoid race conditions

### Cookie Persistence

- Login state is saved to `~/.discord_mcp_cookies.json`
- Delete this file if having persistent login issues
- Cookies eliminate re-login overhead for better performance

## Legal & Ethical Considerations

- Ensure compliance with Discord's Terms of Service
- Only access information you would normally have access to as a user
- Respect rate limits and avoid aggressive scraping  
- Use for legitimate monitoring and research purposes
- Consider reaching out to communities directly when appropriate

## Contributing

1. Fork the repository
2. Create a feature branch
3. Make your changes following the coding style
4. Ensure all quality checks pass (`uv run pyright`, `uvx ruff check`)
5. Run the test suite (`uv run pytest -v tests/`)
6. Submit a pull request

## License

MIT License - see LICENSE file for details.