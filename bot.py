import os
import threading
from flask import Flask
from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes

# --- 1. Dummy Web Server for Render Health Checks ---
app = Flask(__name__)

@app.route("/")
def health_check():
    return "Bot is alive!", 200

def run_flask():
    # Render automatically assigns a PORT environment variable
    port = int(os.environ.get("PORT", 8080))
    app.run(host="0.0.0.0", port=port)

# --- 2. Telegram Bot Logic ---
BOT_TOKEN = os.environ.get("8761403491:AAFvipWrn0J2uo6kQG36SgMQF5x0zIF78GU")

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text("Send me a public Instagram username!")

# (Include your instaloader and handle_message code here)

def main():
    # Run Flask in a background thread
    threading.Thread(target=run_flask, daemon=True).start()

    # Start Telegram Bot
    application = Application.builder().token(BOT_TOKEN).build()
    application.add_handler(CommandHandler("start", start))
    
    print("Bot starting polling...")
    application.run_polling()

if __name__ == "__main__":
    main()
