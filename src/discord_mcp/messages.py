from datetime import datetime, timezone, timedelta
from .client import ClientState, DiscordMessage, get_channel_messages
from .logger import logger


async def read_recent_messages(
    state: ClientState,
    server_id: str,
    channel_id: str,
    hours_back: int = 24,
    max_messages: int = 1000,
) -> tuple[ClientState, list[DiscordMessage]]:
    logger.debug(
        f"read_recent_messages called for server {server_id}, channel {channel_id}, {hours_back}h back, max {max_messages}"
    )
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    logger.debug(f"Cutoff time set to: {cutoff_time}")

    # Get messages in chronological order (newest first)
    state, all_messages = await get_channel_messages(
        state,
        server_id=server_id,
        channel_id=channel_id,
        limit=max_messages,
    )
    logger.debug(f"Retrieved {len(all_messages)} total messages")

    # Filter to only recent messages within the time window
    recent_messages = [m for m in all_messages if m.timestamp > cutoff_time]
    logger.debug(
        f"Filtered to {len(recent_messages)} messages after cutoff {cutoff_time}"
    )

    logger.debug(
        f"read_recent_messages completed, returning {len(recent_messages)} messages in chronological order (newest first)"
    )
    return state, recent_messages
