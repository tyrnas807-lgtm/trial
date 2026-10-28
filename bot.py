"""Telegram bot: /sort <instagram_username> [count] [hue|brightness]

Downloads the latest photos from a PUBLIC Instagram profile and sends them back
sorted by average color.

Runs in webhook mode on Render (RENDER_EXTERNAL_URL is set automatically there),
and falls back to polling when run locally without a public URL.
"""
import asyncio
import hashlib
import logging
import os
import re
import shutil
import tempfile
from pathlib import Path

import instaloader
from telegram import InputMediaPhoto, Update
from telegram.ext import Application, CommandHandler, ContextTypes

from colors import build_mosaic, hex_of, sort_images

logging.basicConfig(level=logging.INFO)
log = logging.getLogger("igsortbot")

BOT_TOKEN = os.environ["BOT_TOKEN"]
IG_USER = os.environ.get("IG_USER")  # optional: a throwaway IG account for login
IG_SESSION_FILE = os.environ.get("IG_SESSION_FILE")  # created with `instaloader --login`
MAX_IMAGES = 60
USERNAME_RE = re.compile(r"^[A-Za-z0-9._]{1,30}$")


def download_images(username: str, limit: int, dest: Path) -> list[Path]:
    """Blocking download of up to `limit` photos (carousel slides included, videos skipped)."""
    L = instaloader.Instaloader(
        download_videos=False,
        download_video_thumbnails=False,
        save_metadata=False,
        quiet=True,
    )
    if IG_USER and IG_SESSION_FILE:
        L.load_session_from_file(IG_USER, IG_SESSION_FILE)

    profile = instaloader.Profile.from_username(L.context, username)
    if profile.is_private and not profile.followed_by_viewer:
        raise PermissionError("That account is private.")

    paths: list[Path] = []
    for post in profile.get_posts():
        if len(paths) >= limit:
            break
        if post.typename == "GraphSidecar":
            urls = [n.display_url for n in post.get_sidecar_nodes() if not n.is_video]
        elif post.is_video:
            continue
        else:
            urls = [post.url]
        for url in urls:
            if len(paths) >= limit:
                break
            base = dest / f"{post.shortcode}_{len(paths)}"
            if L.download_pic(str(base), url, post.date_utc):
                paths.append(base.with_suffix(".jpg"))
    return paths


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send /sort <instagram_username> [count] [hue|brightness]\n"
        "Example: /sort natgeo 30 hue\n\n"
        "I fetch recent photos from a public profile and sort them by average color."
    )


async def sort_cmd(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    if not args:
        await update.message.reply_text("Usage: /sort <username> [count] [hue|brightness]")
        return
    username = args[0].lstrip("@")
    if not USERNAME_RE.match(username):
        await update.message.reply_text("That doesn't look like a valid Instagram username.")
        return
    limit, mode = 20, "hue"
    for a in args[1:]:
        if a.isdigit():
            limit = max(1, min(int(a), MAX_IMAGES))
        elif a.lower() in ("hue", "brightness"):
            mode = a.lower()

    status = await update.message.reply_text(f"Fetching up to {limit} photos from @{username}…")
    tmp = Path(tempfile.mkdtemp(prefix="igsort_"))
    try:
        try:
            paths = await asyncio.to_thread(download_images, username, limit, tmp)
        except PermissionError as e:
            await status.edit_text(str(e))
            return
        except instaloader.exceptions.ProfileNotExistsException:
            await status.edit_text("Profile not found.")
            return
        except instaloader.exceptions.InstaloaderException as e:
            log.exception("instagram error")
            await status.edit_text(
                f"Instagram refused the request ({e.__class__.__name__}). "
                "It likely rate-limited or blocked anonymous access; try later or configure a login session."
            )
            return

        if not paths:
            await status.edit_text("No photos found.")
            return

        await status.edit_text(f"Got {len(paths)} photos, sorting by {mode}…")
        items = await asyncio.to_thread(sort_images, paths, mode)

        mosaic = await asyncio.to_thread(build_mosaic, items, tmp / "mosaic.jpg")
        with open(mosaic, "rb") as f:
            await update.message.reply_photo(f, caption=f"@{username} sorted by {mode} (left→right, top→bottom)")

        # Also send the originals as albums in sorted order (Telegram max 10 per album).
        n = 0
        for i in range(0, len(items), 10):
            chunk = items[i:i + 10]
            media = []
            for path, rgb in chunk:
                n += 1
                media.append(InputMediaPhoto(open(path, "rb"), caption=f"#{n} {hex_of(rgb)}"))
            await update.message.reply_media_group(media)
            await asyncio.sleep(1)
        await status.delete()
    finally:
        shutil.rmtree(tmp, ignore_errors=True)


def main():
    # concurrent_updates: a long /sort job must not block other incoming updates.
    app = Application.builder().token(BOT_TOKEN).concurrent_updates(True).build()
    app.add_handler(CommandHandler(["start", "help"], start))
    app.add_handler(CommandHandler("sort", sort_cmd))

    base_url = os.environ.get("WEBHOOK_URL") or os.environ.get("RENDER_EXTERNAL_URL")
    if base_url:
        # Telegram only allows A-Za-z0-9_- in the secret token, so derive one from the bot token.
        secret = hashlib.sha256(BOT_TOKEN.encode()).hexdigest()
        port = int(os.environ.get("PORT", "10000"))
        log.info("Starting webhook on port %s at %s/webhook", port, base_url)
        app.run_webhook(
            listen="0.0.0.0",
            port=port,
            url_path="webhook",
            webhook_url=f"{base_url.rstrip('/')}/webhook",
            secret_token=secret,
            drop_pending_updates=True,
        )
    else:
        log.info("No WEBHOOK_URL/RENDER_EXTERNAL_URL set; using polling (local mode)")
        app.run_polling()


if __name__ == "__main__":
    main()
