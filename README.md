# Musically

A party-mode song guessing game. Players share one device, a song plays from
a Spotify playlist, and each player takes turns guessing the song title,
artist and release year.

## Prerequisites

- Python 3.12+
- [uv](https://docs.astral.sh/uv/) package manager
- A Spotify Premium account (Spotify requires Premium for both the Web
  Playback SDK and for Development Mode apps)
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
   In Development Mode, a host who isn't the app owner must be added under
   "User Management".

4. Run the server:

```bash
uv run uvicorn app.main:app --reload
```

5. Open http://127.0.0.1:8000 in your browser.

Spotify tokens are kept in memory only, so after a server restart the host
has to log in again.

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

## Deploy on Render (free)

`render.yaml` is a [Render Blueprint](https://render.com/docs/blueprint-spec)
for a free web service that builds the `Dockerfile` and redeploys on every
push to `main`. Render provides HTTPS on an `onrender.com` subdomain.

1. In the [Render Dashboard](https://dashboard.render.com), choose
   **New > Blueprint** and connect this GitHub repository.
2. Enter `SPOTIFY_CLIENT_ID`, `SPOTIFY_CLIENT_SECRET` and
   `SPOTIFY_REDIRECT_URI` (`https://<service>.onrender.com/callback`).
   `SECRET_KEY` is generated. If Render assigns a different subdomain,
   correct the redirect URI under the service's **Environment** tab.
3. Add the same redirect URI in the Spotify Developer Dashboard.

Free instances have limits that matter for this app:

- The service spins down after 15 minutes without traffic. The next visit
  wakes it up, which takes a minute or two, so open the site before the
  party starts. A running game keeps it awake.
- Game state and Spotify tokens live in memory, so every deploy, spin-down
  or restart ends the current game and the host has to log in again. Avoid
  pushing to `main` during a game.

To try the image with the free plan's resources (0.1 CPU, 512 MB) locally:

```bash
docker build -t musically .
docker run --rm --cpus 0.1 --memory 512m -p 8000:8000 --env-file .env musically
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
2. Pick one of the predefined playlists from `config.toml` or enter a Spotify
   playlist URL, and configure the number of rounds (0 plays endlessly until
   the host ends the game). For Development Mode apps, Spotify only returns
   the contents of playlists the host owns or collaborates on, so copy other
   playlists into your own library first.
3. Players register their names.
4. Choose where the music plays: in this browser, or on any Spotify Connect
   device such as the Spotify app on a phone, a laptop or a speaker. Open
   Spotify on the device first, then refresh the list.
5. Start the game. A random song plays and each player takes a turn guessing
   the song title, and optionally the artist and release year. The first
   player rotates each round. Previous guesses stay hidden until everyone has
   had their turn.
6. After all players guess or skip, the answer is revealed and scores are
   updated.
7. At the end, the final leaderboard shows the winner.

Phone browsers usually block the in-browser player because the songs don't
start from a tap. On phones, pick the Spotify app as the device instead. Songs
fade out and in only in the browser player. A Spotify Connect device pauses and
resumes right away.

## Scoring

Points are configured in the `[points]` table of `config.toml`. The defaults:

- Correct song title: 1 point (`song`)
- Correct artist: 1 point (`artist`)
- Correct release year: doubles the points of that guess (`year_multiplier`;
  a correct year on its own is worth nothing)

Guesses are fuzzy-matched, so small typos, word order, a leading "The" and
version suffixes such as "- Remastered 2011" don't matter. The year must be
exact.

## Release years

Spotify often reports the year of a remaster or compilation instead of the
original release. After a playlist loads, Musically looks up the original
year of every track on [MusicBrainz](https://musicbrainz.org) in the
background. MusicBrainz allows one request per second, so large playlists take
a while (about 5 minutes for 300 tracks). The lobby shows when the lookup is
done. You don't have to wait: once a game starts, the lookup jumps to the
current and upcoming rounds, so each song's year is checked within a second
or two of its round starting.

## Development

Run the test suite with:

```bash
uv run pytest
```

See `docs/architecture.md` for the design and `AGENTS.md` for conventions.

## License

Copyright © 2026 Meonwax

Musically is free software: you can redistribute it and/or modify it under the terms of the GNU General Public License as published by the Free Software Foundation, either version 3 of the License, or (at your option) any later version. See [LICENSE](LICENSE) for the full text.
