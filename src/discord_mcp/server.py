import asyncio
import typing as tp
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator, Callable
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP
from .logger import logger
from .client import (
    create_client_state,
    get_guilds,
    get_guild_channels,
    send_message as send_discord_message,
)
from .config import load_config
from .messages import read_recent_messages


@dataclass
class DiscordContext:
    config: tp.Any
    client_lock: asyncio.Lock


@asynccontextmanager
async def discord_lifespan(server: FastMCP) -> AsyncIterator[DiscordContext]:
    config = load_config()
    client_lock = asyncio.Lock()
    logger.debug("Discord MCP server starting up")
    try:
        yield DiscordContext(config=config, client_lock=client_lock)
    finally:
        logger.debug("Discord MCP server shutting down")


async def _execute_with_fresh_client[T](
    discord_ctx: DiscordContext,
    operation: Callable[[tp.Any], tp.Awaitable[tuple[tp.Any, T]]],
) -> T:
    """Execute Discord operation with fresh client state"""
    async with discord_ctx.client_lock:
        client_state = create_client_state(
            discord_ctx.config.email, discord_ctx.config.password, True
        )
        _, result = await operation(client_state)
        return result


mcp = FastMCP("discord-mcp", lifespan=discord_lifespan)


@mcp.tool()
async def get_servers() -> list[dict[str, str]]:
    """List all Discord servers (guilds) you have access to"""
    ctx = mcp.get_context()
    discord_ctx = tp.cast(DiscordContext, ctx.request_context.lifespan_context)

    guilds = await _execute_with_fresh_client(discord_ctx, get_guilds)
    return [{"id": g.id, "name": g.name} for g in guilds]


@mcp.tool()
async def get_channels(server_id: str) -> list[dict[str, str]]:
    """List all channels in a specific Discord server"""
    ctx = mcp.get_context()
    discord_ctx = tp.cast(DiscordContext, ctx.request_context.lifespan_context)

    async def operation(state):
        return await get_guild_channels(state, server_id)

    channels = await _execute_with_fresh_client(discord_ctx, operation)
    return [{"id": c.id, "name": c.name, "type": str(c.type)} for c in channels]


@mcp.tool()
async def read_messages(
    server_id: str, channel_id: str, hours_back: int = 24, max_messages: int = 100
) -> list[dict[str, tp.Any]]:
    """Read recent messages from a specific channel"""
    if not (1 <= hours_back <= 8760):
        raise ValueError("hours_back must be between 1 and 8760 (1 year)")
    if not (1 <= max_messages <= 1000):
        raise ValueError("max_messages must be between 1 and 1000")

    ctx = mcp.get_context()
    discord_ctx = tp.cast(DiscordContext, ctx.request_context.lifespan_context)

    async def operation(state):
        return await read_recent_messages(
            state, server_id, channel_id, hours_back, max_messages
        )

    messages = await _execute_with_fresh_client(discord_ctx, operation)
    return [
        {
            "id": m.id,
            "content": m.content,
            "author_name": m.author_name,
            "timestamp": m.timestamp.isoformat(),
            "attachments": m.attachments,
        }
        for m in messages
    ]


@mcp.tool()
async def send_message(server_id: str, channel_id: str, content: str) -> dict[str, str]:
    """Send a message to a specific Discord channel"""
    if not (1 <= len(content) <= 2000):
        raise ValueError("Message content must be between 1 and 2000 characters")

    ctx = mcp.get_context()
    discord_ctx = tp.cast(DiscordContext, ctx.request_context.lifespan_context)

    async def operation(state):
        return await send_discord_message(state, server_id, channel_id, content)

    message_id = await _execute_with_fresh_client(discord_ctx, operation)
    return {"message_id": message_id, "status": "sent"}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
