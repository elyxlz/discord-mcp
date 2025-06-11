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
    await state.page.wait_for_timeout(3000)

    # FIRST: Capture the original channels before Browse Channels
    logger.debug("Capturing original channels before Browse Channels")
    original_channels_data = await state.page.evaluate(f"""
        () => {{
            const channels = [];
            const seenIds = new Set();
            const guildId = '{guild_id}';
            
            const links = document.querySelectorAll('a[href*="/channels/"]');
            links.forEach(link => {{
                const match = link.href.match(/\\/channels\\/([0-9]+)\\/([0-9]+)/);
                if (match && match[1] === guildId) {{
                    const channelId = match[2];
                    if (!seenIds.has(channelId)) {{
                        seenIds.add(channelId);
                        let channelName = link.textContent?.trim() || '';
                        channelName = channelName.replace(/^[^a-zA-Z0-9#-_]+/, '').trim();
                        channelName = channelName.replace(/\\s+/g, ' ').trim();
                        if (!channelName) channelName = `channel-${{channelId}}`;
                        
                        channels.push({{
                            id: channelId,
                            name: channelName,
                            href: link.href,
                            source: 'original'
                        }});
                    }}
                }}
            }});
            
            return channels;
        }}
    """)
    logger.debug(f"Found {len(original_channels_data)} original channels")

    # Try to click "Browse Channels" button to see all channels
    try:
        # First, look for the Browse Channels button using various approaches
        browse_clicked = False

        # Method 1: Look for text content containing "Browse Channels"
        all_buttons = await state.page.query_selector_all(
            'button, div[role="button"], span[role="button"]'
        )
        for button in all_buttons:
            try:
                text_content = await button.text_content()
                if text_content and "Browse Channels" in text_content:
                    if await button.is_visible():
                        await button.click()
                        await state.page.wait_for_timeout(3000)
                        browse_clicked = True
                        logger.debug(
                            "Successfully clicked Browse Channels button by text content"
                        )
                        break
            except Exception:
                continue

        # Method 2: Look for elements with specific classes or attributes
        if not browse_clicked:
            browse_selectors = [
                '[class*="browse"][class*="channel"]',
                '[class*="Browse"][class*="Channel"]',
                'button[aria-label*="Browse"]',
                'div[aria-label*="Browse"]',
                '[data-testid*="browse"]',
                '[class*="channelBrowser"]',
                'button:has-text("Browse")',
                '*:has-text("Browse Channels")',
            ]

            for selector in browse_selectors:
                try:
                    elements = await state.page.query_selector_all(selector)
                    for element in elements:
                        if await element.is_visible():
                            await element.click()
                            await state.page.wait_for_timeout(3000)
                            browse_clicked = True
                            logger.debug(
                                f"Successfully clicked Browse Channels with selector: {selector}"
                            )
                            break
                    if browse_clicked:
                        break
                except Exception:
                    continue

        if not browse_clicked:
            logger.debug(
                "Browse Channels button not found, proceeding with standard method"
            )
    except Exception as e:
        logger.debug(f"Could not click Browse Channels: {e}")

    # If browse channels was clicked, scroll through the full modal to load all channels
    if browse_clicked:
        try:
            await state.page.wait_for_timeout(2000)

            # Scroll through the browse channels modal to load all channels
            await state.page.evaluate("""
                () => {
                    // Find the browse channels modal/container
                    const modalSelectors = [
                        '[role="dialog"]',
                        '[class*="modal"]',
                        '[class*="Modal"]',
                        '[class*="browser"]',
                        '[class*="Browser"]',
                        '[class*="scroller"]'
                    ];
                    
                    let modalContainer = null;
                    for (let selector of modalSelectors) {
                        const element = document.querySelector(selector);
                        if (element && element.scrollHeight > element.clientHeight) {
                            modalContainer = element;
                            break;
                        }
                    }
                    
                    // If no scrollable modal found, try to find any scrollable container with channels
                    if (!modalContainer) {
                        const scrollableElements = document.querySelectorAll('[class*="scroller"], [class*="scroll"]');
                        for (let element of scrollableElements) {
                            if (element.scrollHeight > element.clientHeight && 
                                element.querySelector('[href*="/channels/"]')) {
                                modalContainer = element;
                                break;
                            }
                        }
                    }
                    
                    if (modalContainer) {
                        return new Promise(resolve => {
                            let scrollPosition = 0;
                            const scrollStep = 300;
                            const maxScrollAttempts = 50;
                            let scrollAttempts = 0;
                            
                            const scrollInterval = setInterval(() => {
                                const previousScrollTop = modalContainer.scrollTop;
                                modalContainer.scrollBy(0, scrollStep);
                                scrollPosition += scrollStep;
                                scrollAttempts++;
                                
                                // Stop if we've reached the bottom or max attempts
                                if (modalContainer.scrollTop === previousScrollTop || 
                                    scrollAttempts >= maxScrollAttempts ||
                                    modalContainer.scrollTop + modalContainer.clientHeight >= modalContainer.scrollHeight - 50) {
                                    clearInterval(scrollInterval);
                                    
                                    // Scroll back to top to ensure we capture all channels
                                    modalContainer.scrollTop = 0;
                                    setTimeout(() => {
                                        // Scroll down one more time to make sure everything is loaded
                                        modalContainer.scrollTop = modalContainer.scrollHeight;
                                        setTimeout(() => {
                                            modalContainer.scrollTop = 0;
                                            resolve();
                                        }, 1000);
                                    }, 1000);
                                }
                            }, 300);
                        });
                    }
                }
            """)

            await state.page.wait_for_timeout(3000)
            logger.debug("Completed scrolling through browse channels modal")

            # After clicking Browse Channels, wait longer and try different approaches
            await state.page.wait_for_timeout(5000)

            # EXTREME SCROLLING: Scroll every scrollable element to load all channels
            scroll_result = await state.page.evaluate("""
                () => {
                    return new Promise(resolve => {
                        const scrollableElements = Array.from(document.querySelectorAll('*')).filter(el => 
                            el.scrollHeight > el.clientHeight + 5
                        );
                        
                        let completed = 0;
                        let totalScrolled = 0;
                        
                        if (scrollableElements.length === 0) {
                            resolve("No scrollable elements found");
                            return;
                        }
                        
                        scrollableElements.forEach((element, index) => {
                            setTimeout(() => {
                                const startScroll = element.scrollTop;
                                element.scrollTop = element.scrollHeight;
                                const endScroll = element.scrollTop;
                                totalScrolled += (endScroll - startScroll);
                                
                                completed++;
                                if (completed === scrollableElements.length) {
                                    setTimeout(() => {
                                        resolve(`Extreme scrolled ${scrollableElements.length} elements, total ${totalScrolled}px`);
                                    }, 2000);
                                }
                            }, index * 50);
                        });
                    });
                }
            """)

            logger.debug(f"Extreme scroll result: {scroll_result}")

            await state.page.wait_for_timeout(3000)

        except Exception as e:
            logger.debug(f"Could not scroll through browse modal: {e}")

    # Wait for channels to load and try to expand all channel categories
    await state.page.wait_for_timeout(2000)

    # Try to expand all collapsed channel categories
    try:
        # Look for category collapse/expand buttons
        category_buttons = await state.page.query_selector_all(
            '[class*="category"] button, [class*="Category"] button, [role="button"][class*="category"]'
        )
        for button in category_buttons:
            try:
                if await button.is_visible():
                    # Check if this looks like a collapsed category (has expand icon)
                    button_text = await button.text_content() or ""
                    aria_expanded = await button.get_attribute("aria-expanded")
                    if aria_expanded == "false" or "expand" in button_text.lower():
                        await button.click()
                        await state.page.wait_for_timeout(500)
            except Exception:
                continue

        # Scroll through the channel list to load all channels
        await state.page.evaluate("""
            () => {
                // Find the main channel list container
                const channelList = document.querySelector('[class*="channels"], [class*="sidebar"], [class*="scroller"]');
                if (channelList) {
                    // Scroll to top first
                    channelList.scrollTop = 0;
                    
                    // Gradually scroll down to load all channels
                    return new Promise(resolve => {
                        let scrolls = 0;
                        const maxScrolls = 20;
                        const scrollInterval = setInterval(() => {
                            channelList.scrollBy(0, 200);
                            scrolls++;
                            
                            if (scrolls >= maxScrolls || 
                                channelList.scrollTop + channelList.clientHeight >= channelList.scrollHeight - 10) {
                                clearInterval(scrollInterval);
                                // Scroll back to top
                                channelList.scrollTop = 0;
                                resolve();
                            }
                        }, 200);
                    });
                }
            }
        """)
        await state.page.wait_for_timeout(1000)
    except Exception as e:
        logger.debug(f"Could not expand categories or scroll: {e}")

    # Wait for additional channels to load
    await state.page.wait_for_timeout(2000)

    logger.debug("Extracting Browse Channels data using JavaScript")
    browse_channels_data = await state.page.evaluate(f"""
        () => {{
            const channels = [];
            const guildId = '{guild_id}';
            const seenIds = new Set();

            // Extract channels from the Browse Channels view
            const allChannelLinks = document.querySelectorAll('a[href*="/channels/"]');
            
            allChannelLinks.forEach(link => {{
                const match = link.href.match(/\\/channels\\/([0-9]+)\\/([0-9]+)/);
                if (match && match[1] === guildId) {{
                    const channelId = match[2];
                    if (!seenIds.has(channelId)) {{
                        seenIds.add(channelId);
                        
                        let channelName = link.textContent?.trim() || '';
                        channelName = channelName.replace(/^[^a-zA-Z0-9#-_]+/, '').trim();
                        channelName = channelName.replace(/\\s+/g, ' ').trim();
                        if (!channelName) channelName = `channel-${{channelId}}`;
                        
                        channels.push({{
                            id: channelId,
                            name: channelName,
                            href: link.href,
                            source: 'browse'
                        }});
                    }}
                }}
            }});

            return channels;
        }}
    """)

    # COMBINE original channels and browse channels, removing duplicates
    logger.debug(
        f"Found {len(original_channels_data)} original + {len(browse_channels_data)} browse channels"
    )

    all_channels_dict = {}

    # Add original channels first (these are the main ones)
    for channel_data in original_channels_data:
        all_channels_dict[channel_data["id"]] = channel_data

    # Add browse channels, but don't overwrite original ones
    for channel_data in browse_channels_data:
        if channel_data["id"] not in all_channels_dict:
            all_channels_dict[channel_data["id"]] = channel_data

    # Convert to list maintaining some order (original first, then browse)
    combined_channels_data = []

    # Add original channels in order
    for channel_data in original_channels_data:
        combined_channels_data.append(channel_data)

    # Add new browse channels that weren't in original
    for channel_data in browse_channels_data:
        if channel_data["id"] not in [ch["id"] for ch in original_channels_data]:
            combined_channels_data.append(channel_data)

    logger.debug(f"Combined total: {len(combined_channels_data)} unique channels")
    channels = [
        DiscordChannel(
            id=channel_data["id"],
            name=channel_data["name"],
            type=0,
            guild_id=guild_id,
        )
        for channel_data in combined_channels_data
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
