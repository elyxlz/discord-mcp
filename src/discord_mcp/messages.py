from datetime import datetime, timezone, timedelta
from .client import ClientState, DiscordMessage, get_channel_messages


async def read_recent_messages(
    state: ClientState,
    channel_id: str,
    hours_back: int = 24,
    max_messages: int = 1000,
) -> tuple[ClientState, list[DiscordMessage]]:
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    all_messages = []
    last_message_id = None

    while len(all_messages) < max_messages:
        batch_size = min(100, max_messages - len(all_messages))

        state, messages = await get_channel_messages(
            state, channel_id=channel_id, limit=batch_size, before=last_message_id
        )

        if not messages:
            break

        recent_messages = [m for m in messages if m.timestamp > cutoff_time]
        all_messages.extend(recent_messages)

        oldest_message = messages[-1]
        if oldest_message.timestamp < cutoff_time:
            break

        last_message_id = oldest_message.id

    return state, sorted(all_messages, key=lambda m: m.timestamp, reverse=True)
