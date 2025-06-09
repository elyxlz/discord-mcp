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
    all_messages = []
    last_message_id = None

    while len(all_messages) < max_messages:
        batch_size = min(100, max_messages - len(all_messages))
        logger.debug(
            f"Fetching batch of {batch_size} messages, before={last_message_id}"
        )

        state, messages = await get_channel_messages(
            state,
            server_id=server_id,
            channel_id=channel_id,
            limit=batch_size,
            before=last_message_id,
        )
        logger.debug(f"Retrieved {len(messages)} messages from batch")

        if not messages:
            logger.debug("No more messages available, breaking")
            break

        recent_messages = [m for m in messages if m.timestamp > cutoff_time]
        logger.debug(
            f"Filtered to {len(recent_messages)} recent messages (after {cutoff_time})"
        )
        all_messages.extend(recent_messages)

        oldest_message = messages[-1]
        logger.debug(f"Oldest message timestamp: {oldest_message.timestamp}")
        if oldest_message.timestamp < cutoff_time:
            logger.debug("Reached cutoff time, breaking")
            break

        last_message_id = oldest_message.id
        logger.debug(f"Continuing with last_message_id: {last_message_id}")

    logger.debug(
        f"read_recent_messages completed, returning {len(all_messages)} total messages"
    )
    return state, sorted(all_messages, key=lambda m: m.timestamp, reverse=True)
