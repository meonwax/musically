(() => {
    const config = document.currentScript.dataset;

    const MAX_VOLUME = 1;
    const PAUSE_ICON = "\u23F8\uFE0E";
    const PLAY_ICON = "\u25B6\uFE0E";
    const FADE_MS = 1500;
    const FADE_STEPS = 15;
    const POLL_MS = 5000;

    const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));

    function whenDomReady(callback) {
        if (document.readyState === "loading") {
            document.addEventListener("DOMContentLoaded", callback);
        } else {
            callback();
        }
    }

    // Status line, elapsed timer and play/pause toggle, shared by the browser
    // player and Spotify Connect devices. `player` provides getCurrentState(),
    // pause() and resume().
    function setupControls(player, { playFailedText, onPlayStarted }) {
        const status = document.getElementById("player-status");
        const statusText = document.getElementById("player-status-text");
        const controls = document.getElementById("player-controls");
        const toggle = document.getElementById("play-toggle");
        const elapsed = document.getElementById("elapsed");

        function setPlayerStatus(text, isError = false) {
            statusText.textContent = text;
            controls.classList.add("hidden");
            status.className = isError
                ? "message message--error"
                : "message message--status";
        }

        function showPlayback(paused) {
            statusText.textContent = paused ? "Paused" : "Playing song...";
            toggle.textContent = paused ? PLAY_ICON : PAUSE_ICON;
            toggle.setAttribute("aria-label", paused ? "Play" : "Pause");
            toggle.title = paused ? "Play" : "Pause";
            controls.classList.remove("hidden");
            status.className = "message message--status";
        }

        // Positions are only reported now and then, so the elapsed time is
        // extrapolated from the last report while playing.
        let playback = null;

        function renderElapsed() {
            if (!playback) {
                return;
            }
            const ms = playback.position
                + (playback.paused ? 0 : performance.now() - playback.reportedAt);
            const seconds = Math.floor(ms / 1000);
            elapsed.textContent =
                Math.floor(seconds / 60) + ":" + String(seconds % 60).padStart(2, "0");
        }

        setInterval(renderElapsed, 250);

        function showState(state) {
            if (!state) {
                return;
            }
            playback = {
                position: state.position,
                paused: state.paused,
                reportedAt: performance.now(),
            };
            showPlayback(state.paused);
            renderElapsed();
        }

        async function pauseIfPlaying() {
            const state = await player.getCurrentState();
            if (state && !state.paused) {
                await player.pause();
            }
        }

        // Browser fades all drive the same volume, so commands run one after
        // another, and the toggle stays disabled until none are left.
        let commandQueue = Promise.resolve();
        let queuedCommands = 0;

        function queueCommand(task) {
            queuedCommands++;
            toggle.disabled = true;
            commandQueue = commandQueue
                .then(task)
                .catch(() => {})
                .finally(() => {
                    queuedCommands--;
                    toggle.disabled = queuedCommands > 0;
                });
            return commandQueue;
        }

        toggle.addEventListener("click", () => {
            queueCommand(async () => {
                const state = await player.getCurrentState();
                if (state) {
                    await (state.paused ? player.resume() : player.pause());
                }
            });
        });

        // Capture phase runs before htmx's own submit handler on the form, so
        // the request (and with it the next track) waits until the song is
        // paused. A Connect device would otherwise keep playing after the game.
        document.addEventListener("submit", (event) => {
            const form = event.target;
            if (!form.matches("[data-fade-out]") || form.dataset.fade === "done") {
                return;
            }
            event.preventDefault();
            event.stopImmediatePropagation();
            if (form.dataset.fade === "running") {
                return;
            }
            form.dataset.fade = "running";
            form.querySelectorAll("button").forEach((button) => (button.disabled = true));
            queueCommand(pauseIfPlaying).then(() => {
                form.dataset.fade = "done";
                form.requestSubmit();
            });
        }, true);

        document.addEventListener("htmx:afterRequest", (event) => {
            if (event.detail.pathInfo.requestPath !== "/game/play-track") {
                return;
            }
            if (event.detail.successful) {
                onPlayStarted();
            } else {
                setPlayerStatus(playFailedText, true);
            }
        });

        return { setPlayerStatus, showState };
    }

    function startBrowserPlayer() {
        let controls = null;
        const sdk = new Spotify.Player({
            name: config.playerName,
            getOAuthToken: (cb) => {
                fetch("/game/token")
                    .then((resp) => resp.json())
                    .then((data) => cb(data.access_token))
                    .catch(() => controls.setPlayerStatus("Could not fetch Spotify token", true));
            },
            volume: MAX_VOLUME,
        });

        async function ramp(from, to) {
            for (let step = 1; step <= FADE_STEPS; step++) {
                await sdk.setVolume(from + (to - from) * (step / FADE_STEPS));
                await sleep(FADE_MS / FADE_STEPS);
            }
        }

        // The volume is restored even if a fade fails, so a paused player is
        // never left silent.
        const player = {
            getCurrentState: () => sdk.getCurrentState(),
            async pause() {
                try {
                    await ramp(MAX_VOLUME, 0);
                    await sdk.pause();
                } finally {
                    await sdk.setVolume(MAX_VOLUME);
                }
            },
            async resume() {
                try {
                    await sdk.setVolume(0);
                    await sdk.resume();
                    await ramp(0, MAX_VOLUME);
                } finally {
                    await sdk.setVolume(MAX_VOLUME);
                }
            },
        };
        controls = setupControls(player, {
            playFailedText: "Could not start playback.",
            onPlayStarted: () => {},
        });

        sdk.addListener("player_state_changed", controls.showState);

        sdk.addListener("ready", ({ device_id }) => {
            document.getElementById("device-id").value = device_id;
            controls.setPlayerStatus("Player ready");
            document.getElementById("play-track-form").requestSubmit();
        });

        sdk.addListener("autoplay_failed", () => {
            controls.setPlayerStatus(
                "This browser blocked playback. Pick a Spotify device in the lobby instead.",
                true,
            );
        });

        sdk.addListener("not_ready", () => {
            controls.setPlayerStatus("Player went offline", true);
        });

        sdk.addListener("initialization_error", ({ message }) => {
            controls.setPlayerStatus("Init error: " + message, true);
        });

        sdk.addListener("authentication_error", ({ message }) => {
            controls.setPlayerStatus("Auth error: " + message, true);
        });

        sdk.addListener("account_error", ({ message }) => {
            controls.setPlayerStatus("Account error (Premium required): " + message, true);
        });

        sdk.connect();
    }

    function startConnectPlayer() {
        // Spotify doesn't guarantee the order of player commands, so a pause
        // gets a moment to apply before the next track is started.
        const SETTLE_MS = 400;

        let controls = null;

        async function post(path) {
            const resp = await fetch(path, { method: "POST" });
            if (!resp.ok) {
                throw new Error(path + " returned " + resp.status);
            }
        }

        const player = {
            async getCurrentState() {
                const resp = await fetch("/game/playback");
                if (!resp.ok) {
                    return null;
                }
                const state = await resp.json();
                controls.showState(state);
                return state;
            },
            async pause() {
                await post("/game/pause");
                await sleep(SETTLE_MS);
                refreshSoon();
            },
            async resume() {
                await post("/game/resume");
                refreshSoon();
            },
        };

        function refreshSoon() {
            setTimeout(() => player.getCurrentState().catch(() => {}), 1000);
        }

        controls = setupControls(player, {
            playFailedText: "Could not start playback on " + config.deviceName
                + ". Open Spotify on it and reload this page.",
            onPlayStarted: refreshSoon,
        });

        setInterval(() => player.getCurrentState().catch(() => {}), POLL_MS);
        document.getElementById("play-track-form").requestSubmit();
    }

    if (config.mode === "connect") {
        whenDomReady(startConnectPlayer);
    } else {
        window.onSpotifyWebPlaybackSDKReady = () => whenDomReady(startBrowserPlayer);
    }
})();
