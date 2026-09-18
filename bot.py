import os
import logging
import threading
import httpx
import requests
from flask import Flask
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

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
RAPIDAPI_KEY = os.environ.get("RAPIDAPI_KEY")

# 3. Command Handler: /start
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send me a public Instagram username (e.g., `nasa`), "
        "and I will fetch the 10 most recent posts for you."
    )

# 4. Helper Function: Fetch Profile Posts via your specific RapidAPI host
def fetch_instagram_posts(username):
    # Match host from your working code snippet
    url = "https://instagram-public-bulk-scraper.p.rapidapi.com/v1/user_info_web"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "instagram-public-bulk-scraper.p.rapidapi.com"
    }
    params = {"username": username.strip().lower()}

    try:
        response = requests.get(url, headers=headers, params=params, timeout=15)
        
        if response.status_code == 404:
            return None, "Profile not found or API route invalid."
        elif response.status_code != 200:
            return None, f"API Error: {response.status_code}"

        data = response.json()
        return data, None
    except Exception as e:
        return None, f"Network error: {str(e)}"

# 5. Message Handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"--> RECEIVED MESSAGE: {update.message.text}", flush=True)

    username = update.message.text.strip().replace("@", "")
    status_msg = await update.message.reply_text(f"Fetching posts for @{username}...")

    if not RAPIDAPI_KEY:
        await status_msg.edit_text("Error: RAPIDAPI_KEY environment variable is missing on Render.")
        return

    # Fetch data from RapidAPI
    api_data, error = fetch_instagram_posts(username)

    if error:
        await status_msg.edit_text(f"Failed to fetch posts. {error}")
        return

    try:
        # Traverse JSON response structure
        data_obj = api_data.get("data", {})
        
        # Check standard timeline media paths
        user_obj = data_obj.get("user", {}) if "user" in data_obj else data_obj
        timeline = user_obj.get("edge_owner_to_timeline_media", {})
        items = timeline.get("edges", [])

        if not items:
            await status_msg.edit_text("No posts found or account is private/non-existent.")
            return

        await status_msg.edit_text("Uploading media to Telegram...")

        media_group = []
        async with httpx.AsyncClient() as client:
            for item in items[:10]:  # Limit to 10 posts
                node = item.get("node", {})
                is_video = node.get("is_video", False)
                media_url = node.get("video_url") if is_video else node.get("display_url")

                if not media_url:
                    continue

                # Download image/video bytes in memory
                resp = await client.get(media_url)
                if resp.status_code == 200:
                    if is_video:
                        media_group.append(InputMediaVideo(media=resp.content))
                    else:
                        media_group.append(InputMediaPhoto(media=resp.content))

                # Telegram accepts up to 10 items per album
                if len(media_group) == 10:
                    await update.message.reply_media_group(media=media_group)
                    media_group = []

            if media_group:
                await update.message.reply_media_group(media=media_group)

        await status_msg.delete()

    except Exception as e:
        logging.error(f"Error processing API response: {e}")
        await status_msg.edit_text("An error occurred while downloading and sending media.")

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
