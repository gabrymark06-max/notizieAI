# notizieAI

Bot Telegram che ogni ora controlla le notizie sull'intelligenza artificiale e
manda solo quelle nuove, nella lingua originale. Se non c'è niente di nuovo,
non scrive. 🔥 = lancio grosso (nuovi modelli GPT, Claude, Gemini, Llama…).

Fonti: OpenAI, Anthropic, Google, Google DeepMind, Meta AI, Hugging Face,
TechCrunch AI, The Verge AI.

- Gira gratis su GitHub Actions (`.github/workflows/notizie.yml`), ogni ora.
- Segreti del repository: `TELEGRAM_TOKEN` (da @BotFather) e `TELEGRAM_CHAT_ID`.
- `visti.json`: le notizie già mandate (si cancellano dopo 45 giorni).
- Per aggiungere una fonte: lista `FONTI` in `notizie.py`.
- Per farlo partire subito: scheda **Actions** → "Notizie AI su Telegram" → **Run workflow**.
