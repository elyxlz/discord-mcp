import asyncio
import re
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

        current_url = state.page.url

        email_check_count = await state.page.locator('text="Check your email"').count()
        if "/verify" in current_url or email_check_count > 0:
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
    try:
        if state.browser:
            await state.browser.close()
    except Exception:
        pass

    try:
        if state.playwright:
            await state.playwright.stop()
    except Exception:
        pass


async def get_guilds(state: ClientState) -> tuple[ClientState, list[DiscordGuild]]:
    state = await _login(state)
    if not state.page:
        raise RuntimeError("Browser page not initialized")

    await state.page.goto(
        "https://discord.com/channels/@me", wait_until="domcontentloaded"
    )

    # Wait for Discord to fully load guilds with text content
    try:
        await state.page.wait_for_selector(
            '[data-list-id="guildsnav"] [role="treeitem"]',
            state="visible",
            timeout=15000,
        )
        # Give extra time for guild names to load
        await state.page.wait_for_timeout(3000)

        await state.page.wait_for_function(
            """
            () => {
                const elements = document.querySelectorAll('[data-list-id="guildsnav"] [role="treeitem"]');
                return Array.from(elements).some(el => 
                    el.textContent?.trim() || el.getAttribute('aria-label')
                );
            }
        """,
            timeout=10000,
        )
    except Exception:
        pass

    # Use JavaScript to extract guild information directly without clicking each one
    guilds_data = await state.page.evaluate("""
        () => {
            const guilds = [];
            
            // Look for guild elements with data-dnd-name
            const elements = document.querySelectorAll('[data-list-id="guildsnav"] [data-dnd-name]:not([data-dnd-name="Private channels"])');
            
            elements.forEach(element => {
                const text = element.textContent?.trim();
                const ariaLabel = element.getAttribute('aria-label');
                const displayText = text || ariaLabel || '';
                
                // Skip non-guild elements
                if (!displayText || 
                    displayText.toLowerCase().includes('direct messages') ||
                    displayText.toLowerCase().includes('create') ||
                    displayText.toLowerCase().includes('add') ||
                    displayText.toLowerCase().includes('explore') ||
                    displayText.toLowerCase().includes('download') ||
                    displayText.toLowerCase().includes('discover') ||
                    displayText.toLowerCase().includes('browse') ||
                    displayText.toLowerCase().includes('join a server')) {
                    return;
                }
                
                // Try to find a link to extract guild ID
                const link = element.querySelector('a[href*="/channels/"]') || element.closest('a[href*="/channels/"]');
                if (link) {
                    const href = link.getAttribute('href');
                    const match = href.match(/\\/channels\\/([0-9]+)/);
                    if (match && match[1] !== '@me') {
                        const guildId = match[1];
                        let guildName = displayText.replace(/^\\d+\\s+mentions?,\\s*/, '').trim();
                        
                        guilds.push({
                            id: guildId,
                            name: guildName
                        });
                    }
                }
            });
            
            return guilds;
        }
    """)

    guild_elements = []
    if len(guilds_data) == 0:
        # Fallback: try clicking approach for a few elements
        all_elements = await state.page.query_selector_all(
            '[data-list-id="guildsnav"] [data-dnd-name]:not([data-dnd-name="Private channels"])'
        )
        guild_elements = all_elements[:5]  # Only try first 5 elements

    # Convert JavaScript results to DiscordGuild objects
    guilds = [
        DiscordGuild(id=guild_data["id"], name=guild_data["name"], icon=None)
        for guild_data in guilds_data
    ]

    # If JavaScript approach didn't work, fall back to clicking approach (limited)
    if len(guilds) == 0 and len(guild_elements) > 0:
        for element in guild_elements:
            try:
                text_content = await element.text_content()
                aria_label = await element.get_attribute("aria-label")
                display_text = text_content or aria_label or ""

                # Skip non-guild elements
                if not display_text or any(
                    skip_text in display_text.lower()
                    for skip_text in [
                        "direct messages",
                        "create",
                        "add a server",
                        "explore",
                        "download",
                        "discover",
                        "browse",
                        "join a server",
                        "create your server",
                    ]
                ):
                    continue

                await element.click()
                await state.page.wait_for_timeout(500)

                current_url = state.page.url
                guild_match = re.search(r"/channels/([0-9]+)", current_url)

                if guild_match and guild_match.group(1) != "@me":
                    guild_id = guild_match.group(1)
                    guild_name = display_text.strip()
                    guild_name = re.sub(r"^\d+\s+mentions?,\s*", "", guild_name)
                    guilds.append(DiscordGuild(id=guild_id, name=guild_name, icon=None))

            except Exception:
                continue

    await state.page.goto(
        "https://discord.com/channels/@me", wait_until="domcontentloaded"
    )
    await state.page.wait_for_selector(
        '[data-list-id="guildsnav"] [role="treeitem"]', state="visible", timeout=10000
    )

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


