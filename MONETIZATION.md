# Monetization Guide — humanizer

This is an internal guide for the project owner. It is not public-facing.

---

## Step 1 — Create a Gumroad account

1. Go to [gumroad.com](https://gumroad.com) and sign up with your email.
2. Complete your creator profile (display name, payout details).
3. Connect a bank account or PayPal under **Settings → Payouts** so you can receive payments.

---

## Step 2 — Create the product

1. In the Gumroad dashboard, click **New Product**.
2. Select **Digital product**.
3. Name it: `humanizer — AI-detection bypass for academic writing`
4. Upload the binary:
   - Build it first: `./packaging/build-release.sh 1.2.0`
   - Upload `dist/release/humanize-linux-x86_64` (and `humanize-macos-arm64` if you have a Mac build).
   - Optionally zip both into `humanizer-v1.2.zip` and upload the zip as the single download.
5. Upload `install.sh` as a second file so buyers get the one-command installer too.

---

## Step 3 — Set the price

1. Set the price to **$15 USD**.
2. Enable **"Pay what you want"** with a **$15 minimum** — this lets supportive buyers pay more.
3. Leave "Require login to purchase" off to reduce friction.

---

## Step 4 — Write the product description

Paste the following into the Gumroad description field (adapt as needed):

---

> **Rewrite your academic essays to pass AI detectors — in 30 seconds.**
>
> humanizer is a local desktop app (no cloud, no subscription) that runs on your machine. It rewrites your text in your own voice using a local AI model, then applies a set of edits that stylometric detectors can't fingerprint.
>
> **Quick start (3 steps):**
>
> 1. Install (Linux / macOS):
>    `curl -fsSL <your-gumroad-install-url> | bash`
>
> 2. Open the app:
>    `humanize`
>
> 3. Press **T**, type the path to your essay, press **Ctrl+S**.
>
> Your file is rewritten. The original is unchanged.
>
> **Works with .docx and .md files. No Python. No package manager. Everything runs locally.**

---

## Step 5 — Publish and update the README

1. Click **Publish** in Gumroad.
2. Copy the product URL (looks like `https://yourname.gumroad.com/l/humanizer`).
3. Open `README.md` in this repo and replace the placeholder line:
   ```
   Support the project and get the latest binary: [Gumroad link — coming soon]
   ```
   with:
   ```
   Support the project and get the latest binary: [Gumroad →](https://yourname.gumroad.com/l/humanizer)
   ```
4. Commit and push the README update.

---

## Step 6 — Add a refund policy (optional but recommended)

In Gumroad under **Product → Refund policy**, set a **30-day no-questions-asked refund**. Gumroad supports this natively. Reduces payment disputes and signals confidence in the product.

---

## Step 7 — Growth

- Post the install command in your university Discord, WhatsApp, or Telegram group:
  ```
  curl -fsSL https://yourname.gumroad.com/l/humanizer-install | bash
  ```
- Ask satisfied users to leave a Gumroad review (public reviews increase conversions).
- After 10+ sales, consider a brief demo video (30 seconds: paste AI text → press Ctrl+S → show score drop). Upload to YouTube or TikTok and link it from the Gumroad page.
- At $15 × 100 buyers = $1,500 — enough to cover a year of API credits if you switch to hosted backends.

---

## Notes

- The binary is a one-file self-contained executable. Buyers do not need Python or any package manager.
- Ollama (the local AI runtime) is free and open-source. The install script downloads it automatically.
- The AI model (`gemma3:4b`) is ~2 GB and is pulled automatically on first run. Make sure this is clear in the description so buyers are not surprised.
- Do not store API keys in the binary. The binary reads keys from `~/.config/humanizer/secrets.toml` on the buyer's own machine.
