import os
import shutil
import logging
import threading
import asyncio
from flask import Flask
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import instaloader

# Configure logging
logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

# 1. Flask Web Server for Render Health Checks
app_web = Flask(__name__)

@app_web.route("/")
def health_check():
    return "Bot is alive!", 200

def run_flask():
    port = int(os.environ.get("PORT", 8080))
    app_web.run(host="0.0.0.0", port=port)

# 2. Retrieve Environment Variables
BOT_TOKEN = os.environ.get("BOT_TOKEN")
IG_SESSION_ID = os.environ.get("IG_SESSION_ID")

# 3. Create SINGLE Global Instaloader Instance & Queue Lock
L = instaloader.Instaloader(
    download_pictures=True,
    download_videos=True,
    download_video_thumbnails=False,
    download_geotags=False,
    download_comments=False,
    save_metadata=False
)

# Inject session cookie globally on startup
if IG_SESSION_ID:
    L.context._session.cookies.set("sessionid", IG_SESSION_ID, domain=".instagram.com")
    print("Global Instaloader instance initialized with IG_SESSION_ID.", flush=True)

# Lock to ensure only one download happens at a time
download_lock = asyncio.Lock()

# 4. Command Handler: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send me a public Instagram username (e.g., `nasa`), "
        "and I will fetch the 10 most recent posts for you."
    )

# 5. Message Handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"--> RECEIVED MESSAGE: {update.message.text}", flush=True)

    username = update.message.text.strip().replace("@", "")
    chat_id = update.message.chat_id
    download_folder = f"/tmp/downloads_{chat_id}"

    status_msg = await update.message.reply_text(f"Queueing request for @{username}...")

    # Wait turn if another download is already running
    async with download_lock:
        await status_msg.edit_text(f"Fetching posts for @{username}...")

        try:
            profile = instaloader.Profile.from_username(L.context, username)
            
            if profile.is_private:
                await status_msg.edit_text("Error: This Instagram profile is private.")
                return

            posts = profile.get_posts()
            count = 0

            # Download up to 10 posts
            for post in posts:
                if count >= 10:
                    break
                # Download into target folder
                L.dirname_pattern = download_folder
                L.download_post(post, target=download_folder)
                count += 1

            if count == 0:
                await status_msg.edit_text("No posts found or user has no media.")
                return

            await status_msg.edit_text("Uploading media to Telegram...")

            # Prepare and send media albums
            media_group = []
            
            for root, _, files in os.walk(download_folder):
                for file in sorted(files):
                    file_path = os.path.join(root, file)
                    
                    if file.endswith(".jpg") or file.endswith(".png"):
                        with open(file_path, "rb") as f:
                            media_group.append(InputMediaPhoto(media=f.read()))
                    elif file.endswith(".mp4"):
                        with open(file_path, "rb") as f:
                            media_group.append(InputMediaVideo(media=f.read()))

                    if len(media_group) == 10:
                        await update.message.reply_media_group(media=media_group)
                        media_group = []

            if media_group:
                await update.message.reply_media_group(media=media_group)

            await status_msg.delete()

        except instaloader.exceptions.ProfileNotExistsException:
            await status_msg.edit_text("Error: Profile does not exist.")
        except Exception as e:
            logging.error(f"Error handling request: {e}")
            await status_msg.edit_text("An error occurred while fetching posts. Instagram rate limits may apply.")
        finally:
            if os.path.exists(download_folder):
                shutil.rmtree(download_folder)

# 6. Entry Point
def main():
    threading.Thread(target=run_flask, daemon=True).start()

    if not BOT_TOKEN:
        raise ValueError("CRITICAL: BOT_TOKEN environment variable is not set!")

    application = Application.builder().token(BOT_TOKEN).build()

    application.add_handler(CommandHandler("start", start))
    application.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot starting polling...", flush=True)
    application.run_polling()

if __name__ == "__main__":
    main()
