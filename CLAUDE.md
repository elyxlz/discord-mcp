# Discord MCP Server (Python)

## Task
Build a Discord MCP (Model Context Protocol) server that can:
- Read messages across multiple Discord servers and channels
- Send messages to Discord channels  
- List Discord servers and channels
- Provide efficient message reading with proper chronological ordering
- Handle authentication with Discord credentials using web scraping

## Use Cases
Enable an LLM to:
1. Monitor Discord servers and communities of interest
2. Read and summarize recent messages from channels
3. Send messages to Discord channels
4. Discover available servers and channels

This enables automated community monitoring, content aggregation, and interaction across Discord servers for purposes like community engagement, trend monitoring, and content curation.

## Implementation Approach
This implementation uses **Playwright web scraping** instead of Discord's API because:
- Discord's API only allows reading from servers where you have bot permissions
- Web scraping enables reading from any Discord server you can access as a user
- No need for bot creation or server permissions

## Package Management
- Use `uv` package manager for all operations
- Use `uv run` prefix for all Python commands
- Use `uv add` for adding dependencies

## Code Quality
- Always run `uv run pyright` for Python type checking
- Always run `uvx ruff format .` for formatting
- Always run `uvx ruff check --fix --unsafe-fixes .` for linting

## Current Architecture
- **`main.py`** - Entry point that starts the MCP server
- **`src/discord_mcp/server.py`** - FastMCP server with 4 tool definitions
- **`src/discord_mcp/client.py`** - Playwright-based Discord client with simplified message extraction
- **`src/discord_mcp/config.py`** - Configuration management for Discord credentials
- **`src/discord_mcp/messages.py`** - Message reading and time filtering logic
- **`src/discord_mcp/logger.py`** - Logging setup and configuration
- **`tests/test_integration.py`** - Integration tests for all MCP tools

## MCP Tools Implemented
- **`get_servers`** - List all Discord servers you have access to
- **`get_channels(server_id)`** - List all channels in a specific Discord server
- **`read_messages(server_id, channel_id, max_messages, hours_back?)`** - Read recent messages in chronological order (newest first)
- **`send_message(server_id, channel_id, content)`** - Send messages to specific Discord channels (automatically splits long messages)

## Dependencies
- **mcp** - Official MCP library via FastMCP
- **playwright** - Browser automation for Discord web scraping  
- **python-dotenv** - Environment variable management
- **pytest** - Testing framework

## Test Strategy & Reliability
The implementation prioritizes **reliability over speed** through:

### Browser State Management
- Complete browser reset between every MCP tool call using `_execute_with_fresh_client()`
- Async lock serialization to prevent race conditions
- Cookie persistence at `~/.discord_mcp_cookies.json` for login state

### Message Extraction
- **Chronological ordering**: Messages returned newest-first
- **Simplified extraction**: Streamlined from ~130 lines to ~54 lines
- **Robust scrolling**: JavaScript-based scroll to bottom for newest messages
- **Proper filtering**: Time-based and count-based message limiting

### Test Execution
- Sequential test execution (`-n 0` in pytest.ini) to avoid resource conflicts
- Comprehensive integration tests covering all 4 MCP tools
- 100% test reliability across multiple runs

## Performance Characteristics
- **Cookie persistence** eliminates re-login overhead  
- **JavaScript extraction** faster than clicking through UI elements
- **Fresh browser state** adds ~2-3 seconds per tool call but ensures reliability
- **Simplified message logic** improved performance while maintaining functionality

## Development Workflow
1. Make changes following functional programming patterns
2. Run `uv run pyright` for type checking
3. Run `uvx ruff format .` and `uvx ruff check --fix --unsafe-fixes .` for code quality
4. Run `uv run pytest -v tests/` for integration testing
5. Verify all 4 MCP tools work correctly

## Configuration
Set environment variables:
```env
DISCORD_EMAIL=your_email@example.com
DISCORD_PASSWORD=your_password
DISCORD_HEADLESS=true  # For production
```

## Message Ordering Behavior
Messages are returned in **chronological order (newest first)**:
- `max_messages: 1` returns the most recent message
- `max_messages: 20` returns the 20 most recent messages
- More messages means going further back in time chronologically

This ordering was fixed from previous counterintuitive behavior and now works correctly and consistently.