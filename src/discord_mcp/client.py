import asyncio
import re
import pathlib as pl
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


@dc.dataclass(frozen=True)
class ClientState:
    email: str
    password: str
    headless: bool
    playwright: Playwright | None
    browser: Browser | None
    page: Page | None
    logged_in: bool
    cookies_file: pl.Path


def create_client_state(
    email: str, password: str, headless: bool = True
) -> ClientState:
    return ClientState(
        email=email,
        password=password,
        headless=headless,
        playwright=None,
        browser=None,
        page=None,
        logged_in=False,
        cookies_file=pl.Path.home() / ".discord_mcp_cookies.json",
    )


async def _ensure_browser(state: ClientState) -> ClientState:
    if state.playwright:
        return state

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=state.headless)

    ctx_kwargs = {}
    if state.cookies_file.exists():
        ctx_kwargs["storage_state"] = str(state.cookies_file)
        print(f"▶️  Loading persisted Discord storage from {state.cookies_file}")

    context = await browser.new_context(**ctx_kwargs)
    page = await context.new_page()

    return dc.replace(
        state,
        playwright=playwright,
        browser=browser,
        page=page,
    )


async def _save_storage_state(state: ClientState) -> None:
    if state.page is None:
        return

    await state.page.context.storage_state(path=str(state.cookies_file))
    print(f"💾  Discord storage state saved to {state.cookies_file}")


async def _check_logged_in(state: ClientState) -> bool:
    if not state.page:
        return False
    try:
        await state.page.goto(
            "https://discord.com/channels/@me", wait_until="domcontentloaded"
        )
        await asyncio.sleep(3)
        current_url = state.page.url

        if "/login" in current_url or "/register" in current_url:
            return False

        if "/channels/@me" not in current_url:
            return False

        try:
            user_area = await state.page.query_selector('[data-list-id="guildsnav"]')
            if not user_area:
                return False

            user_settings = await state.page.query_selector(
                '[aria-label*="User Settings"]'
            )
            if user_settings:
                return True

            dm_elements = await state.page.query_selector(
                '[data-list-id="guildsnav"] [role="treeitem"]'
            )
            return dm_elements is not None

        except Exception:
            return False

    except Exception:
        return False


async def _login(state: ClientState) -> ClientState:
    if state.logged_in:
        return state

    state = await _ensure_browser(state)
    if not state.page:
        raise RuntimeError("Browser page not initialized")

    print("Checking if already logged in with cookies...")
    if await _check_logged_in(state):
        print("Already logged in! Using existing session.")
        return dc.replace(state, logged_in=True)
    else:
        print("Not logged in, proceeding with fresh login...")

    await state.page.goto("https://discord.com/login")
    await asyncio.sleep(2)

    await state.page.fill('input[name="email"]', state.email)
    await state.page.fill('input[name="password"]', state.password)
    await state.page.click('button[type="submit"]')

    try:
        await state.page.wait_for_function(
            "() => !window.location.href.includes('/login')", timeout=60000
        )

        await asyncio.sleep(3)

        current_url = state.page.url

        email_check_count = await state.page.locator('text="Check your email"').count()
        if "/verify" in current_url or email_check_count > 0:
            print(
                "Verification required - please check email and complete verification"
            )
            await state.page.wait_for_function(
                "() => window.location.href.includes('/channels/')", timeout=120000
            )

        if await _check_logged_in(state):
            was_logged_in = state.logged_in
            state = dc.replace(state, logged_in=True)
            await asyncio.sleep(5)

            if state.page:
                await state.page.goto("https://discord.com/channels/@me")
            await asyncio.sleep(3)

            if not was_logged_in:
                await _save_storage_state(state)
            return state
        else:
            raise RuntimeError("Login appeared to succeed but verification failed")

    except Exception as e:
        raise RuntimeError(f"Failed to login to Discord: {e}")


async def clear_cookies(state: ClientState) -> ClientState:
    if state.page:
        await state.page.evaluate("localStorage.clear()")
    if state.cookies_file.exists():
        state.cookies_file.unlink()
    return dc.replace(state, logged_in=False)


async def close_client(state: ClientState) -> None:
    if state.browser:
        await state.browser.close()
    if state.playwright:
        await state.playwright.stop()


def reset_client_state(state: ClientState) -> ClientState:
    return dc.replace(state, playwright=None, browser=None, page=None, logged_in=False)


async def get_guilds(state: ClientState) -> tuple[ClientState, list[DiscordGuild]]:
    state = await _login(state)
    if not state.page:
        raise RuntimeError("Browser page not initialized")

    await state.page.goto(
        "https://discord.com/channels/@me", wait_until="domcontentloaded"
    )
    await asyncio.sleep(3)

    try:
        await state.page.wait_for_selector(
            '[data-list-id="guildsnav"] [role="treeitem"]', timeout=10000
        )
    except Exception as e:
        await asyncio.sleep(5)
        try:
            await state.page.wait_for_selector(
                '[data-list-id="guildsnav"] [role="treeitem"]', timeout=10000
            )
        except Exception:
            raise RuntimeError(f"Could not find guild navigation elements: {e}")

    guild_elements = await state.page.query_selector_all(
        '[data-list-id="guildsnav"] [role="treeitem"]'
    )
    guilds = []

    for element in guild_elements:
        try:
            text_content = await element.text_content()
            if not text_content or "Direct Messages" in text_content:
                continue

            await element.click()
            await asyncio.sleep(1)

            current_url = state.page.url
            guild_match = re.search(r"/channels/([0-9]+)", current_url)

            if guild_match and guild_match.group(1) != "@me":
                guild_id = guild_match.group(1)

                guild_name = text_content.strip()
                guild_name = re.sub(r"^\d+\s+mentions?,\s*", "", guild_name)

                guilds.append(DiscordGuild(id=guild_id, name=guild_name, icon=None))

        except Exception:
            continue

    await state.page.goto(
        "https://discord.com/channels/@me", wait_until="domcontentloaded"
    )
    await asyncio.sleep(2)
    await state.page.wait_for_selector(
        '[data-list-id="guildsnav"] [role="treeitem"]', timeout=10000
    )

    return state, guilds


