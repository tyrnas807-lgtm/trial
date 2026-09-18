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
        "and I will fetch ALL posts for that account."
    )

# 4. Helper Function: Fetch ALL Posts across Pages via RapidAPI
def fetch_all_instagram_posts(username):
    base_url = "https://instagram-public-bulk-scraper.p.rapidapi.com/v1/user_info_web"
    headers = {
        "x-rapidapi-key": RAPIDAPI_KEY,
        "x-rapidapi-host": "instagram-public-bulk-scraper.p.rapidapi.com"
    }

    all_items = []
    end_cursor = None
    has_next_page = True
    page_count = 0

    while has_next_page:
        params = {"username": username.strip().lower()}
        if end_cursor:
            params["max_id"] = end_cursor  # Pass pagination token if available

        try:
            response = requests.get(base_url, headers=headers, params=params, timeout=20)
            
            if response.status_code == 404:
                return None, "Profile not found or API route invalid."
            elif response.status_code != 200:
                return None, f"API Error: {response.status_code} - {response.text}"

            api_data = response.json()
            page_items = []
            page_info = {}

            # Extract timeline data across different standard schema formats
            if isinstance(api_data, dict):
                data_obj = api_data.get("data", api_data)
                if isinstance(data_obj, dict):
                    user_obj = data_obj.get("user", data_obj)
                    timeline = (
                        user_obj.get("edge_owner_to_timeline_media") or 
                        user_obj.get("posts") or 
                        user_obj.get("timeline") or 
                        {}
                    )
                    
                    if isinstance(timeline, dict):
                        page_items = timeline.get("edges", timeline.get("items", []))
                        page_info = timeline.get("page_info", {})
                    elif isinstance(timeline, list):
                        page_items = timeline

            if not page_items:
                break

            all_items.extend(page_items)
            page_count += 1
            print(f"Fetched page {page_count} with {len(page_items)} posts. Total: {len(all_items)}", flush=True)

            # Check pagination cursor for next page
            has_next_page = page_info.get("has_next_page", False)
            end_cursor = page_info.get("end_cursor")

            if not end_cursor:
                has_next_page = False

        except Exception as e:
            print(f"Error fetching page {page_count + 1}: {str(e)}", flush=True)
            break

    return all_items, None

# 5. Message Handler
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    print(f"--> RECEIVED MESSAGE: {update.message.text}", flush=True)

    username = update.message.text.strip().replace("@", "")
    status_msg = await update.message.reply_text(f"Fetching all posts for @{username}...")

    if not RAPIDAPI_KEY:
        await status_msg.edit_text("Error: RAPIDAPI_KEY environment variable is missing on Render.")
        return

    # Fetch all items across pagination
    all_items, error = fetch_all_instagram_posts(username)

    if error:
        await status_msg.edit_text(f"Failed to fetch posts. {error}")
        return

    if not all_items:
        await status_msg.edit_text("No posts found or account has no public media.")
        return

    total_count = len(all_items)
    await status_msg.edit_text(f"Found {total_count} posts. Downloading and uploading to Telegram...")

    try:
        media_group = []
        uploaded_count = 0

        async with httpx.AsyncClient() as client:
            for item in all_items:
                node = item.get("node", item) if isinstance(item, dict) else {}
                
                is_video = node.get("is_video", False)
                media_url = node.get("video_url") or node.get("display_url") or node.get("image_url")

                if not media_url:
                    continue

                try:
                    resp = await client.get(media_url, timeout=10)
                    if resp.status_code == 200:
                        if is_video:
                            media_group.append(InputMediaVideo(media=resp.content))
                        else:
                            media_group.append(InputMediaPhoto(media=resp.content))
                except Exception as dl_err:
                    print(f"Failed to download media item: {dl_err}", flush=True)
                    continue

                # Telegram media groups allow up to 10 items per batch
                if len(media_group) == 10:
                    await update.message.reply_media_group(media=media_group)
                    uploaded_count += len(media_group)
                    media_group = []
                    # Keep status updated for large accounts
                    await status_msg.edit_text(f"Uploaded {uploaded_count}/{total_count} media items...")

            # Upload remaining media items if any
            if media_group:
                await update.message.reply_media_group(media=media_group)
                uploaded_count += len(media_group)

        await status_msg.edit_text(f"Successfully finished uploading {uploaded_count} posts for @{username}!")

    except Exception as e:
        logging.error(f"Error processing API response: {str(e)}", exc_info=True)
        await status_msg.edit_text(f"An error occurred while uploading media: {str(e)}")

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
