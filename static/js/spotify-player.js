window.onSpotifyWebPlaybackSDKReady = () => {
    function setPlayerStatus(text, isError = false) {
        const status = document.getElementById("player-status");
        status.textContent = text;
        status.className = isError
            ? "message message--error"
            : "message message--status";
    }

    function setPlayingStatus() {
        const status = document.getElementById("player-status");
        status.className = "message message--status";
        status.innerHTML =
            'Playing song... <span class="vinyl-icon" aria-hidden="true"><span class="vinyl-icon__disc">\uD83D\uDCBF</span></span>';
    }

    const player = new Spotify.Player({
        name: "Musically Game",
        getOAuthToken: (cb) => {
            fetch("/game/token")
                .then((resp) => resp.json())
                .then((data) => cb(data.access_token))
                .catch(() => setPlayerStatus("Could not fetch Spotify token", true));
        },
        volume: 0.8,
    });

    player.addListener("player_state_changed", (state) => {
        if (state && !state.paused) {
            setPlayingStatus();
        }
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

    async function fadeOut() {
        const state = await player.getCurrentState();
        if (!state || state.paused) {
            return;
        }
        const volume = await player.getVolume();
        for (let step = 1; step <= FADE_STEPS; step++) {
            await player.setVolume(volume * (1 - step / FADE_STEPS));
            await new Promise((resolve) => setTimeout(resolve, FADE_MS / FADE_STEPS));
        }
        await player.pause();
        await player.setVolume(volume);
    }

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
        fadeOut()
            .catch(() => {})
            .finally(() => {
                form.dataset.fade = "done";
                form.requestSubmit();
            });
    }, true);

    player.connect();
};
