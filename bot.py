import os
import shutil
import logging
from telegram import Update, InputMediaPhoto, InputMediaVideo
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
import instaloader

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO
)

BOT_TOKEN = "8761403491:AAGwVae-eDb6_ljtfZLzNDRZDZo-a82ti-M"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Send me a public Instagram username (e.g., `nasa`), "
        "and I will fetch the 10 most recent posts."
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    username = update.message.text.strip().replace("@", "")
    chat_id = update.message.chat_id
    
    # Save files to /tmp to avoid filling up main account storage quota
    download_folder = f"/tmp/downloads_{chat_id}"

    status_msg = await update.message.reply_text(f"Fetching posts for @{username}...")

    try:
        L = instaloader.Instaloader(
            download_pictures=True,
            download_videos=True,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            dirname_pattern=download_folder
        )

        profile = instaloader.Profile.from_username(L.context, username)
        
        if profile.is_private:
            await status_msg.edit_text("Error: This Instagram profile is private.")
            return

        posts = profile.get_posts()
        count = 0

        for post in posts:
            if count >= 10:
                break
            L.download_post(post, target=download_folder)
            count += 1

        if count == 0:
            await status_msg.edit_text("No posts found or user has no media.")
            return

        await status_msg.edit_text("Uploading media to Telegram...")

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
        await status_msg.edit_text("Failed to fetch media. Instagram rate limit or proxy restrictions may apply.")
    finally:
        # Crucial for PythonAnywhere: clean up downloaded media
        if os.path.exists(download_folder):
            shutil.rmtree(download_folder)

def main():
    app = Application.builder().token(BOT_TOKEN).build()
    app.add_handler(CommandHandler("start", start))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot running...")
    app.run_polling()

if __name__ == "__main__":
    main()
