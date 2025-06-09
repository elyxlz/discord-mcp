import pytest
import json
from src.discord_mcp.server import call_tool


@pytest.mark.integration
@pytest.mark.browser
@pytest.mark.slow
@pytest.mark.asyncio
async def test_mcp_get_servers_tool(real_config):
    """Test the get_servers MCP tool."""
    # Test get_servers tool
    result = await call_tool("get_servers", {})
    assert isinstance(result, list)
    assert len(result) == 1

    servers_data = json.loads(result[0].text)  # type: ignore
    print(f"Servers response: {servers_data}")

    # Check if it's an error response
    if isinstance(servers_data, dict) and "error" in servers_data:
        print(f"Error in response: {servers_data['error']}")
        raise Exception(f"Tool returned error: {servers_data['error']}")

    assert isinstance(servers_data, list)
    assert len(servers_data) > 0
    print(f"MCP server found {len(servers_data)} guilds")

    # Should find Tech Tavern server
    tech_tavern_server = None
    for server in servers_data:
        if "Tech Tavern" in server["name"]:
            tech_tavern_server = server
            break

    assert tech_tavern_server is not None, "Tech Tavern server should be found via MCP"
    assert tech_tavern_server["id"] == "780179350682599445"
    print(f"Found Tech Tavern server: {tech_tavern_server['name']}")


@pytest.mark.integration
@pytest.mark.browser
@pytest.mark.slow
@pytest.mark.asyncio
async def test_mcp_get_channels_tool(real_config):
    """Test the get_channels MCP tool."""
    tech_tavern_id = "780179350682599445"

    # Test get_channels tool
    result = await call_tool("get_channels", {"server_id": tech_tavern_id})
    assert isinstance(result, list)
    assert len(result) == 1

    channels_data = json.loads(result[0].text)  # type: ignore
    assert isinstance(channels_data, list)
    assert len(channels_data) > 0, (
        "Expected to find channels in Tech Tavern via MCP, but found 0"
    )
    print(f"MCP found {len(channels_data)} channels in Tech Tavern")

    for channel_info in channels_data:
        assert "id" in channel_info
        assert "name" in channel_info
        assert "type" in channel_info
        print(f"  {channel_info['name']} (ID: {channel_info['id']})")


@pytest.mark.integration
@pytest.mark.browser
@pytest.mark.slow
@pytest.mark.asyncio
async def test_mcp_read_messages_tool(real_config):
    """Test the read_messages MCP tool."""
    test_channel_id = "825674804077789214"

    # Test read_messages tool
    print(f"Testing MCP message reading from channel ID: {test_channel_id}")
    result = await call_tool(
        "read_messages", {"channel_id": test_channel_id, "max_messages": 5}
    )

    assert isinstance(result, list)
    assert len(result) == 1

    messages_data = json.loads(result[0].text)  # type: ignore
    assert isinstance(messages_data, list)
    print(f"MCP read {len(messages_data)} messages from channel {test_channel_id}")

    for message_info in messages_data:
        assert "id" in message_info
        assert "content" in message_info
        assert "author_name" in message_info
        assert "timestamp" in message_info
        assert "attachments" in message_info
