# Discord MCP Server

A Model Context Protocol (MCP) server that lets LLMs read messages, discover channels, send messages, and monitor Discord communities using web scraping.

## Features

- List Discord servers and channels you have access to
- Read recent messages with time filtering (newest first)
- Send messages to Discord channels (automatically splits long messages)
- Web scraping approach - works with any Discord server you can access as a user
- No bot permissions or API tokens required

## Quick Start with Claude Code

```bash
# Add Discord MCP server
claude mcp add discord-mcp -s user -e DISCORD_EMAIL=your_email@example.com -e DISCORD_PASSWORD=your_password -e DISCORD_HEADLESS=true -- uvx --from git+https://github.com/elyxlz/discord-mcp.git discord-mcp

# Start Claude Code
claude
```

### Usage Examples

```bash
# List your Discord servers
> use get_servers to show me all my Discord servers

# Read recent messages (max_messages is required)
> read the last 20 messages from channel ID 123 in server ID 456

# Send a message (long messages automatically split)
> send "Hello!" to channel 123 in server 456

# Send a long message (will be split automatically)
> send a very long message with multiple paragraphs to channel 123 in server 456

# Monitor communities
> summarize discussions from the last 24 hours across my Discord servers
```

## Available Tools

- **`get_servers`** - List all Discord servers you have access to
- **`get_channels(server_id)`** - List channels in a specific server
- **`read_messages(server_id, channel_id, max_messages, hours_back?)`** - Read recent messages (newest first, max_messages required)
- **`send_message(server_id, channel_id, content)`** - Send messages to channels (automatically splits long messages)

## Manual Setup

### Prerequisites
- Python 3.10+ with `uv` package manager
- Discord account credentials

### Installation
```bash
git clone https://github.com/elyxlz/discord-mcp.git
cd discord-mcp
uv sync
uv run playwright install
```

### Configuration
Create `.env` file:
```env
DISCORD_EMAIL=your_email@example.com
DISCORD_PASSWORD=your_password
DISCORD_HEADLESS=true
```

### Run Server
```bash
uv run python main.py
```

## Claude Desktop Integration

Add to `~/.claude/claude_desktop_config.json`:
```json
{
  "mcpServers": {
    "discord": {
      "command": "uvx",
      "args": ["--from", "git+https://github.com/elyxlz/discord-mcp.git", "discord-mcp"],
      "env": {
        "DISCORD_EMAIL": "your_email@example.com",
        "DISCORD_PASSWORD": "your_password",
        "DISCORD_HEADLESS": "true"
      }
    }
  }
}
```

## Development

```bash
# Type checking
uv run pyright

# Formatting
uvx ruff format .

# Linting
uvx ruff check --fix --unsafe-fixes .

# Testing
uv run pytest -v tests/
```

## Security Notes

- Use app passwords if 2FA is enabled
- Consider using a dedicated Discord account for automation
- Server includes delays to avoid rate limiting (0.5s between split messages)
- Always use `DISCORD_HEADLESS=true` in production

## Troubleshooting

- **Login issues**: Verify credentials, use app password for 2FA
- **Browser errors**: Run `uv run playwright install --force`
- **Rate limits**: Reduce `max_messages`, monitor for Discord warnings (server auto-splits long messages with delays)
- **Cookie issues**: Delete `~/.discord_mcp_cookies.json` if needed
- **Message splitting**: Long messages (>2000 chars) automatically split into multiple messages with 0.5s delays

## Legal Notice

Ensure compliance with Discord's Terms of Service. Only access information you would normally have access to as a user. Use for legitimate monitoring and research purposes.