async def get_channel_messages(
    state: ClientState,
    server_id: str,
    channel_id: str,
    limit: int = 100,
    before: str | None = None,
    after: str | None = None,
) -> tuple[ClientState, list[DiscordMessage]]:
    logger.debug(
        f"get_channel_messages called for server {server_id}, channel {channel_id}, limit {limit}"
    )
    state = await _login(state)
    if not state.page:
        logger.error("Browser page not initialized after login")
        raise RuntimeError("Browser page not initialized")
    logger.debug("Login completed for get_channel_messages")

    logger.debug("Navigating directly to channel URL")
    await state.page.goto(
        f"https://discord.com/channels/{server_id}/{channel_id}",
        wait_until="domcontentloaded",
    )
    logger.debug("Channel page loaded, waiting for chat messages")
    await state.page.wait_for_selector('[data-list-id="chat-messages"]', timeout=10000)
    logger.debug("Chat messages container found")

    # Debug: Check what elements are actually in the chat container
    all_elements = await state.page.query_selector_all(
        '[data-list-id="chat-messages"] *[id]'
    )
    logger.debug(f"Found {len(all_elements)} elements with IDs in chat container")
    if all_elements:
        sample_ids = []
        for i, elem in enumerate(all_elements[:5]):  # Sample first 5
            elem_id = await elem.get_attribute("id")
            sample_ids.append(elem_id)
        logger.debug(f"Sample IDs: {sample_ids}")

    # Also check for any direct children of the chat container
    chat_children = await state.page.query_selector_all(
        '[data-list-id="chat-messages"] > *'
    )
    logger.debug(f"Found {len(chat_children)} direct children of chat container")

    # And check all elements in the container regardless of ID
    all_chat_elements = await state.page.query_selector_all(
        '[data-list-id="chat-messages"] *'
    )
    logger.debug(f"Found {len(all_chat_elements)} total elements in chat container")

    # Check if there are any elements with message-like class names
    message_like = await state.page.query_selector_all(
        '[data-list-id="chat-messages"] [class*="message"]'
    )
    logger.debug(f"Found {len(message_like)} elements with 'message' in class name")

    messages = []
    collected = 0

    while collected < limit:
        # Try different selectors to find messages
        message_elements = await state.page.query_selector_all(
            '[data-list-id="chat-messages"] [id^="chat-messages-"]'
        )
        if len(message_elements) == 0:
            # Try alternative selectors that work with current Discord
            message_elements = await state.page.query_selector_all(
                '[data-list-id="chat-messages"] li[id]'
            )
            if len(message_elements) == 0:
                # Try even broader selector for message containers
                message_elements = await state.page.query_selector_all(
                    '[data-list-id="chat-messages"] [class*="message"][class*="container"]'
                )
                if len(message_elements) == 0:
                    # Try any element that looks like a message
                    message_elements = await state.page.query_selector_all(
                        '[data-list-id="chat-messages"] [data-list-item-id]'
                    )
            logger.debug(
                f"Alternative selectors found {len(message_elements)} elements"
            )

        logger.debug(f"Found {len(message_elements)} message elements on page")

        for element in message_elements[-min(50, limit - collected) :]:
            try:
                message_id = await element.get_attribute("id")
                if not message_id:
                    # If no ID, try to get data-list-item-id or create a unique ID
                    message_id = await element.get_attribute("data-list-item-id")
                    if not message_id:
                        # Generate a temporary ID based on element position
                        message_id = f"message-{collected}"

                # Clean up the message ID (remove common prefixes)
                if message_id.startswith("chat-messages-"):
                    message_id = message_id.replace("chat-messages-", "")
                elif message_id.startswith("message-"):
                    pass  # Keep as is
                else:
                    # For other formats, use as is
                    pass

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
            await message_elements[0].scroll_into_view_if_needed()
            await state.page.wait_for_timeout(500)
        else:
            break

    logger.debug(
        f"get_channel_messages completed, returning {len(messages[:limit])} messages"
    )
    return state, messages[:limit]


async def send_message(
    state: ClientState, server_id: str, channel_id: str, content: str
) -> tuple[ClientState, str]:
    logger.debug(f"send_message called for server {server_id}, channel {channel_id}")
    state = await _login(state)
    if not state.page:
        logger.error("Browser page not initialized after login")
        raise RuntimeError("Browser page not initialized")
    logger.debug("Login completed for send_message")

    logger.debug("Navigating directly to channel URL")
    await state.page.goto(
        f"https://discord.com/channels/{server_id}/{channel_id}",
        wait_until="domcontentloaded",
    )
    logger.debug("Channel page loaded, waiting for message input")
    await state.page.wait_for_selector('[data-slate-editor="true"]', timeout=10000)
    logger.debug("Message input found")

    message_input = await state.page.query_selector('[data-slate-editor="true"]')
    if not message_input:
        logger.error("Could not find message input element")
        raise RuntimeError("Could not find message input")

    logger.debug(f"Filling message content: {content[:50]}...")
    await message_input.fill(content)
    logger.debug("Pressing Enter to send message")
    await state.page.keyboard.press("Enter")
    logger.debug("Message sent, waiting 1 second")

    await asyncio.sleep(1)

    message_id = f"sent-{int(datetime.now().timestamp())}"
    logger.debug(f"send_message completed with ID: {message_id}")
    return state, message_id
