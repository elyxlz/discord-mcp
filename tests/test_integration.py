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

    # Should find Audiogen Company server
    audiogen_server = None
    for server in servers_data:
        if "Audiogen Company" in server["name"]:
            audiogen_server = server
            break

    assert audiogen_server is not None, (
        "Audiogen Company server should be found via MCP"
    )
    assert audiogen_server["id"] == "1353689257796960296"
    print(f"Found Audiogen Company server: {audiogen_server['name']}")


@pytest.mark.integration
@pytest.mark.browser
@pytest.mark.slow
@pytest.mark.asyncio
async def test_mcp_get_channels_tool(real_config):
    """Test the get_channels MCP tool."""
    audiogen_id = "1353689257796960296"

    # Test get_channels tool
    result = await call_tool("get_channels", {"server_id": audiogen_id})
    assert isinstance(result, list)
    assert len(result) == 1

    channels_data = json.loads(result[0].text)  # type: ignore
    assert isinstance(channels_data, list)
    assert len(channels_data) > 0, (
        "Expected to find channels in Audiogen Company via MCP, but found 0"
    )
    print(f"MCP found {len(channels_data)} channels in Audiogen Company")

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
    audiogen_server_id = "1353689257796960296"
    test_channel_id = "1353694097696755766"  # Use Audiogen general channel

    # Test read_messages tool
    print(
        f"Testing MCP message reading from server {audiogen_server_id}, channel {test_channel_id}"
    )
    result = await call_tool(
        "read_messages",
        {
            "server_id": audiogen_server_id,
            "channel_id": test_channel_id,
            "max_messages": 5,
        },
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


@pytest.mark.integration
@pytest.mark.browser
@pytest.mark.slow
@pytest.mark.asyncio
async def test_mcp_send_message_tool(real_config):
    """Test the send_message MCP tool."""
    audiogen_server_id = "1353689257796960296"
    audiogen_channel_id = "1353694097696755766"
    test_message = "hi from discord mcp"

    # Test send_message tool
    print(
        f"Testing MCP message sending to server {audiogen_server_id}, channel {audiogen_channel_id}"
    )
    result = await call_tool(
        "send_message",
        {
            "server_id": audiogen_server_id,
            "channel_id": audiogen_channel_id,
            "content": test_message,
        },
    )

    assert isinstance(result, list)
    assert len(result) == 1

    response_data = json.loads(result[0].text)  # type: ignore

    # Check if it's an error response
    if isinstance(response_data, dict) and "error" in response_data:
        print(f"Error in response: {response_data['error']}")
        raise Exception(f"Tool returned error: {response_data['error']}")

    assert isinstance(response_data, dict)
    assert "message_id" in response_data
    assert "status" in response_data
    assert response_data["status"] == "sent"
    print(f"MCP successfully sent message with ID: {response_data['message_id']}")
