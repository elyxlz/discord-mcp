# Discord MCP Server (Python)

## Task
Build a Discord MCP (Model Context Protocol) server that can:
- Read messages across multiple Discord servers and channels
- Send messages to Discord channels
- Automatically discover channels across servers
- Provide efficient message reading with proper pagination to avoid token limits
- Handle authentication with Discord API tokens

## Use Cases
Enable an LLM to:
1. Monitor Discord servers and communities of interest
2. Automatically find announcement and feedback channels
3. Read and summarize recent messages from channels
4. Send community summaries and insights to designated channels

This enables automated community monitoring, content aggregation, and research across Discord servers. Competitive analysis is one possible use case among many others including community engagement, trend monitoring, and content curation.

## Note
This is the original Python implementation using Discord API. For web scraping approach, see the JavaScript implementation at `/home/elyx/Audiogen/discord-mcp-js/`.

## Package Management
- Use `uv init` to initialize the project
- Use `uv add` for adding dependencies
- Follow uv workflow for Python package management

## Code Quality
- Always run `uv run pyright` for Python type checking before committing
- Always run `uv run ruff check .` for Python linting before committing
- Use `uv run ruff check --fix .` to auto-fix Python linting issues

## Key Requirements
- MCP server implementation following official MCP protocol
- Discord API integration for reading and sending messages
- Channel discovery across all accessible servers with intelligent filtering
- Message pagination and filtering to work within MCP response size limits
- Time-based message filtering (last 24 hours, etc.)
- Channel name matching (find channels containing "announcement", "feedback", "news", etc.)
- Configuration management for Discord bot tokens
- Efficient data structures to minimize response sizes
- Cross-server message aggregation and summarization support

## Architecture
- Core MCP server with proper tool definitions
- Discord client wrapper for API interactions
- Channel discovery service with intelligent filtering
- Message reading service with pagination and time filtering
- Message sending service
- Configuration management for tokens and settings
- Server/guild management for tracking multiple Discord servers
- Content filtering and aggregation utilities

## MCP Tools to Implement
- `discover_channels` - Find channels by name patterns across servers
- `read_messages` - Read messages with time/pagination filters
- `send_message` - Send messages to specific channels
- `get_servers` - List accessible Discord servers
- `search_channels` - Search for channels containing keywords like "announcement", "feedback"

## Dependencies Needed
- mcp (official MCP library)
- aiohttp (for Discord API calls)
- python-dotenv (for environment variable management)
- typing-extensions (for type hints)