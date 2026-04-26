from __future__ import annotations

import asyncio
import io
import logging
import os
from dataclasses import dataclass
from typing import Optional

from dotenv import load_dotenv

from app.config import BACKEND_DIR
from app.html_snippets import HtmlSnippet, extract_html_snippets, normalize_html_document

load_dotenv(BACKEND_DIR / ".env")
load_dotenv(BACKEND_DIR / ".env.local")

LOGGER = logging.getLogger("discord_html_renderer")


@dataclass(frozen=True)
class HtmlRendererSettings:
    bot_token: str
    webhook_url: str
    channel_id: Optional[int]
    max_chars: int
    max_snippets_per_message: int
    viewport_width: int
    viewport_height: int
    timeout_ms: int
    allow_remote_assets: bool


def _optional_int(value: Optional[str]) -> Optional[int]:
    if value is None or value == "":
        return None
    return int(value)


def _env_bool(name: str, *, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def load_settings() -> HtmlRendererSettings:
    bot_token = os.getenv("DISCORD_HTML_RENDERER_BOT_TOKEN", "").strip()
    webhook_url = os.getenv("DISCORD_HTML_RENDERER_WEBHOOK_URL", "").strip()

    missing = []
    if not bot_token:
        missing.append("DISCORD_HTML_RENDERER_BOT_TOKEN")
    if not webhook_url:
        missing.append("DISCORD_HTML_RENDERER_WEBHOOK_URL")
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")

    return HtmlRendererSettings(
        bot_token=bot_token,
        webhook_url=webhook_url,
        channel_id=_optional_int(os.getenv("DISCORD_HTML_RENDERER_CHANNEL_ID")),
        max_chars=int(os.getenv("DISCORD_HTML_RENDERER_MAX_CHARS", "12000")),
        max_snippets_per_message=int(os.getenv("DISCORD_HTML_RENDERER_MAX_SNIPPETS", "3")),
        viewport_width=int(os.getenv("DISCORD_HTML_RENDERER_VIEWPORT_WIDTH", "1200")),
        viewport_height=int(os.getenv("DISCORD_HTML_RENDERER_VIEWPORT_HEIGHT", "800")),
        timeout_ms=int(os.getenv("DISCORD_HTML_RENDERER_TIMEOUT_MS", "5000")),
        allow_remote_assets=_env_bool("DISCORD_HTML_RENDERER_ALLOW_REMOTE_ASSETS"),
    )


async def render_html_to_png(html: str, settings: HtmlRendererSettings) -> bytes:
    from playwright.async_api import async_playwright

    async def block_route(route):
        await route.abort()

    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch()
        context = await browser.new_context(
            java_script_enabled=False,
            viewport={"width": settings.viewport_width, "height": settings.viewport_height},
            device_scale_factor=1,
        )

        if not settings.allow_remote_assets:
            await context.route("**/*", block_route)

        page = await context.new_page()
        try:
            await page.set_content(
                normalize_html_document(html),
                wait_until="domcontentloaded",
                timeout=settings.timeout_ms,
            )
            await page.emulate_media(media="screen")
            return await page.screenshot(
                type="png",
                full_page=True,
                timeout=settings.timeout_ms,
            )
        finally:
            await context.close()
            await browser.close()


async def send_rendered_image(
    *,
    webhook_url: str,
    image: bytes,
    filename: str,
    content: str,
) -> None:
    import aiohttp
    import discord

    async with aiohttp.ClientSession() as session:
        webhook = discord.Webhook.from_url(webhook_url, session=session)
        await webhook.send(
            content=content,
            file=discord.File(io.BytesIO(image), filename=filename),
            allowed_mentions=discord.AllowedMentions.none(),
            wait=True,
        )


async def render_and_send_snippet(
    *,
    snippet: HtmlSnippet,
    settings: HtmlRendererSettings,
    message_url: str,
    message_id: int,
    index: int,
) -> None:
    image = await render_html_to_png(snippet.html, settings)
    suffix = f"-{index}" if index > 1 else ""
    content = f"Rendered HTML from {message_url}"
    if snippet.truncated:
        content += f" (truncated to {settings.max_chars} characters)"

    await send_rendered_image(
        webhook_url=settings.webhook_url,
        image=image,
        filename=f"html-render-{message_id}{suffix}.png",
        content=content,
    )


async def run_bot(settings: HtmlRendererSettings) -> None:
    import discord

    intents = discord.Intents.default()
    intents.message_content = True
    intents.messages = True

    client = discord.Client(intents=intents)

    @client.event
    async def on_ready() -> None:
        LOGGER.info("Discord HTML renderer logged in as %s", client.user)

    @client.event
    async def on_message(message: discord.Message) -> None:
        if message.author.bot or message.webhook_id is not None:
            return

        if settings.channel_id is not None and message.channel.id != settings.channel_id:
            return

        snippets = extract_html_snippets(
            message.content,
            max_chars=settings.max_chars,
            max_snippets=settings.max_snippets_per_message,
        )

        for index, snippet in enumerate(snippets, start=1):
            try:
                await render_and_send_snippet(
                    snippet=snippet,
                    settings=settings,
                    message_url=message.jump_url,
                    message_id=message.id,
                    index=index,
                )
            except Exception:
                LOGGER.exception("Failed to render HTML from Discord message %s", message.id)

    await client.start(settings.bot_token)


def main() -> None:
    logging.basicConfig(level=os.getenv("LOG_LEVEL", "INFO"))
    settings = load_settings()
    asyncio.run(run_bot(settings))


if __name__ == "__main__":
    main()
