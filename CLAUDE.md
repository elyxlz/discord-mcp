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

## Test Stability Fixes Applied

### Critical Lessons Learned
During development, we discovered that Playwright-based Discord automation requires very careful state management to avoid test flakiness and browser hanging. The following fixes were essential for reliable test execution:

#### 1. Browser State Isolation Between Tool Calls
**Problem**: Browser state would get corrupted between MCP tool calls, causing subsequent calls to hang or fail.
**Solution**: Complete browser reset between every tool call using `close_client()` and recreating `client_state`.

**Implementation**: In `server.py`, every tool call now:
```python
# COMPLETE RESET: Close and recreate client state for every tool call
await asyncio.wait_for(close_client(client_state), timeout=10.0)
client_state = create_client_state(config.email, config.password, config.headless)
```

#### 2. Async Lock Serialization
**Problem**: Concurrent test execution led to race conditions in browser operations.
**Solution**: Global `_CLIENT_LOCK = asyncio.Lock()` to serialize all browser operations.

#### 3. Robust Waiting Strategies
**Problem**: `await asyncio.sleep()` calls were unreliable and caused random test failures.
**Solution**: Replaced with proper Playwright waits:
- `page.wait_for_selector()` with specific timeouts
- `page.wait_for_function()` for dynamic content
- `page.wait_for_timeout()` only for brief delays after actions

#### 4. Optimized Guild Discovery
**Problem**: Clicking through every Discord server was slow and error-prone.
**Solution**: JavaScript-based extraction using `page.evaluate()` to get guild information without clicking:
```javascript
const elements = document.querySelectorAll('[data-list-id="guildsnav"] [data-dnd-name]');
// Extract guild IDs and names directly from DOM
```

#### 5. Deterministic Scrolling
**Problem**: `PageUp` key presses for message scrolling were unpredictable.
**Solution**: Use `element.scroll_into_view_if_needed()` for precise scrolling control.

#### 6. Sequential Test Execution
**Problem**: Parallel test execution caused resource conflicts.
**Solution**: Added `-n 0` to `pytest.ini` to force sequential execution.

### Future Simplification Opportunities

#### Option 1: Session Reuse with Smart Reset
Instead of complete browser recreation, implement selective reset:
```python
# Only reset when necessary, keep browser alive
if browser_in_bad_state:
    await page.reload()
    await navigate_to_home()
else:
    # Just navigate to clean state
    await page.goto("https://discord.com/channels/@me")
```

#### Option 2: Stateless Tool Operations
Make each tool completely stateless by passing all required context:
```python
async def get_guild_channels(email: str, password: str, guild_id: str):
    # Create browser, do operation, close browser
    # No shared state between calls
```

#### Option 3: Browser Pool
Maintain a pool of browser instances for better resource management:
```python
class BrowserPool:
    async def get_browser(self) -> Browser:
        # Return available browser or create new one
    async def return_browser(self, browser: Browser):
        # Reset and return to pool
```

### Testing Strategy
- Always run `uv run pytest -v tests/test_integration.py` to verify changes
- Use comprehensive logging during development to identify hanging points
- Monitor browser close operations with timeouts to prevent infinite hangs
- Keep the complete reset mechanism as fallback for maximum reliability

### Performance Notes
- Complete browser reset adds ~2-3 seconds per tool call
- Cookie persistence (`discord_mcp_cookies.json`) eliminates re-login overhead
- JavaScript extraction is 10x faster than clicking through UI elements
- Sequential execution is slower but eliminates race conditions

The current implementation prioritizes **reliability over speed** - all tests pass consistently, which is essential for production use. Future optimizations should maintain this reliability while improving performance.

## Critical Bug Discovery: Message Extraction Order Issue

**Date**: June 9, 2025
**Issue**: Discord message extraction has counterintuitive behavior where requesting MORE messages reveals NEWER messages instead of older ones.

### The Problem
When using `max_messages` parameter:
- `max_messages: 20` → Shows messages from May 18, 2025 as "newest"
- `max_messages: 100` → Reveals actual newest messages from June 9, 2025

This is **backwards** from expected behavior where more messages should go further back in history, not forward to newer content.

### Root Cause Investigation Needed
This suggests a fundamental issue in the message extraction logic:
1. **Scrolling Logic**: The initial scroll-to-bottom might not be reaching the actual newest messages
2. **Message Selection**: The element selection might be picking up messages in wrong order
3. **Sorting Issue**: Messages might be getting sorted incorrectly before limiting
4. **Discord DOM Structure**: Discord's lazy loading might be serving different content based on scroll position

### Current Workaround
- **Always use high `max_messages` count** (100+) when looking for recent messages
- Cannot trust low message counts to show actual newest content

### Fix Required
The message extraction logic in `get_channel_messages()` needs investigation to ensure:
1. Proper scroll positioning reaches absolute newest messages first
2. Message elements are selected in correct chronological order
3. Sorting and limiting happens correctly

This is a **critical reliability issue** that affects the core functionality of reading recent messages.