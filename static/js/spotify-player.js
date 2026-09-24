window.onSpotifyWebPlaybackSDKReady = () => {
    const MAX_VOLUME = 1;
    const PAUSE_ICON = "\u23F8\uFE0E";
    const PLAY_ICON = "\u25B6\uFE0E";

    const status = document.getElementById("player-status");
    const statusText = document.getElementById("player-status-text");
    const controls = document.getElementById("player-controls");
    const toggle = document.getElementById("play-toggle");
    const elapsed = document.getElementById("elapsed");
    const startMusic = document.getElementById("start-music");

    function setPlayerStatus(text, isError = false) {
        statusText.textContent = text;
        controls.classList.add("hidden");
        startMusic.classList.add("hidden");
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

    const player = new Spotify.Player({
        name: "Musically Game",
        getOAuthToken: (cb) => {
            fetch("/game/token")
                .then((resp) => resp.json())
                .then((data) => cb(data.access_token))
                .catch(() => setPlayerStatus("Could not fetch Spotify token", true));
        },
        volume: MAX_VOLUME,
    });

    // Mobile browsers only let the SDK start audio from a user gesture. Songs
    // are started by the server, so a tap has to unlock the player beforehand.
    let unlocked = false;

    function unlockAudio() {
        if (unlocked) {
            return;
        }
        unlocked = true;
        Promise.resolve(player.activateElement()).catch(() => (unlocked = false));
    }

    document.addEventListener("click", unlockAudio, true);
    document.addEventListener("submit", unlockAudio, true);

    player.addListener("autoplay_failed", () => {
        unlocked = false;
        startMusic.classList.remove("hidden");
    });

    startMusic.addEventListener("click", () => {
        startMusic.classList.add("hidden");
        player.resume();
    });

    // The SDK only reports the position when the state changes, so the
    // elapsed time is extrapolated from the last report while playing.
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

    player.addListener("player_state_changed", (state) => {
        if (!state) {
            return;
        }
        playback = {
            position: state.position,
            paused: state.paused,
            reportedAt: performance.now(),
        };
        if (!state.paused) {
            startMusic.classList.add("hidden");
        }
        showPlayback(state.paused);
        renderElapsed();
    });

    player.addListener("ready", ({ device_id }) => {
        document.getElementById("device-id").value = device_id;
        setPlayerStatus("Player ready");
        document.getElementById("play-track-form").requestSubmit();
    });

    player.addListener("not_ready", () => {
        setPlayerStatus("Player went offline", true);
    });

    player.addListener("initialization_error", ({ message }) => {
        setPlayerStatus("Init error: " + message, true);
    });

    player.addListener("authentication_error", ({ message }) => {
        setPlayerStatus("Auth error: " + message, true);
    });

    player.addListener("account_error", ({ message }) => {
        setPlayerStatus("Account error (Premium required): " + message, true);
    });

    const FADE_MS = 1500;
    const FADE_STEPS = 15;

    async function ramp(from, to) {
        for (let step = 1; step <= FADE_STEPS; step++) {
            await player.setVolume(from + (to - from) * (step / FADE_STEPS));
            await new Promise((resolve) => setTimeout(resolve, FADE_MS / FADE_STEPS));
        }
    }

    async function fadeOut() {
        const state = await player.getCurrentState();
        if (!state || state.paused) {
            return;
        }
        await ramp(MAX_VOLUME, 0);
        await player.pause();
    }

    async function fadeIn() {
        await player.setVolume(0);
        await player.resume();
        await ramp(0, MAX_VOLUME);
    }

    // All fades drive the same volume, so they run one after another, and the
    // toggle stays disabled until none are left.
    let fadeQueue = Promise.resolve();
    let queuedFades = 0;

    function queueFade(task) {
        queuedFades++;
        toggle.disabled = true;
        fadeQueue = fadeQueue
            .then(task)
            .catch(() => player.setVolume(MAX_VOLUME).catch(() => {}))
            .finally(() => {
                queuedFades--;
                toggle.disabled = queuedFades > 0;
            });
        return fadeQueue;
    }

    toggle.addEventListener("click", () => {
        queueFade(async () => {
            const state = await player.getCurrentState();
            if (state) {
                await (state.paused ? fadeIn() : fadeOut());
            }
        });
    });

    // Capture phase runs before htmx's own submit handler on the form, so the
    // request (and with it the next track) waits until the fade is done.
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
        queueFade(async () => {
            await fadeOut().catch(() => {});
            await player.setVolume(MAX_VOLUME);
        }).then(() => {
            form.dataset.fade = "done";
            form.requestSubmit();
        });
    }, true);

    player.connect();
};