async def get_guild_channels(
    state: ClientState, guild_id: str
) -> tuple[ClientState, list[DiscordChannel]]:
    state = await _login(state)
    if not state.page:
        raise RuntimeError("Browser page not initialized")

    # Navigate directly to guild
    await state.page.goto(
        f"https://discord.com/channels/{guild_id}", wait_until="domcontentloaded"
    )
    await asyncio.sleep(2)

    # Verify we're in the correct guild
    current_url = state.page.url
    if f"/channels/{guild_id}" not in current_url:
        raise RuntimeError(f"Could not navigate to guild {guild_id}")

    # Extract channels from page
    channels_data = await state.page.evaluate(f"""
        () => {{
            const channels = [];
            const guildId = '{guild_id}';

            // Extract current channel if we're in one
            const currentUrlMatch = window.location.href.match(/\\/channels\\/${{guildId}}\\/([0-9]+)/);
            if (currentUrlMatch) {{
                const currentChannelId = currentUrlMatch[1];
                const titleMatch = document.title.match(/#([^|]+)/);
                const channelName = titleMatch ? titleMatch[1].trim() : 'unknown-channel';

                channels.push({{
                    id: currentChannelId,
                    name: channelName,
                    href: window.location.href
                }});
            }}

            // Find all channel links
            const seenIds = new Set();
            const allElements = document.querySelectorAll('a[href*="/channels/"]');

            for (let element of allElements) {{
                const href = element.href;
                if (href) {{
                    const match = href.match(/\\/channels\\/([0-9]+)\\/([0-9]+)/);
                    if (match && match[1] === guildId) {{
                        const channelId = match[2];

                        if (!seenIds.has(channelId)) {{
                            seenIds.add(channelId);
                            let channelName = element.textContent?.trim() || '';

                            channelName = channelName.replace(/^[^a-zA-Z0-9#-_]+/, '').trim();
                            channelName = channelName.replace(/\\s+/g, ' ').trim();

                            if (channelName && channelName.length > 0 && !channelName.includes('undefined')) {{
                                channels.push({{
                                    id: channelId,
                                    name: channelName,
                                    href: href
                                }});
                            }}
                        }}
                    }}
                }}
            }}

            return channels;
        }}
    """)

    channels = [
        DiscordChannel(
            id=channel_data["id"],
            name=channel_data["name"],
            type=0,
            guild_id=guild_id,
        )
        for channel_data in channels_data
    ]

    return state, channels


async def get_channel_messages(
    state: ClientState,
    channel_id: str,
    limit: int = 100,
    before: str | None = None,
    after: str | None = None,
) -> tuple[ClientState, list[DiscordMessage]]:
    state = await _login(state)
    if not state.page:
        raise RuntimeError("Browser page not initialized")

    guild_id = await _find_guild_for_channel(state, channel_id)
    if not guild_id:
        raise RuntimeError(f"Could not find guild for channel {channel_id}")

    await state.page.goto(
        f"https://discord.com/channels/{guild_id}/{channel_id}",
        wait_until="domcontentloaded",
    )
    await state.page.wait_for_selector('[data-list-id="chat-messages"]', timeout=10000)

    messages = []
    collected = 0

    while collected < limit:
        message_elements = await state.page.query_selector_all(
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
                    await author_element.text_content() if author_element else "Unknown"
                )
                author_name = author_name_raw.strip() if author_name_raw else "Unknown"

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
            await state.page.keyboard.press("PageUp")
            await asyncio.sleep(1)
        else:
            break

    return state, messages[:limit]


async def _find_guild_for_channel(state: ClientState, channel_id: str) -> str | None:
    state, guilds = await get_guilds(state)
    for guild in guilds:
        state, channels = await get_guild_channels(state, guild.id)
        if any(c.id == channel_id for c in channels):
            return guild.id
    return None


async def send_message(
    state: ClientState, channel_id: str, content: str
) -> tuple[ClientState, str]:
    state = await _login(state)
    if not state.page:
        raise RuntimeError("Browser page not initialized")

    guild_id = await _find_guild_for_channel(state, channel_id)
    if not guild_id:
        raise RuntimeError(f"Could not find guild for channel {channel_id}")

    await state.page.goto(
        f"https://discord.com/channels/{guild_id}/{channel_id}",
        wait_until="domcontentloaded",
    )
    await state.page.wait_for_selector('[data-slate-editor="true"]', timeout=10000)

    message_input = await state.page.query_selector('[data-slate-editor="true"]')
    if not message_input:
        raise RuntimeError("Could not find message input")

    await message_input.fill(content)
    await state.page.keyboard.press("Enter")

    await asyncio.sleep(1)

    return state, f"sent-{int(datetime.now().timestamp())}"
