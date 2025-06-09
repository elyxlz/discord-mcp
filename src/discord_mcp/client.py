import asyncio
import re
from datetime import datetime, timezone
import dataclasses as dc
from playwright.async_api import async_playwright, Browser, Page, Playwright


@dc.dataclass(frozen=True)
class DiscordMessage:
    id: str
    content: str
    author_name: str
    author_id: str
    channel_id: str
    timestamp: datetime
    attachments: list[str]


@dc.dataclass(frozen=True)
class DiscordChannel:
    id: str
    name: str
    type: int
    guild_id: str | None


@dc.dataclass(frozen=True)
class DiscordGuild:
    id: str
    name: str
    icon: str | None


class DiscordWebClient:
    def __init__(self, email: str, password: str, headless: bool = True):
        self.email = email
        self.password = password
        self.headless = headless
        self.playwright: Playwright | None = None
        self.browser: Browser | None = None
        self.page: Page | None = None
        self._logged_in = False

    async def _ensure_browser(self) -> None:
        if not self.playwright:
            self.playwright = await async_playwright().start()
            self.browser = await self.playwright.chromium.launch(headless=self.headless)
            self.page = await self.browser.new_page()

    async def _login(self) -> None:
        if self._logged_in:
            return

        await self._ensure_browser()
        if not self.page:
            raise RuntimeError("Browser page not initialized")

        await self.page.goto("https://discord.com/login")
        await self.page.fill('input[name="email"]', self.email)
        await self.page.fill('input[name="password"]', self.password)
        await self.page.click('button[type="submit"]')

        try:
            await self.page.wait_for_url(
                "https://discord.com/channels/*", timeout=30000
            )
            self._logged_in = True
        except Exception:
            raise RuntimeError("Failed to login to Discord")

    async def close(self) -> None:
        if self.browser:
            await self.browser.close()
        if self.playwright:
            await self.playwright.stop()

    async def get_guilds(self) -> list[DiscordGuild]:
        await self._login()
        if not self.page:
            raise RuntimeError("Browser page not initialized")

        await self.page.goto("https://discord.com/channels/@me")
        await self.page.wait_for_load_state("networkidle")

        guild_elements = await self.page.query_selector_all(
            '[data-list-id="guildsnav"] [role="treeitem"]'
        )
        guilds = []

        for element in guild_elements:
            try:
                guild_link = await element.query_selector("a")
                if not guild_link:
                    continue

                href = await guild_link.get_attribute("href")
                if not href or "/channels/@me" in href:
                    continue

                guild_id_match = re.search(r"/channels/([0-9]+)", href)
                if not guild_id_match:
                    continue

                guild_id = guild_id_match.group(1)

                guild_name_element = await element.query_selector(
                    "[data-list-item-id] div"
                )
                guild_name_raw = (
                    await guild_name_element.text_content()
                    if guild_name_element
                    else f"Guild {guild_id}"
                )
                guild_name = (
                    guild_name_raw.strip() if guild_name_raw else f"Guild {guild_id}"
                )

                guilds.append(DiscordGuild(id=guild_id, name=guild_name, icon=None))
            except Exception:
                continue

        return guilds

    async def get_guild_channels(self, guild_id: str) -> list[DiscordChannel]:
        await self._login()
        if not self.page:
            raise RuntimeError("Browser page not initialized")

        await self.page.goto(f"https://discord.com/channels/{guild_id}")
        await self.page.wait_for_load_state("networkidle")

        channel_elements = await self.page.query_selector_all(
            '[data-list-id="channels"] [role="treeitem"] a'
        )
        channels = []

        for element in channel_elements:
            try:
                href = await element.get_attribute("href")
                if not href:
                    continue

                channel_match = re.search(f"/channels/{guild_id}/([0-9]+)", href)
                if not channel_match:
                    continue

                channel_id = channel_match.group(1)

                channel_name_element = await element.query_selector('[class*="name"]')
                if not channel_name_element:
                    channel_name_element = await element.query_selector("div")

                channel_name_raw = (
                    await channel_name_element.text_content()
                    if channel_name_element
                    else f"channel-{channel_id}"
                )
                channel_name = (
                    channel_name_raw.strip()
                    if channel_name_raw
                    else f"channel-{channel_id}"
                )

                channels.append(
                    DiscordChannel(
                        id=channel_id, name=channel_name, type=0, guild_id=guild_id
                    )
                )
            except Exception:
                continue

        return channels

    async def get_channel_messages(
        self,
        channel_id: str,
        limit: int = 100,
        before: str | None = None,
        after: str | None = None,
    ) -> list[DiscordMessage]:
        await self._login()
        if not self.page:
            raise RuntimeError("Browser page not initialized")

        guild_id = await self._find_guild_for_channel(channel_id)
        if not guild_id:
            raise RuntimeError(f"Could not find guild for channel {channel_id}")

        await self.page.goto(f"https://discord.com/channels/{guild_id}/{channel_id}")
        await self.page.wait_for_load_state("networkidle")

        messages = []
        collected = 0

        while collected < limit:
            message_elements = await self.page.query_selector_all(
                '[data-list-id="chat-messages"] [id^="chat-messages-"]'
            )

            for element in message_elements[-min(50, limit - collected) :]:
                try:
                    message_id = await element.get_attribute("id")
                    if not message_id:
                        continue

                    message_id = message_id.replace("chat-messages-", "")

                    content_element = await element.query_selector(
                        '[class*="messageContent"]'
                    )
                    content_raw = (
                        await content_element.text_content() if content_element else ""
                    )
                    content = content_raw.strip() if content_raw else ""

                    author_element = await element.query_selector('[class*="username"]')
                    author_name_raw = (
                        await author_element.text_content()
                        if author_element
                        else "Unknown"
                    )
                    author_name = (
                        author_name_raw.strip() if author_name_raw else "Unknown"
                    )

                    timestamp_element = await element.query_selector("time")
                    timestamp_str = (
                        await timestamp_element.get_attribute("datetime")
                        if timestamp_element
                        else None
                    )

                    if timestamp_str:
                        timestamp = datetime.fromisoformat(
                            timestamp_str.replace("Z", "+00:00")
                        )
                    else:
                        timestamp = datetime.now(timezone.utc)

                    attachment_elements = await element.query_selector_all(
                        'a[href*="cdn.discordapp.com"]'
                    )
                    attachments = []
                    for att_element in attachment_elements:
                        href = await att_element.get_attribute("href")
                        if href:
                            attachments.append(href)

                    messages.append(
                        DiscordMessage(
                            id=message_id,
                            content=content,
                            author_name=author_name,
                            author_id="unknown",
                            channel_id=channel_id,
                            timestamp=timestamp,
                            attachments=attachments,
                        )
                    )

                    collected += 1
                    if collected >= limit:
                        break

                except Exception:
                    continue

            if collected < limit and len(message_elements) > 0:
                await self.page.keyboard.press("PageUp")
                await asyncio.sleep(1)
            else:
                break

        return messages[:limit]

    async def _find_guild_for_channel(self, channel_id: str) -> str | None:
        guilds = await self.get_guilds()
        for guild in guilds:
            channels = await self.get_guild_channels(guild.id)
            if any(c.id == channel_id for c in channels):
                return guild.id
        return None

    async def send_message(self, channel_id: str, content: str) -> str:
        await self._login()
        if not self.page:
            raise RuntimeError("Browser page not initialized")

        guild_id = await self._find_guild_for_channel(channel_id)
        if not guild_id:
            raise RuntimeError(f"Could not find guild for channel {channel_id}")

        await self.page.goto(f"https://discord.com/channels/{guild_id}/{channel_id}")
        await self.page.wait_for_load_state("networkidle")

        message_input = await self.page.query_selector('[data-slate-editor="true"]')
        if not message_input:
            raise RuntimeError("Could not find message input")

        await message_input.fill(content)
        await self.page.keyboard.press("Enter")

        await asyncio.sleep(1)

        return f"sent-{int(datetime.now().timestamp())}"
