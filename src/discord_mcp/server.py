import asyncio
import json
import typing as tp

from mcp.server import Server
from mcp.types import Tool, TextContent

from .client import DiscordWebClient
from .config import load_config
from .discovery import (
    discover_channels_by_keywords,
    discover_channels_by_pattern,
    get_announcement_channels,
    get_feedback_channels,
)
from .messages import (
    read_recent_messages,
    aggregate_channel_messages,
    summarize_messages_by_channel,
)


server = Server("discord-mcp")
config = load_config()
discord_client = DiscordWebClient(config.email, config.password, config.headless)


@server.list_tools()
async def list_tools() -> list[Tool]:
    return [
        Tool(
            name="get_servers",
            description="List all Discord servers (guilds) the bot has access to",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="discover_channels",
            description="Find channels by keyword patterns across servers",
            inputSchema={
                "type": "object",
                "properties": {
                    "keywords": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Keywords to search for in channel names",
                    },
                    "guild_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of guild IDs to limit search",
                    },
                },
                "required": ["keywords"],
            },
        ),
        Tool(
            name="search_channels",
            description="Search for channels using regex pattern",
            inputSchema={
                "type": "object",
                "properties": {
                    "pattern": {
                        "type": "string",
                        "description": "Regex pattern to match channel names",
                    },
                    "guild_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Optional list of guild IDs to limit search",
                    },
                },
                "required": ["pattern"],
            },
        ),
        Tool(
            name="get_announcement_channels",
            description="Find channels that likely contain announcements",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="get_feedback_channels",
            description="Find channels that likely contain feedback or discussions",
            inputSchema={"type": "object", "properties": {}, "required": []},
        ),
        Tool(
            name="read_messages",
            description="Read recent messages from a channel with time filtering",
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
                        "default": 200,
                    },
                },
                "required": ["channel_id"],
            },
        ),
        Tool(
            name="read_channel_batch",
            description="Read messages from multiple channels and aggregate results",
            inputSchema={
                "type": "object",
                "properties": {
                    "channel_ids": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "List of Discord channel IDs",
                    },
                    "hours_back": {
                        "type": "integer",
                        "description": "How many hours back to read messages",
                        "default": 24,
                    },
                    "max_per_channel": {
                        "type": "integer",
                        "description": "Maximum messages per channel",
                        "default": 100,
                    },
                    "summary_only": {
                        "type": "boolean",
                        "description": "Return only summary statistics",
                        "default": False,
                    },
                },
                "required": ["channel_ids"],
            },
        ),
        Tool(
            name="send_message",
            description="Send a message to a Discord channel",
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
    try:
        if name == "get_servers":
            guilds = await discord_client.get_guilds()
            result = [{"id": g.id, "name": g.name, "icon": g.icon} for g in guilds]
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "discover_channels":
            keywords = arguments["keywords"]
            guild_ids = arguments.get("guild_ids")

            matches = await discover_channels_by_keywords(
                discord_client, keywords, guild_ids
            )

            result = [
                {
                    "channel_id": m.channel.id,
                    "channel_name": m.channel.name,
                    "guild_id": m.guild.id,
                    "guild_name": m.guild.name,
                    "match_reason": m.match_reason,
                }
                for m in matches
            ]
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "search_channels":
            pattern = arguments["pattern"]
            guild_ids = arguments.get("guild_ids")

            matches = await discover_channels_by_pattern(
                discord_client, pattern, guild_ids
            )

            result = [
                {
                    "channel_id": m.channel.id,
                    "channel_name": m.channel.name,
                    "guild_id": m.guild.id,
                    "guild_name": m.guild.name,
                    "match_reason": m.match_reason,
                }
                for m in matches
            ]
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_announcement_channels":
            matches = await get_announcement_channels(discord_client)

            result = [
                {
                    "channel_id": m.channel.id,
                    "channel_name": m.channel.name,
                    "guild_id": m.guild.id,
                    "guild_name": m.guild.name,
                    "match_reason": m.match_reason,
                }
                for m in matches
            ]
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "get_feedback_channels":
            matches = await get_feedback_channels(discord_client)

            result = [
                {
                    "channel_id": m.channel.id,
                    "channel_name": m.channel.name,
                    "guild_id": m.guild.id,
                    "guild_name": m.guild.name,
                    "match_reason": m.match_reason,
                }
                for m in matches
            ]
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "read_messages":
            channel_id = arguments["channel_id"]
            hours_back = arguments.get("hours_back", config.default_hours_back)
            max_messages = arguments.get(
                "max_messages", config.max_messages_per_channel
            )

            messages = await read_recent_messages(
                discord_client, channel_id, hours_back, max_messages
            )

            result = [
                {
                    "id": m.id,
                    "content": m.content,
                    "author_name": m.author_name,
                    "author_id": m.author_id,
                    "timestamp": m.timestamp.isoformat(),
                    "attachments": m.attachments,
                }
                for m in messages
            ]
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "read_channel_batch":
            channel_ids = arguments["channel_ids"]
            hours_back = arguments.get("hours_back", config.default_hours_back)
            max_per_channel = arguments.get("max_per_channel", 100)
            summary_only = arguments.get("summary_only", False)

            channels = []
            for channel_id in channel_ids:
                try:
                    guilds = await discord_client.get_guilds()
                    for guild in guilds:
                        guild_channels = await discord_client.get_guild_channels(
                            guild.id
                        )
                        for channel in guild_channels:
                            if channel.id == channel_id:
                                channels.append(channel)
                                break
                except Exception:
                    continue

            messages_by_channel = await aggregate_channel_messages(
                discord_client, channels, hours_back, max_per_channel
            )

            if summary_only:
                result = summarize_messages_by_channel(messages_by_channel, channels)
            else:
                result = {}
                for channel_id, messages in messages_by_channel.items():
                    result[channel_id] = [
                        {
                            "id": m.id,
                            "content": m.content,
                            "author_name": m.author_name,
                            "timestamp": m.timestamp.isoformat(),
                        }
                        for m in messages
                    ]

            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        elif name == "send_message":
            channel_id = arguments["channel_id"]
            content = arguments["content"]

            message_id = await discord_client.send_message(channel_id, content)

            result = {
                "success": True,
                "message_id": message_id,
                "channel_id": channel_id,
            }
            return [TextContent(type="text", text=json.dumps(result, indent=2))]

        else:
            return [TextContent(type="text", text=f"Unknown tool: {name}")]

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
