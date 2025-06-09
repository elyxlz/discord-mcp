import asyncio
import typing as tp
from contextlib import asynccontextmanager
from collections.abc import AsyncIterator
from dataclasses import dataclass

from mcp.server.fastmcp import FastMCP
from .logger import logger

from .client import (
    create_client_state,
    get_guilds,
    get_guild_channels,
    send_message as send_discord_message,
    close_client,
)
from .config import load_config
from .messages import read_recent_messages


@dataclass
class DiscordContext:
    client_state: tp.Any
    config: tp.Any
    client_lock: asyncio.Lock


@asynccontextmanager
async def discord_lifespan(server: FastMCP) -> AsyncIterator[DiscordContext]:
    config = load_config()
    client_state = create_client_state(config.email, config.password, config.headless)
    client_lock = asyncio.Lock()

    logger.debug("Discord MCP server starting up")
    try:
        yield DiscordContext(
            client_state=client_state, config=config, client_lock=client_lock
        )
    finally:
        logger.debug("Discord MCP server shutting down")
        try:
            await asyncio.wait_for(close_client(client_state), timeout=10.0)
        except Exception as e:
            logger.warning(f"Error closing client during shutdown: {e}")


mcp = FastMCP("discord-mcp", lifespan=discord_lifespan)


@mcp.tool()
async def get_servers() -> list[dict[str, str]]:
    """List all Discord servers (guilds) you have access to"""
    ctx = mcp.get_context()
    discord_ctx = tp.cast(DiscordContext, ctx.request_context.lifespan_context)

    async with discord_ctx.client_lock:
        logger.debug("Executing get_servers tool")
        try:
            await asyncio.wait_for(close_client(discord_ctx.client_state), timeout=10.0)
        except Exception as e:
            logger.warning(f"Error closing client: {e}")

        # Create completely fresh client state for each tool call
        fresh_client_state = create_client_state(
            discord_ctx.config.email,
            discord_ctx.config.password,
            True,  # Force headless=True for all operations
        )

        fresh_client_state, guilds = await get_guilds(fresh_client_state)
        logger.debug(f"Retrieved {len(guilds)} guilds")

        result = [{"id": g.id, "name": g.name} for g in guilds]
        logger.debug(f"Prepared guild data: {result}")
        return result


@mcp.tool()
async def get_channels(server_id: str) -> list[dict[str, str]]:
    """List all channels in a specific Discord server"""
    ctx = mcp.get_context()
    discord_ctx = tp.cast(DiscordContext, ctx.request_context.lifespan_context)

    async with discord_ctx.client_lock:
        logger.debug(f"Executing get_channels tool for server {server_id}")
        try:
            await asyncio.wait_for(close_client(discord_ctx.client_state), timeout=10.0)
        except Exception as e:
            logger.warning(f"Error closing client: {e}")

        # Create completely fresh client state for each tool call
        fresh_client_state = create_client_state(
            discord_ctx.config.email,
            discord_ctx.config.password,
            True,  # Force headless=True for all operations
        )

        fresh_client_state, channels = await get_guild_channels(
            fresh_client_state, server_id
        )
        logger.debug(f"Retrieved {len(channels)} channels")

        result = [
            {
                "id": c.id,
                "name": c.name,
                "type": c.type,
            }
            for c in channels
        ]
        logger.debug(f"Prepared channel data: {[c['name'] for c in result]}")
        return result


@mcp.tool()
async def read_messages(
    server_id: str, channel_id: str, hours_back: int = 24, max_messages: int = 100
) -> list[dict[str, tp.Any]]:
    """Read recent messages from a specific channel"""
    ctx = mcp.get_context()
    discord_ctx = tp.cast(DiscordContext, ctx.request_context.lifespan_context)

    if not (1 <= hours_back <= 168):
        raise ValueError("hours_back must be between 1 and 168")
    if not (1 <= max_messages <= 1000):
        raise ValueError("max_messages must be between 1 and 1000")

    async with discord_ctx.client_lock:
        logger.debug(
            f"Executing read_messages tool for server {server_id}, channel {channel_id}, {hours_back}h back, max {max_messages}"
        )
        try:
            await asyncio.wait_for(close_client(discord_ctx.client_state), timeout=10.0)
        except Exception as e:
            logger.warning(f"Error closing client: {e}")

        # Create completely fresh client state for each tool call
        fresh_client_state = create_client_state(
            discord_ctx.config.email,
            discord_ctx.config.password,
            True,  # Force headless=True for all operations
        )

        fresh_client_state, messages = await read_recent_messages(
            fresh_client_state, server_id, channel_id, hours_back, max_messages
        )
        logger.debug(f"Retrieved {len(messages)} messages")

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
        logger.debug(f"Prepared message data for {len(result)} messages")
        return result


@mcp.tool()
async def send_message(server_id: str, channel_id: str, content: str) -> dict[str, str]:
    """Send a message to a specific Discord channel"""
    ctx = mcp.get_context()
    discord_ctx = tp.cast(DiscordContext, ctx.request_context.lifespan_context)

    if not (1 <= len(content) <= 2000):
        raise ValueError("Message content must be between 1 and 2000 characters")

    async with discord_ctx.client_lock:
        logger.debug(
            f"Executing send_message tool to server {server_id}, channel {channel_id} with content: {content[:50]}..."
        )
        try:
            await asyncio.wait_for(close_client(discord_ctx.client_state), timeout=10.0)
        except Exception as e:
            logger.warning(f"Error closing client: {e}")

        # Create completely fresh client state for each tool call
        fresh_client_state = create_client_state(
            discord_ctx.config.email,
            discord_ctx.config.password,
            True,  # Force headless=True for all operations
        )

        fresh_client_state, message_id = await send_discord_message(
            fresh_client_state, server_id, channel_id, content
        )
        logger.debug(f"Message sent successfully with ID: {message_id}")

        return {"message_id": message_id, "status": "sent"}


def main():
    mcp.run()


if __name__ == "__main__":
    main()
