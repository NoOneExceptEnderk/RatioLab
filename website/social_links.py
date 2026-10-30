"""Build-time social links shared by the homepage and documentation footer."""
from __future__ import annotations

import html
import json
from pathlib import Path
from urllib.parse import unquote, urlsplit

ROOT = Path(__file__).resolve().parent
DEFAULT_CHANNELS = ("Discord", "GitHub")


def validate_social_url(value: str) -> str:
    """Accept only explicit HTTPS destinations; never invent or repair a URL."""
    if not isinstance(value, str):
        raise ValueError("A social channel URL must be a string")
    value = value.strip()
    if not value:
        return ""
    decoded = unquote(value)
    if any(character.isspace() or ord(character) < 32 for character in decoded) or "\\" in decoded:
        raise ValueError("Social URLs cannot contain whitespace, control characters or backslashes")
    try:
        parts = urlsplit(value)
        port = parts.port
    except ValueError as error:
        raise ValueError("Invalid social channel URL") from error
    if parts.scheme.lower() != "https" or not parts.hostname or not value.lower().startswith("https://"):
        raise ValueError("Social channel URLs must use an explicit https:// address")
    if parts.username is not None or parts.password is not None:
        raise ValueError("Social channel URLs cannot contain credentials")
    return value


def load_social_channels(path: Path = ROOT / "social.json") -> list[dict[str, str]]:
    if not path.exists():
        return [{"label": label, "url": ""} for label in DEFAULT_CHANNELS]
    config = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(config, dict) or not isinstance(config.get("channels"), list):
        raise ValueError("social.json must contain a channels array")
    channels = []
    for channel in config["channels"]:
        if not isinstance(channel, dict) or not isinstance(channel.get("label"), str) or not channel["label"].strip():
            raise ValueError("Every social channel needs a nonempty label")
        channels.append({"label": channel["label"].strip(), "url": validate_social_url(channel.get("url", ""))})
    return channels


def render_social_links(channels: list[dict[str, str]] | None = None) -> str:
    if channels is None:
        channels = load_social_channels()
    items = []
    for channel in channels:
        label = html.escape(channel["label"], quote=True)
        url = validate_social_url(channel.get("url", ""))
        if url:
            items.append(f'<li><a href="{html.escape(url, quote=True)}">{label} ↗</a></li>')
        else:
            items.append(f'<li><span>{label}</span><small>Not linked yet</small></li>')
    return "\n".join(items)


def render_discord_ctas(channels: list[dict[str, str]] | None = None) -> dict[str, str]:
    """Use the configured Discord destination for navigation and community links."""
    if channels is None:
        channels = load_social_channels()
    url = next((validate_social_url(channel.get("url", "")) for channel in channels
                if channel["label"].strip().casefold() == "discord" and channel.get("url")), "")
    if not url:
        return {"discord_nav": "", "discord_action": '<span class="community-unavailable">Discord is not linked.</span>'}
    destination = html.escape(url, quote=True)
    return {"discord_nav": f'<a href="{destination}">Discord</a>',
            "discord_action": f'<a class="community-action" href="{destination}">Join Discord <span aria-hidden="true">↗</span></a>'}
