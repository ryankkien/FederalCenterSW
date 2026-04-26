# Discord HTML Renderer

The Discord HTML renderer is a worker-style backend process that watches a Discord
channel for HTML snippets, renders each snippet to a PNG with Chromium, and posts the
image back to Discord through a channel webhook.

Discord webhooks are send-only. The renderer also needs a Discord bot token so it can
read messages from the channel.

## Discord Setup

1. Create or choose the Discord channel where users will post HTML snippets.
2. Create a Discord webhook in that channel. Use the webhook URL as
   `DISCORD_HTML_RENDERER_WEBHOOK_URL`.
3. Create a Discord application and bot in the Discord Developer Portal.
4. Enable the bot's Message Content Intent.
5. Invite the bot to the server with permission to view the channel and read message
   history.
6. Use the bot token as `DISCORD_HTML_RENDERER_BOT_TOKEN`.
7. Optionally set `DISCORD_HTML_RENDERER_CHANNEL_ID` so the bot only reacts in one
   channel.

## Local Run

Install backend dependencies and Playwright's Chromium browser:

```sh
.venv/bin/python -m pip install -r backend/requirements-dev.txt
.venv/bin/python -m playwright install chromium
```

Configure the environment in `backend/.env.local` or `backend/.env`:

```sh
DISCORD_HTML_RENDERER_BOT_TOKEN=<discord-bot-token>
DISCORD_HTML_RENDERER_WEBHOOK_URL=<discord-channel-webhook-url>
DISCORD_HTML_RENDERER_CHANNEL_ID=<optional-channel-id>
```

Run the renderer:

```sh
bun run discord:html-renderer
```

Post HTML in the configured Discord channel:

````text
```html
<div style="padding: 24px; font: 20px sans-serif;">
  Hello from HTML
</div>
```
````

The bot will render the snippet and post a PNG back to the channel.

## Rendering Behavior

- Fenced `html` or `htm` code blocks are rendered.
- Unlabeled fenced code blocks and raw messages are rendered only when they look like
  HTML.
- Up to `DISCORD_HTML_RENDERER_MAX_SNIPPETS` snippets are rendered per message. The
  default is `3`.
- Each snippet is capped at `DISCORD_HTML_RENDERER_MAX_CHARS`. The default is `12000`.
- JavaScript is disabled during rendering.
- Remote network assets are blocked by default. Set
  `DISCORD_HTML_RENDERER_ALLOW_REMOTE_ASSETS=true` only when the channel is trusted and
  external images/CSS are required.

## Environment Variables

| Variable | Required | Default | Purpose |
| --- | --- | --- | --- |
| `DISCORD_HTML_RENDERER_BOT_TOKEN` | Yes | None | Discord bot token used to read channel messages. |
| `DISCORD_HTML_RENDERER_WEBHOOK_URL` | Yes | None | Discord webhook URL used to post rendered PNGs. |
| `DISCORD_HTML_RENDERER_CHANNEL_ID` | No | None | Restricts rendering to one Discord channel. |
| `DISCORD_HTML_RENDERER_MAX_CHARS` | No | `12000` | Maximum HTML characters rendered per snippet. |
| `DISCORD_HTML_RENDERER_MAX_SNIPPETS` | No | `3` | Maximum snippets rendered from one Discord message. |
| `DISCORD_HTML_RENDERER_VIEWPORT_WIDTH` | No | `1200` | Chromium viewport width in pixels. |
| `DISCORD_HTML_RENDERER_VIEWPORT_HEIGHT` | No | `800` | Chromium viewport height in pixels. |
| `DISCORD_HTML_RENDERER_TIMEOUT_MS` | No | `5000` | Playwright render and screenshot timeout. |
| `DISCORD_HTML_RENDERER_ALLOW_REMOTE_ASSETS` | No | `false` | Allows external image/CSS/font requests during rendering. |

## Deployment Notes

The renderer is a long-running process, not a FastAPI route or a GitHub Actions workflow.
Run it in a worker host, container app, VM, or another process supervisor that can keep a
Discord Gateway connection open.

Do not commit bot tokens or webhook URLs. Store them in local ignored env files, GitHub
environment secrets, Azure app settings, or Key Vault.
