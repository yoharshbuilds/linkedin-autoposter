# LinkedIn Auto-Poster (Rahul Mathur style)

Twice a day, this finds fresh Indian startup / VC / AI / fintech news, writes a LinkedIn post in
the style of **Rahul Mathur (VP @ DeVC)**, generates a matching stat-card image, and (optionally)
publishes it to your LinkedIn.

- **Reading** (his posts as style reference + daily news): [agent-reach](https://github.com/Panniantong/agent-reach) via `twitter-cli`, plus RSS.
- **Writing**: Claude (`anthropic/claude-sonnet-4.6`) via OpenRouter. Hard rule: **no em dashes**.
- **Image**: `openai/gpt-5-image-mini` via OpenRouter, rendered as a navy/gold stat-card.
- **Posting**: Playwright automating the LinkedIn web UI (no public API for individuals).
- **Schedule**: macOS `launchd` (recommended) or GitHub Actions.

## How it works
`src/main.py`: research -> pick a fresh item (deduped) -> generate post JSON -> stat-card -> publish.

## Setup
```bash
cd ~/linkedin-autoposter
uv venv --python 3.13 .venv && source .venv/bin/activate
uv pip install -r requirements.txt
python -m playwright install chromium          # only needed for live posting
cp .env.example .env                            # then add your keys
```
The style reference (`reference/rahul_posts.json`) is already extracted. To refresh it:
`twitter user-posts Rahul_J_Mathur -n 60 --json -o reference/rahul_raw.json` then rebuild the clean file.

## Keys (.env)
- `OPENROUTER_API_KEY` — required. One key for both text and image.
- `LI_AT` — your LinkedIn `li_at` cookie. Only needed to post live (`dry_run: false`).

## Run
```bash
./run.sh                 # one cycle (dry-run by default: preview saved to out/)
```
Dry-run writes `out/preview-*.txt` (post) and `out/card-*.png` (image). Review, then go live.

## Go live
1. In `config.yaml` set `dry_run: false`.
2. Put your `li_at` cookie in `.env`.
3. `python -m playwright install chromium`.

## Schedule (twice daily)
**macOS launchd (recommended, uses your residential IP + local twitter session):**
```bash
# edit absolute paths in the plist first
cp deploy/com.getbelong.linkedin-autopost.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.getbelong.linkedin-autopost.plist
```
Fires at ~09:32 and ~18:33 local time. The Mac must be awake.

**GitHub Actions** (`.github/workflows/autopost.yml`): always-on, but runs from datacenter IPs.
Live LinkedIn posting and twitter reading from those IPs are much more likely to be flagged. Add
repo secrets `OPENROUTER_API_KEY` and `LI_AT` if you use it.

## Config (`config.yaml`)
Models, topics, keyword filter, RSS feeds, twitter sources, hashtags, recency window, `dry_run`,
and the image art-direction string.

## Important notes
- **Rotate your OpenRouter key** if it was ever shared in plain text.
- LinkedIn has no individual posting API, so live mode automates the web UI. This is against
  LinkedIn's ToS and carries account risk. Keep `dry_run: true` until you have reviewed output, and
  prefer running from your Mac (stable IP) over a datacenter.
- The generator only uses facts present in the source item. It never invents numbers.
