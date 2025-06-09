import typing as tp
from datetime import datetime, timezone, timedelta
from .client import DiscordWebClient, DiscordMessage, DiscordChannel


class MessageBatch(tp.NamedTuple):
    messages: list[DiscordMessage]
    has_more: bool
    oldest_message_id: str | None


def _filter_messages_by_time(
    messages: list[DiscordMessage],
    after: datetime | None = None,
    before: datetime | None = None,
) -> list[DiscordMessage]:
    filtered = messages

    if after:
        filtered = [m for m in filtered if m.timestamp > after]

    if before:
        filtered = [m for m in filtered if m.timestamp < before]

    return filtered


def _get_last_24_hours() -> datetime:
    return datetime.now(timezone.utc) - timedelta(hours=24)


async def read_recent_messages(
    client: DiscordWebClient,
    channel_id: str,
    hours_back: int = 24,
    max_messages: int = 1000,
) -> list[DiscordMessage]:
    cutoff_time = datetime.now(timezone.utc) - timedelta(hours=hours_back)
    all_messages = []
    last_message_id = None

    while len(all_messages) < max_messages:
        batch_size = min(100, max_messages - len(all_messages))

        messages = await client.get_channel_messages(
            channel_id=channel_id, limit=batch_size, before=last_message_id
        )

        if not messages:
            break

        recent_messages = _filter_messages_by_time(messages, after=cutoff_time)
        all_messages.extend(recent_messages)

        oldest_message = messages[-1]
        if oldest_message.timestamp < cutoff_time:
            break

        last_message_id = oldest_message.id

    return sorted(all_messages, key=lambda m: m.timestamp, reverse=True)


async def read_messages_paginated(
    client: DiscordWebClient,
    channel_id: str,
    limit: int = 100,
    before_message_id: str | None = None,
    after_time: datetime | None = None,
) -> MessageBatch:
    messages = await client.get_channel_messages(
        channel_id=channel_id, limit=min(limit, 100), before=before_message_id
    )

    if after_time:
        messages = _filter_messages_by_time(messages, after=after_time)

    has_more = len(messages) == min(limit, 100)
    oldest_id = messages[-1].id if messages else None

    return MessageBatch(
        messages=messages, has_more=has_more, oldest_message_id=oldest_id
    )


async def aggregate_channel_messages(
    client: DiscordWebClient,
    channels: list[DiscordChannel],
    hours_back: int = 24,
    max_per_channel: int = 200,
) -> dict[str, list[DiscordMessage]]:
    results = {}

    for channel in channels:
        try:
            messages = await read_recent_messages(
                client=client,
                channel_id=channel.id,
                hours_back=hours_back,
                max_messages=max_per_channel,
            )
            results[channel.id] = messages
        except Exception:
            results[channel.id] = []

    return results


def summarize_messages_by_channel(
    messages_by_channel: dict[str, list[DiscordMessage]], channels: list[DiscordChannel]
) -> dict[str, dict[str, tp.Any]]:
    channel_map = {c.id: c for c in channels}
    summary = {}

    for channel_id, messages in messages_by_channel.items():
        channel = channel_map.get(channel_id)
        if not channel:
            continue

        summary[channel_id] = {
            "channel_name": channel.name,
            "message_count": len(messages),
            "latest_message": messages[0].timestamp.isoformat() if messages else None,
            "oldest_message": messages[-1].timestamp.isoformat() if messages else None,
            "unique_authors": len(set(m.author_id for m in messages)),
        }

    return summary
