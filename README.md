# Musically

A party-mode song guessing game. Players share one device,
a song plays from a Spotify playlist, and each player takes turns guessing the
song name.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- A Spotify Premium account
- A Spotify Developer application (create one at https://developer.spotify.com/dashboard)

## Setup (local development)

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

## Docker (local)

Run with Docker Compose (uses `.env`; `config.toml` is baked into the image):

```bash
cp .env.example .env   # edit with your credentials first
docker compose up --build
```

Open http://127.0.0.1:8000.

To build the image without Compose:

```bash
docker build -t musically .
docker run --rm -p 8000:8000 --env-file .env musically
```

## Production deployment

Production assumes:

- The app container listens on port **8000** (plain HTTP inside the host/Docker network).
- **[Caddy](https://caddyserver.com/)** terminates TLS on the public hostname and reverse-proxies to the app.
- Spotify OAuth uses an **https** redirect URI matching your public domain.

### 1. Prepare the server

On the production host:

- Install Docker.
- Install Caddy (package or official install guide).
- Open ports 80 and 443 (and 22 for SSH).

### 2. Configure on your deploy machine

You do not need to clone the repository on the server. Keep a local checkout for deploying; Docker builds on the remote host over SSH and bakes `config.toml` into the image. Edit playlists and scoring in `config.toml` locally before deploying.

Create `.env` from `.env.example` with production values:

```bash
SPOTIFY_CLIENT_ID=...
SPOTIFY_CLIENT_SECRET=...
SPOTIFY_REDIRECT_URI=https://musically.example.com/callback
SECRET_KEY=<long-random-secret>
LOG_LEVEL=INFO
```

Add the same `https://musically.example.com/callback` redirect URI in the Spotify Developer Dashboard.

Configure Caddy on the server to terminate TLS and reverse-proxy to `127.0.0.1:8000`.

### 3. Deploy with Docker over SSH

From your workstation, create a Docker context that targets the server (once):

```bash
docker context create musically-prod --docker "host=ssh://user@your-server"
```

Deploy (sends the build context to the server, builds the image there, and starts the container):

```bash
cd /path/to/musically
docker --context musically-prod compose up -d --build
```

Logs:

```bash
docker --context musically-prod compose logs -f musically
```

### 4. Updates

```bash
docker --context musically-prod compose up -d --build
```

## How to Play

1. The host logs in with their Spotify Premium account.
2. Enter a Spotify playlist URL and configure the number of rounds (or play endlessly).
3. Players register their names.
4. Start the game — a random song plays and each player takes turns typing their guess.
5. After all players guess, the answer is revealed and scores are updated.
6. At the end, the final leaderboard shows the winner.
