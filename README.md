# Instagram color-sorter Telegram bot

`/sort <username> [count] [hue|brightness]` downloads recent photos from a public
Instagram profile and sends them back sorted by average color (a mosaic plus
albums in sorted order, each captioned with its hex color).

## Deploy on Render (nothing runs on your computer)

1. Message [@BotFather](https://t.me/BotFather), create a bot, and copy the token.
2. Create a free GitHub account if you don't have one, make a **new repository**, and
   upload these files via the web UI ("Add file" -> "Upload files"):
   `bot.py`, `colors.py`, `requirements.txt`, `render.yaml`, `README.md`.
   (Do not put your bot token in any file.)
3. On [render.com](https://render.com), sign in with GitHub, then
   **New -> Blueprint**, pick your repository, and apply. Render reads `render.yaml`.
4. When asked for `BOT_TOKEN`, paste the token from step 1. Deploy.
5. When the deploy shows "Live", open your bot in Telegram and send `/start`.

How it works: on Render the bot uses a Telegram **webhook** (Render sets
`RENDER_EXTERNAL_URL` automatically). The free web service sleeps after about 15
minutes without traffic; the next message wakes it, so the first reply after a quiet
period can take up to a minute. Free-tier terms change, so check Render's pricing page.

## Notes

- **Instagram blocks anonymous scraping often, especially from cloud servers.** If you
  see rate-limit/login errors, you would need a throwaway-account session
  (`instaloader --login YOUR_USER`, which does require running Python once somewhere),
  uploaded and referenced via `IG_USER` / `IG_SESSION_FILE`. Without it, expect failures.
  Scraping goes against Instagram's Terms of Use and accounts used for it can get
  restricted. Don't use your main account.
- Only public profiles work. Use it for your own or permitted content and respect
  creators' copyright.
- Sorting: `hue` orders colorful photos around the color wheel (red->violet) and puts
  near-gray ones last (dark->light); `brightness` sorts dark->light.
- Videos are skipped; carousel posts contribute each photo slide.
- Running locally (optional): `pip install -r requirements.txt`, set `BOT_TOKEN`, run
  `python bot.py`. Without a public URL it falls back to polling.
