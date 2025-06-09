import typing as tp
import re
from .client import DiscordWebClient, DiscordChannel, DiscordGuild


class ChannelMatch(tp.NamedTuple):
    channel: DiscordChannel
    guild: DiscordGuild
    match_reason: str


def _matches_keywords(channel_name: str, keywords: list[str]) -> bool:
    name_lower = channel_name.lower()
    return any(keyword.lower() in name_lower for keyword in keywords)


def _matches_pattern(channel_name: str, pattern: str) -> bool:
    try:
        return bool(re.search(pattern, channel_name, re.IGNORECASE))
    except re.error:
        return False


async def discover_channels_by_keywords(
    client: DiscordWebClient, keywords: list[str], guild_ids: list[str] | None = None
) -> list[ChannelMatch]:
    guilds = await client.get_guilds()

    if guild_ids:
        guilds = [g for g in guilds if g.id in guild_ids]

    matches = []

    for guild in guilds:
        try:
            channels = await client.get_guild_channels(guild.id)

            for channel in channels:
                if _matches_keywords(channel.name, keywords):
                    matched_keywords = [
                        k for k in keywords if k.lower() in channel.name.lower()
                    ]
                    match_reason = f"Keywords: {', '.join(matched_keywords)}"

                    matches.append(
                        ChannelMatch(
                            channel=channel, guild=guild, match_reason=match_reason
                        )
                    )
        except Exception:
            continue

    return matches


async def discover_channels_by_pattern(
    client: DiscordWebClient, pattern: str, guild_ids: list[str] | None = None
) -> list[ChannelMatch]:
    guilds = await client.get_guilds()

    if guild_ids:
        guilds = [g for g in guilds if g.id in guild_ids]

    matches = []

    for guild in guilds:
        try:
            channels = await client.get_guild_channels(guild.id)

            for channel in channels:
                if _matches_pattern(channel.name, pattern):
                    matches.append(
                        ChannelMatch(
                            channel=channel,
                            guild=guild,
                            match_reason=f"Pattern: {pattern}",
                        )
                    )
        except Exception:
            continue

    return matches


async def get_announcement_channels(client: DiscordWebClient) -> list[ChannelMatch]:
    keywords = [
        "announcement",
        "announcements",
        "news",
        "updates",
        "general",
        "info",
        "information",
        "notice",
    ]
    return await discover_channels_by_keywords(client, keywords)


async def get_feedback_channels(client: DiscordWebClient) -> list[ChannelMatch]:
    keywords = [
        "feedback",
        "suggestions",
        "bug",
        "bugs",
        "feature",
        "requests",
        "support",
        "help",
        "discuss",
        "discussion",
    ]
    return await discover_channels_by_keywords(client, keywords)
