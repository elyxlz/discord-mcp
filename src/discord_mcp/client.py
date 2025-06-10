import asyncio
import pathlib as pl
from datetime import datetime, timezone
import dataclasses as dc
from playwright.async_api import async_playwright, Browser, Page, Playwright
from .logger import logger


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
    icon: str | None = None


@dc.dataclass(frozen=True)
class ClientState:
    email: str
    password: str
    headless: bool = True
    playwright: Playwright | None = None
    browser: Browser | None = None
    context: object | None = None  # BrowserContext
    page: Page | None = None
    logged_in: bool = False
    cookies_file: pl.Path = dc.field(
        default_factory=lambda: pl.Path.home() / ".discord_mcp_cookies.json"
    )


def create_client_state(
    email: str, password: str, headless: bool = True
) -> ClientState:
    return ClientState(email=email, password=password, headless=headless)


async def _ensure_browser(state: ClientState) -> ClientState:
    if state.playwright and state.browser and state.context and state.page:
        return state

    playwright = await async_playwright().start()
    browser = await playwright.chromium.launch(headless=state.headless)

    ctx_kwargs = {}
    if state.cookies_file.exists():
        ctx_kwargs["storage_state"] = str(state.cookies_file)
    context = await browser.new_context(**ctx_kwargs)
    page = await context.new_page()

    return dc.replace(
        state, playwright=playwright, browser=browser, context=context, page=page
    )


async def _save_storage_state(state: ClientState) -> None:
    if state.page:
        await state.page.context.storage_state(path=str(state.cookies_file))


async def _check_logged_in(state: ClientState) -> bool:
    if not state.page:
        return False
    try:
        await state.page.goto(
            "https://discord.com/channels/@me", wait_until="domcontentloaded"
        )
        await state.page.wait_for_selector(
            '[data-list-id="guildsnav"] [role="treeitem"]',
            state="visible",
            timeout=15000,
        )

        url = state.page.url
        if (
            any(path in url for path in ["/login", "/register"])
            or "/channels/@me" not in url
        ):
            return False

        return bool(
            await state.page.query_selector(
                '[data-list-id="guildsnav"] [role="treeitem"]'
            )
        )
    except Exception:
        return False


async def _login(state: ClientState) -> ClientState:
    if state.logged_in:
        return state

    state = await _ensure_browser(state)
    if not state.page:
        raise RuntimeError("Browser page not initialized")

    if await _check_logged_in(state):
        return dc.replace(state, logged_in=True)

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

        if (
            "/verify" in state.page.url
            or await state.page.locator('text="Check your email"').count()
        ):
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


async def close_client(state: ClientState) -> None:
    # Close resources in reverse order: page -> context -> browser -> playwright
    resources = [
        (state.page, "close"),
        (state.context, "close"),
        (state.browser, "close"),
        (state.playwright, "stop"),
    ]

    for resource, action in resources:
        try:
            if resource:
                await getattr(resource, action)()
        except Exception:
            pass

    # Force garbage collection to help cleanup
    import gc

    gc.collect()


async def get_guilds(state: ClientState) -> tuple[ClientState, list[DiscordGuild]]:
    state = await _login(state)
    if not state.page:
        raise RuntimeError("Browser page not initialized")

    logger.debug("Starting guild detection process")
    await state.page.goto(
        "https://discord.com/channels/@me", wait_until="domcontentloaded"
    )
    logger.debug(f"Navigated to Discord, current URL: {state.page.url}")

    # Wait for Discord to fully load guilds with text content
    try:
        await state.page.wait_for_selector(
            '[data-list-id="guildsnav"] [role="treeitem"]',
            state="visible",
            timeout=15000,
        )
        await state.page.wait_for_timeout(5000)

        # Scroll guild navigation to load all guilds
        await state.page.evaluate("""
            () => {
                const guildNav = document.querySelector('[data-list-id="guildsnav"]');
                const container = guildNav?.closest('[class*="guilds"]') || guildNav?.parentElement;
                if (container) {
                    container.scrollTop = 0;
                    return new Promise(resolve => {
                        let scrolls = 0;
                        const interval = setInterval(() => {
                            container.scrollBy(0, 100);
                            if (++scrolls >= 20 || container.scrollTop + container.clientHeight >= container.scrollHeight - 10) {
                                clearInterval(interval);
                                resolve();
                            }
                        }, 100);
                    });
                }
            }
        """)
        await state.page.wait_for_timeout(2000)
    except Exception:
        pass

    # Extract guild information from navigation elements
    guilds_data = await state.page.evaluate("""
        () => {
            const guilds = [];
            const treeItems = document.querySelectorAll('[data-list-id="guildsnav"] [role="treeitem"]');
            
            treeItems.forEach(item => {
                const listItemId = item.getAttribute('data-list-item-id');
                if (listItemId?.startsWith('guildsnav___') && listItemId !== 'guildsnav___home') {
                    const guildId = listItemId.replace('guildsnav___', '');
                    if (/^[0-9]+$/.test(guildId)) {
                        // Extract guild name from tree item text
                        let guildName = null;
                        const textElements = item.querySelectorAll('*');
                        for (let elem of textElements) {
                            const text = elem.textContent?.trim();
                            if (text && text.length > 2 && text.length < 100 && 
                                !text.includes('notification') && !text.includes('unread') &&
                                !text.match(/^\\d+$/)) {
                                guildName = text;
                                break;
                            }
                        }
                        
                        if (!guildName) {
                            const fullText = item.textContent?.trim();
                            if (fullText) {
                                guildName = fullText.replace(/^\\d+\\s+mentions?,\\s*/, '').replace(/\\s+/g, ' ').trim();
                            }
                        }
                        
                        // Clean up mention prefixes
                        if (guildName) {
                            guildName = guildName.replace(/^\\d+\\s+mentions?,\\s*/, '').trim();
                        }
                        
                        if (guildName && !guilds.some(g => g.id === guildId)) {
                            guilds.push({ id: guildId, name: guildName });
                        }
                    }
                }
            });
            
            return guilds;
        }
    """)

    # Convert JavaScript results to DiscordGuild objects
    guilds = [
        DiscordGuild(id=guild_data["id"], name=guild_data["name"], icon=None)
        for guild_data in guilds_data
    ]

    return state, guilds


