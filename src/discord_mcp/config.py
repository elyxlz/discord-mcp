import os
import typing as tp
from pathlib import Path
from dotenv import load_dotenv


class DiscordConfig(tp.NamedTuple):
    email: str
    password: str
    headless: bool
    default_guild_ids: list[str]
    max_messages_per_channel: int
    default_hours_back: int


def load_config() -> DiscordConfig:
    env_file = Path(".env")
    if env_file.exists():
        load_dotenv(env_file)

    email = os.getenv("DISCORD_EMAIL")
    if not email:
        raise ValueError("DISCORD_EMAIL environment variable is required")

    password = os.getenv("DISCORD_PASSWORD")
    if not password:
        raise ValueError("DISCORD_PASSWORD environment variable is required")

    headless = os.getenv("DISCORD_HEADLESS", "true").lower() == "true"

    guild_ids_str = os.getenv("DISCORD_GUILD_IDS", "")
    guild_ids = [gid.strip() for gid in guild_ids_str.split(",") if gid.strip()]

    max_messages = int(os.getenv("MAX_MESSAGES_PER_CHANNEL", "200"))
    hours_back = int(os.getenv("DEFAULT_HOURS_BACK", "24"))

    return DiscordConfig(
        email=email,
        password=password,
        headless=headless,
        default_guild_ids=guild_ids,
        max_messages_per_channel=max_messages,
        default_hours_back=hours_back,
    )
