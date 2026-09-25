# Musically - Architecture and Design Plan

## Overview

A party-mode web game where players share one device, a song plays from a Spotify playlist, and each player takes turns guessing the song name via free text input with fuzzy matching. The host authenticates with Spotify and configures the game (playlist, number of rounds or endless mode).

## Tech Stack

- **Backend**: Python 3.12+ with **FastAPI** (async, modern, great Jinja2/template support)
- **Frontend**: HTML + **HTMX** for server-driven interactivity, minimal vanilla JS only for Spotify playback
- **Templating**: Jinja2 (via `fastapi` + `jinja2`)
- **Spotify Playback**: [Spotify Web Playback SDK](https://developer.spotify.com/documentation/web-playback-sdk) (JavaScript, requires Premium)
- **Spotify Data**: [Spotify Web API](https://developer.spotify.com/documentation/web-api) (fetch playlist tracks, metadata)
- **Fuzzy Matching**: `thefuzz` library (Levenshtein distance-based string matching)
- **State Management**: In-memory Python dataclasses (no database -- state lives only for the server process lifetime)
- **Package Manager**: [uv](https://docs.astral.sh/uv/)
- **No CSS framework**: A trimmed copy of [The Monospace Web](https://github.com/owickstrom/the-monospace-web) stylesheet (`static/css/monospace.css`, MIT), the self-hosted JetBrains Mono font (OFL) and the [uchū simple palette](https://uchu.style/simple.html). See "Styling and Themes"

## Spotify Integration

### Authentication Flow

```mermaid
sequenceDiagram
    participant Host as Host Browser
    participant Server as FastAPI Server
    participant Spotify as Spotify Accounts

    Host->>Server: GET / (home page)
    Server-->>Host: "Login with Spotify" button
    Host->>Spotify: Redirect to /authorize
    Spotify-->>Host: Redirect back with ?code=...
    Host->>Server: GET /callback?code=...
    Server->>Spotify: POST /api/token (exchange code)
    Spotify-->>Server: access_token + refresh_token
    Server-->>Host: Redirect to /lobby
```

- **OAuth 2.0 Authorization Code** flow (not PKCE, since we have a server to keep the client secret safe)
- Scopes needed: `streaming`, `user-read-playback-state`, `user-modify-playback-state`, `user-read-email`, `user-read-private`, `playlist-read-private`, `playlist-read-collaborative`
- Backend stores a single set of tokens in memory (one host per server process); a signed session cookie marks the host's browser as logged in
- A request counts as logged in only if the session cookie says so **and** tokens exist, since tokens are lost on server restart while the cookie survives
- Backend handles automatic token refresh when access token expires
- Playlist contents come from `GET /v1/playlists/{id}/items` (the `/tracks` endpoint was removed in the February 2026 Web API changes). Spotify only returns items for playlists the host owns or collaborates on. Local files and podcast episodes are skipped.
- The game page names the loaded playlist (`GameState.playlist`) and links to it on Spotify. Predefined playlists use their name from `config.toml`, matched by playlist ID. Other playlists show as "Custom playlist", without an extra API call for the name

### Playback Architecture

- The lobby lets the host pick the playback device (`GameState.playback_device`, kept across resets):
  - **This browser** (default): the **Spotify Web Playback SDK** runs in the page and creates a virtual device in the user's Spotify account
  - **A Spotify Connect device** from `GET /v1/me/player/devices` (Spotify app on a phone, laptop, speaker). Restricted devices and the game's own web player are left out. Phone browsers usually block the SDK's audio, so this is the way to play on phones
- Either way, the **backend** tells Spotify which track to play on the device via the Web API (`PUT /v1/me/player/play`)
- The track name/artist is **never sent to the frontend** during a round -- not even the track URI reaches the browser
- A small `static/js/spotify-player.js` file drives the status line, play/pause, elapsed time for both modes and the fades of the browser player (see "HTMX + Spotify JS Bridge")

## Game Flow

```mermaid
stateDiagram-v2
    [*] --> Home
    Home --> SpotifyAuth: Host clicks Login
    SpotifyAuth --> Lobby: Auth success
    Lobby --> Lobby: Players register names
    Lobby --> Lobby: Host sets playlist + rounds
    Lobby --> RoundStart: Host starts game
    RoundStart --> SongPlaying: Pick random track, play it
    SongPlaying --> PlayerTurn: Show current player input
    PlayerTurn --> PlayerTurn: Next player's turn
    PlayerTurn --> RoundResult: All players guessed
    RoundResult --> RoundStart: Next round (if rounds remain)
    RoundResult --> FinalLeaderboard: Game over (all rounds done or host ends)
    FinalLeaderboard --> Lobby: Play again
    FinalLeaderboard --> [*]
```

- A game only ends through "End Game" or its last round, never by navigation. While it runs (`GameState.in_progress`), `GET /lobby` redirects to `/game`, so the Back button or a reload can't reset it. Lobby changes from a stale tab answer with `HX-Redirect: /game`, and `POST /lobby/start` redirects without restarting
- All game state is on the server, so reloading any page shows the same state. The lobby preselects the loaded playlist

### Detailed Round Mechanics

1. Server picks a random track from the playlist (no repeats until the playlist is exhausted)
2. Server tells Spotify to play the track on the chosen device: the browser's player or a Spotify Connect device (via the JS bridge)
3. UI shows "Player X's turn" with inputs for song title, artist (optional) and release year (optional) -- **the first player rotates each round** (round-robin) for fairness
4. Player submits a guess (HTMX `POST /game/guess`) or skips (`POST /game/skip`)
5. `GameState.submit_guess` fuzzy-matches song and artist, checks the year, and awards points
6. Next player's turn is shown (HTMX swap of the guess form area)
7. **Previous guesses are hidden** so later players cannot cheat
8. After the last player has guessed (or skipped), the round moves to `ROUND_RESULT` and the server reveals the answer and shows who got what right
9. Host clicks "Next Round" to continue, or "See Final Leaderboard" once all rounds are done

### Fuzzy Matching Rules

Implemented in `app/matching.py`:

- Both strings are normalized: Spotify version suffixes (`" - Remastered 2011"`) and bracketed parts (`"(feat. X)"`) are removed, then lowercase, punctuation stripped, leading "The" dropped
- Titles with a leading bracket like `"(I Can't Get No) Satisfaction"` match with or without the bracketed words
- Compare using `thefuzz.fuzz.token_sort_ratio`; **>= 75** counts as correct (handles typos and word order)
- There is deliberately no substring matching, so a single word from a longer title (e.g. "love") does not count
- Artist guesses match if they fit any of the track's artists
- Spotify credits acts like "Bob Marley & The Wailers" as one artist, so the lead ("Bob Marley") and the backing band ("The Wailers") also count on their own. This split only happens before "& the", "and the" or "with the", so neither half of names like "Simon & Garfunkel" or "Earth, Wind & Fire" counts alone
- Years must match exactly
- The round result shows the title without version info (`" - Remastered 2012"`, `"(Radio Edit)"`), but keeps other bracketed parts like `"(feat. X)"`

## Scoring

Point values come from the `[points]` table in `config.toml` (loaded by `app/game_config.py` into `ScoringConfig`). Defaults:

- **Correct song title**: 1 point (`song`)
- **Correct artist**: 1 point (`artist`)
- **Correct release year**: multiplies the points of that guess (`year_multiplier`, default 2; worth nothing on its own)
- All correct guessers in a round score equally, and the rotating start spreads any turn-order advantage
- Per-player totals of correct songs, artists and years are shown on the final leaderboard
- Per-game leaderboard only; resets when a new game starts
- Displayed after each round and as a final summary

## Styling and Themes

- Stylesheets load in this order: `reset.css`, `monospace.css` (layout, type, form controls on a character grid), `theme.css` (font faces, palette, themes), then `app.css` and page styles
- `base.html` opens every page with The Monospace Web's header table: title, subtitle and a language selector. The selector preselects the browser's language from `Accept-Language` (`app/i18n.py`, English or German, falling back to English). Switching languages is not implemented yet. The app version is in the footer
- Pages are laid out for phones, tablets and desktop browsers alike. Rows wrap instead of overflowing, since `body` cuts off horizontal overflow, and wide tables scroll inside `.table-scroll`
- The app theme is uchū purple and uses all three shades: light for the background, dark for text and borders, the mid shade as accent
- Each player has a `PlayerColor` (red, orange, yellow, green, blue, pink). Purple stays the app's own color, and gray and yin/yang are left out. Colors are unique per game, so a game has at most `MAX_PLAYERS` (6) players
- New players get the first free color and can pick another in the lobby (`POST /lobby/set-player-color`). A color taken by another player is disabled
- On the game page the guess form carries `data-turn="<color>"`. `theme.css` switches the whole page with `:root:has([data-turn=...])`, so the theme follows the player on turn without JS. The round result has no turn and falls back to purple
- A theme defines `--color-light`, `--color-base`, `--color-dark`, `--color-text` and `--color-accent`, from which the Monospace Web variables (`--text-color`, `--background-color`, ...) are derived. Purple, red and blue use their dark shade for text. For orange, yellow, green and pink the dark shade is too light to read on the light shade, so they use yin for text and the dark shade as accent
- `[data-theme="<color>"]` applies a theme to a single element, as the lobby's color swatches do
- The five theme colors are registered with `@property` as `<color>`, so `:root` transitions them in 0.4 s when the palette changes. Everything derived from them blends along. The transition is off under `prefers-reduced-motion`

## Release Year Enrichment

Spotify's album release date is often a remaster or compilation year. After a playlist is loaded, `app/musicbrainz.py` runs as a background `asyncio` task and looks up each track's earliest release year on MusicBrainz, overwriting the Spotify year only when MusicBrainz reports an earlier one.

- MusicBrainz allows 1 request per second, so the task sleeps between lookups
- The lobby polls `/lobby/enrichment-status` via HTMX until the task is done
- Loading another playlist cancels the running task before starting a new one
- The game can start before enrichment finishes. The task takes its next track from `GameState.tracks_to_verify()`, which re-evaluates the order on every step: the current round's track first, then the upcoming rounds in play order, then the rest of the playlist. A new round's year is therefore verified within a second or two
- Requests send a `User-Agent` with the app version and repository URL, as MusicBrainz requires

## Project Structure

```
musically/
├── app/
│   ├── __init__.py
│   ├── main.py              # FastAPI app, startup, middleware
│   ├── config.py             # Settings (Spotify client ID/secret, env vars)
│   ├── game_config.py        # Loads playlists and scoring from config.toml
│   ├── logging_config.py     # Log format and LOG_LEVEL
│   ├── middleware.py         # Request logging
│   ├── spotify.py            # Spotify Web API client (auth, playlist, playback)
│   ├── game.py               # Game state dataclasses and logic
│   ├── i18n.py               # Supported languages, browser language detection
│   ├── matching.py           # Fuzzy matching logic
│   ├── musicbrainz.py        # Original release year lookup
│   ├── project.py            # Version and repository URL from pyproject.toml
│   ├── templating.py         # Shared Jinja2Templates instance
│   ├── routes/
│   │   ├── __init__.py
│   │   ├── auth.py           # /login, /callback -- Spotify OAuth, is_logged_in
│   │   ├── lobby.py          # /lobby -- player registration, playlist, game config
│   │   └── game.py           # /game/* -- round play, guessing, leaderboard
│   └── templates/
│       ├── base.html          # Base layout (includes HTMX)
│       ├── home.html          # Landing page with "Login with Spotify"
│       ├── lobby.html         # Player names, playlist input, round config
│       ├── game.html          # Main game view (loads the Spotify SDK)
│       ├── partials/
│       │   ├── add_player_form.html      # Player name input, or a notice once the game is full
│       │   ├── device_picker.html        # Playback device selection in the lobby
│       │   ├── guess_form.html           # Current player's guess input
│       │   ├── lobby_player_update.html  # Player list plus out-of-band add form, start form and messages
│       │   ├── messages.html             # Shared message pane; polls release year lookup
│       │   ├── messages_oob.html         # Out-of-band swap wrapper for messages.html
│       │   ├── player_list.html          # Registered players with their color swatches
│       │   ├── round.html                # Round header, scores and guess area; swapped per round
│       │   ├── round_result.html         # Round summary
│       │   ├── scoreboard.html           # Current scores
│       │   └── start_game_form.html      # Round count and start button
│       └── leaderboard.html   # Final game-over leaderboard
├── static/
│   ├── css/                   # reset, monospace, theme, app and page stylesheets
│   ├── fonts/                 # JetBrains Mono (variable woff2) and its OFL license
│   └── js/
│       └── spotify-player.js  # Playback controls for the SDK and Spotify Connect
├── tests/                     # Pytest suite, mirrors app/
├── docs/
│   └── architecture.md        # This file
├── config.toml                # Predefined playlists and scoring
├── Dockerfile, docker-compose.yml
├── render.yaml                # Render Blueprint (free web service, deploys on push)
├── pyproject.toml
├── .env.example               # Template for SPOTIFY_CLIENT_ID, SPOTIFY_CLIENT_SECRET
└── README.md
```

## Key Dependencies

- `fastapi` -- web framework
- `uvicorn` -- ASGI server
- `jinja2` -- HTML templating
- `httpx` -- async HTTP client for Spotify API calls
- `thefuzz[speedup]` -- fuzzy string matching
- `python-dotenv` -- load `.env` config
- `itsdangerous` -- secure cookie-based sessions
- `python-multipart` -- form data parsing

## HTMX + Spotify JS Bridge

Since HTMX drives the UI but Spotify playback requires JavaScript, a small bridge is needed:

- `game.html` contains a hidden HTMX form (`#play-track-form`, `hx-post="/game/play-track"`) with an empty `device_id` field
- When the SDK fires `ready`, the JS writes the device ID into that field and submits the form
- The server looks up the current round's track and starts playback on that device
- Only the first round loads `/game` as a full page. "Next Round" (`POST /game/next-round`) swaps `partials/round.html` into `#round`, so the SDK player and its device survive across rounds
- The swapped-in partial contains an element with `hx-trigger="load"` that posts to `/game/play-track` with `hx-include="#device-id"`, starting the new track without any extra JS. If the player isn't ready yet the device ID is empty, the request is a no-op, and the `ready` handler starts playback instead
- The partial also carries a top-level `<title>`, which htmx uses to update the document title
- `/game/next-round` only advances from `ROUND_RESULT`; a repeated click returns 204 so the page stays put
- Forms that stop the song ("Next Round", "End Game", "See Final Leaderboard") carry `data-fade-out`. A capture-phase `submit` listener in the JS holds the submission, pauses the song, and then resubmits the form. Because it runs before htmx's own handler, the next track is only requested once the song is paused, and a Connect device doesn't keep playing after the game
- In browser mode, pausing fades the SDK volume to zero over 1.5 s and restores it afterwards, and resuming fades back in. This applies to the play/pause button and the forms above. Commands run one after another, and the button is disabled while any of them is in progress
- The script gets its mode from `data-*` attributes on its own `<script>` tag. In browser mode the SDK is loaded and its events drive the UI. If the SDK reports `autoplay_failed`, the status line suggests picking a Spotify device in the lobby
- In Connect mode the SDK isn't loaded. `#device-id` is prefilled with the chosen device, playback starts once the DOM is ready, and the controls go through `GET /game/playback`, `POST /game/pause` and `/game/resume`. The state is polled every 5 s for the elapsed time
- Connect mode doesn't fade: every volume step would be a Web API call, and the device's own volume stays untouched. Spotify doesn't guarantee the order of player commands, so a pause waits briefly before the next track is started
- Reloading `/game` continues the current song. `RoundState.playback_started` marks a track that was already started; a later `/game/play-track` for it reads `/me/player` first. If the same device still has the track, nothing is sent, so a paused song stays paused. If another device has it (the browser player gets a new device ID on every page load), the track restarts on the new device at the reported position. Otherwise it starts from the beginning
- This keeps JS minimal and lets HTMX handle all game flow navigation

## Session Management

- A signed cookie (Starlette `SessionMiddleware`, backed by `itsdangerous`) stores the OAuth state and an `authenticated` flag
- Game state and Spotify tokens are process-wide singletons on `app.state`
- Single-session design: one active game per server process (party mode simplification)
- If needed later, multiple concurrent games can be supported by keying state on a session ID

## Configuration / Environment

Required environment variables (`.env`):
- `SPOTIFY_CLIENT_ID` -- from Spotify Developer Dashboard
- `SPOTIFY_CLIENT_SECRET` -- from Spotify Developer Dashboard
- `SPOTIFY_REDIRECT_URI` -- e.g. `http://127.0.0.1:8000/callback`
- `SECRET_KEY` -- for signing session cookies

## Open Design Notes

- **Endless mode**: When rounds are set to 0 (or "endless"), the game continues until the host clicks "End Game". The server keeps picking random songs (cycling through the playlist, re-shuffling if exhausted).
- **Skip**: Each player can skip their turn (no points, no penalty).
- **Song preview duration**: The full song plays until all players have guessed. No artificial time limit for MVP, but a configurable timer per turn could be added later.
