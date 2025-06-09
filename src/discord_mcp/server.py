import asyncio
import json
import typing as tp

from mcp.server import Server
from mcp.types import Tool, TextContent

from .client import (
    create_client_state,
    get_guilds,
    get_guild_channels,
    send_message,
    close_client,
)
from .config import load_config
from .messages import read_recent_messages


server = Server("discord-mcp")
config = load_config()
client_state = create_client_state(config.email, config.password, config.headless)
_CLIENT_LOCK = asyncio.Lock()


async def reset_global_client_state():
    global client_state
    await close_client(client_state)
    client_state = create_client_state(config.email, config.password, config.headless)


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_servers",
            description="List all Discord servers (guilds) you have access to",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_channels",
            description="List all channels in a specific Discord server",
            inputSchema={
                "type": "object",
                "properties": {
                    "server_id": {
                        "type": "string",
                        "description": "Discord server (guild) ID",
                    },
                },
                "required": ["server_id"],
            },
        ),
        Tool(
            name="read_messages",
            description="Read recent messages from a specific channel",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Discord channel ID",
                    },
                    "hours_back": {
                        "type": "integer",
                        "description": "How many hours back to read messages",
                        "default": 24,
                    },
                    "max_messages": {
                        "type": "integer",
                        "description": "Maximum number of messages to read",
                        "default": 100,
                    },
                },
                "required": ["channel_id"],
            },
        ),
        Tool(
            name="send_message",
            description="Send a message to a specific Discord channel",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_id": {
                        "type": "string",
                        "description": "Discord channel ID",
                    },
                    "content": {
                        "type": "string",
                        "description": "Message content to send",
                    },
                },
                "required": ["channel_id", "content"],
            },
        ),
    ]


@server.call_tool()
async def call_tool(name: str, arguments: dict[str, tp.Any]) -> list[TextContent]:
    global client_state

    async with _CLIENT_LOCK:
        try:
            try:
                await asyncio.wait_for(close_client(client_state), timeout=10.0)
            except Exception:
                pass

            client_state = create_client_state(
                config.email, config.password, config.headless
            )

            if name == "get_servers":
                client_state, guilds = await get_guilds(client_state)
                result = [{"id": g.id, "name": g.name} for g in guilds]
                response = [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "get_channels":
                server_id = arguments["server_id"]
                client_state, channels = await get_guild_channels(
                    client_state, server_id
                )
                result = [
                    {
                        "id": c.id,
                        "name": c.name,
                        "type": c.type,
                    }
                    for c in channels
                ]
                response = [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "read_messages":
                channel_id = arguments["channel_id"]
                hours_back = arguments.get("hours_back", config.default_hours_back)
                max_messages = arguments.get("max_messages", 100)

                client_state, messages = await read_recent_messages(
                    client_state, channel_id, hours_back, max_messages
                )
                result = [
                    {
                        "id": m.id,
                        "content": m.content,
                        "author_name": m.author_name,
                        "timestamp": m.timestamp.isoformat(),
                        "attachments": m.attachments,
                    }
                    for m in messages
                ]
                response = [TextContent(type="text", text=json.dumps(result, indent=2))]

            elif name == "send_message":
                channel_id = arguments["channel_id"]
                content = arguments["content"]
                client_state, message_id = await send_message(
                    client_state, channel_id, content
                )
                result = {"message_id": message_id, "status": "sent"}
                response = [TextContent(type="text", text=json.dumps(result, indent=2))]

            else:
                response = [TextContent(type="text", text=f"Unknown tool: {name}")]

            return response
        except Exception as e:
            error_result = {"error": str(e), "tool": name, "arguments": arguments}
            return [TextContent(type="text", text=json.dumps(error_result, indent=2))]


async def main():
    from mcp.server.stdio import stdio_server

    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream, write_stream, server.create_initialization_options()
        )


if __name__ == "__main__":
    asyncio.run(main())
