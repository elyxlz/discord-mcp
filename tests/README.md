# Discord MCP Tests

This directory contains integration tests for the Discord MCP server using real Discord browser automation.

## Setup

1. Install test dependencies:
```bash
uv sync --group test
```

2. Set your Discord credentials:
```bash
export DISCORD_EMAIL="your_email@example.com"
export DISCORD_PASSWORD="your_password"
```

## Running Tests

Run all integration tests:
```bash
uv run pytest
```

Run with verbose output:
```bash
uv run pytest -v
```

Run specific test:
```bash
uv run pytest tests/test_integration.py::TestDiscordMCPIntegration::test_client_login_and_guilds
```

## Test Coverage

The integration tests cover:

- **Client functionality**: Login, guild discovery, channel detection, message reading
- **Discovery features**: Finding announcement/feedback channels by keywords and patterns
- **Message operations**: Reading recent messages, time filtering, batch operations
- **MCP server tools**: All server endpoints including get_servers, discover_channels, read_messages
- **Error handling**: Invalid channels, cleanup, edge cases

## Notes

- Tests run with headful browser (you'll see Chrome windows open)
- Tests use real Discord credentials and access real servers
- Tests are marked as `@pytest.mark.integration` for organization
- Each test automatically cleans up browser resources
- Tests may be slow due to Discord rate limits and page load times