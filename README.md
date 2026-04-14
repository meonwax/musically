# Musically

A party-mode song guessing game. Players share one device,
a song plays from a Spotify playlist, and each player takes turns guessing the
song name.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- A Spotify Premium account
- A Spotify Developer application (create one at https://developer.spotify.com/dashboard)

## Setup

1. Install dependencies:

```bash
uv sync
```

2. Copy `.env.example` to `.env` and fill in your Spotify credentials:

```bash
cp .env.example .env
```

3. In your Spotify Developer Dashboard, add the redirect URI
   (`http://127.0.0.1:8000/callback` by default) to your app's settings.

4. Run the server:

```bash
uv run uvicorn app.main:app --reload
```

5. Open http://127.0.0.1:8000 in your browser.

## How to Play

1. The host logs in with their Spotify Premium account.
2. Enter a Spotify playlist URL and configure the number of rounds (or play endlessly).
3. Players register their names.
4. Start the game — a random song plays and each player takes turns typing their guess.
5. After all players guess, the answer is revealed and scores are updated.
6. At the end, the final leaderboard shows the winner.