async def get_guild_channels(
    state: ClientState, guild_id: str
) -> tuple[ClientState, list[DiscordChannel]]:
    state = await _login(state)
    if not state.page:
        raise RuntimeError("Browser page not initialized")

    await state.page.goto(
        f"https://discord.com/channels/{guild_id}", wait_until="domcontentloaded"
    )
    await state.page.wait_for_selector(
        f'a[href*="/channels/{guild_id}/"]', timeout=15000
    )

    current_url = state.page.url
    if f"/channels/{guild_id}" not in current_url:
        raise RuntimeError(f"Could not navigate to guild {guild_id}")
    logger.debug("Extracting channel data using JavaScript")
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

    logger.debug(f"JavaScript extraction returned {len(channels_data)} channels")
    channels = [
        DiscordChannel(
            id=channel_data["id"],
            name=channel_data["name"],
            type=0,
            guild_id=guild_id,
        )
        for channel_data in channels_data
    ]
    logger.debug(f"Created {len(channels)} DiscordChannel objects")
    logger.debug(f"get_guild_channels completed successfully for guild {guild_id}")

    return state, channels


async def _extract_message_data(
    element, channel_id: str, collected: int
) -> DiscordMessage | None:
    try:
        message_id = (
            await element.get_attribute("id") or f"message-{collected}"
        ).replace("chat-messages-", "")

        content = ""
        for selector in [
            '[class*="messageContent"]',
            '[class*="markup"]',
            ".messageContent",
        ]:
            content_elem = await element.query_selector(selector)
            if content_elem and (text := await content_elem.text_content()):
                content = text.strip()
                break

        author_name = "Unknown"
        for selector in ['[class*="username"]', '[class*="authorName"]', ".username"]:
            author_elem = await element.query_selector(selector)
            if author_elem and (name := await author_elem.text_content()):
                author_name = name.strip()
                break

        timestamp_elem = await element.query_selector("time")
        timestamp_str = (
            await timestamp_elem.get_attribute("datetime") if timestamp_elem else None
        )
        timestamp = (
            datetime.fromisoformat(timestamp_str.replace("Z", "+00:00"))
            if timestamp_str
            else datetime.now(timezone.utc)
        )

        attachments = [
            href
            for att in await element.query_selector_all('a[href*="cdn.discordapp.com"]')
            if (href := await att.get_attribute("href"))
        ]

        if not content and not attachments:
            return None

        return DiscordMessage(
            id=message_id,
            content=content,
            author_name=author_name,
            author_id="unknown",
            channel_id=channel_id,
            timestamp=timestamp,
            attachments=attachments,
        )
    except Exception:
        return None


async def get_channel_messages(
    state: ClientState,
    server_id: str,
    channel_id: str,
    limit: int = 100,
    before: str | None = None,
    after: str | None = None,
) -> tuple[ClientState, list[DiscordMessage]]:
    state = await _login(state)
    if not state.page:
        raise RuntimeError("Browser page not initialized")

    await state.page.goto(
        f"https://discord.com/channels/{server_id}/{channel_id}",
        wait_until="domcontentloaded",
    )
    await state.page.wait_for_selector('[data-list-id="chat-messages"]', timeout=15000)

    # Scroll to bottom for newest messages
    await state.page.evaluate("""
        const chat = document.querySelector('[data-list-id="chat-messages"]');
        if (chat) chat.scrollTo(0, chat.scrollHeight);
        window.scrollTo(0, document.body.scrollHeight);
    """)
    await state.page.wait_for_timeout(2000)

    messages = []
    seen_ids = set()

    for attempt in range(10):
        elements = await state.page.query_selector_all(
            '[data-list-id="chat-messages"] [id^="chat-messages-"]'
        )
        if not elements:
            await state.page.keyboard.press("PageUp")
            await state.page.wait_for_timeout(1000)
            continue

        for element in reversed(elements):
            if len(messages) >= limit:
                break
            try:
                message = await _extract_message_data(
                    element, channel_id, len(seen_ids)
                )
                if message and message.id not in seen_ids:
                    if before and message.id >= before:
                        continue
                    if after and message.id <= after:
                        continue
                    seen_ids.add(message.id)
                    messages.append(message)
            except Exception:
                continue

        if len(messages) >= limit or not elements:
            break
        await state.page.keyboard.press("PageUp")
        await state.page.wait_for_timeout(1000)

    return state, sorted(messages, key=lambda m: m.timestamp, reverse=True)[:limit]


async def send_message(
    state: ClientState, server_id: str, channel_id: str, content: str
) -> tuple[ClientState, str]:
    state = await _login(state)
    if not state.page:
        raise RuntimeError("Browser page not initialized")

    await state.page.goto(
        f"https://discord.com/channels/{server_id}/{channel_id}",
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
