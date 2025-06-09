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
    server_id: str, channel_id: str, max_messages: int, hours_back: int = 24
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
async def send_message(
    server_id: str, channel_id: str, content: str
) -> dict[str, tp.Any]:
    """Send a message to a specific Discord channel. Long messages are automatically split."""
    if len(content) == 0:
        raise ValueError("Message content cannot be empty")

    # Split long messages into chunks of 2000 characters or less
    chunks = []
    if len(content) <= 2000:
        chunks = [content]
    else:
        # Split by newlines first to avoid breaking paragraphs
        lines = content.split("\n")
        current_chunk = ""

        for line in lines:
            # If single line is too long, split it by words
            if len(line) > 2000:
                words = line.split(" ")
                current_line = ""
                for word in words:
                    if len(current_line + " " + word) <= 2000:
                        current_line += (" " + word) if current_line else word
                    else:
                        if current_line:
                            if len(current_chunk + "\n" + current_line) <= 2000:
                                current_chunk += (
                                    ("\n" + current_line)
                                    if current_chunk
                                    else current_line
                                )
                            else:
                                chunks.append(current_chunk)
                                current_chunk = current_line
                            current_line = word
                        else:
                            # Single word too long, truncate it
                            current_line = word[:2000]
                if current_line:
                    if len(current_chunk + "\n" + current_line) <= 2000:
                        current_chunk += (
                            ("\n" + current_line) if current_chunk else current_line
                        )
                    else:
                        chunks.append(current_chunk)
                        current_chunk = current_line
            else:
                # Normal line length
                if len(current_chunk + "\n" + line) <= 2000:
                    current_chunk += ("\n" + line) if current_chunk else line
                else:
                    chunks.append(current_chunk)
                    current_chunk = line

        if current_chunk:
            chunks.append(current_chunk)

    ctx = mcp.get_context()
    discord_ctx = tp.cast(DiscordContext, ctx.request_context.lifespan_context)

    message_ids = []
    for i, chunk in enumerate(chunks):

        async def operation(state, chunk_content=chunk):
            return await send_discord_message(
                state, server_id, channel_id, chunk_content
            )

        message_id = await _execute_with_fresh_client(discord_ctx, operation)
        message_ids.append(message_id)

        # Small delay between messages to avoid rate limiting
        if i < len(chunks) - 1:
            await asyncio.sleep(0.5)

    return {
        "message_ids": message_ids,
        "status": "sent",
        "chunks": len(chunks),
        "total_length": len(content),
    }


def main():
    mcp.run()


if __name__ == "__main__":
    main()
