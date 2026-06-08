let player = null;
let currentDeviceId = null;

window.onSpotifyWebPlaybackSDKReady = () => {
    const token = document.getElementById("spotify-data").dataset.token;
    console.log("Spotify SDK ready, token length:", token.length);

    player = new Spotify.Player({
        name: "Musically Game",
        getOAuthToken: (cb) => {
            fetch("/game/token")
                .then((resp) => resp.json())
                .then((data) => {
                    console.log("Refreshed token from server");
                    cb(data.access_token);
                })
                .catch(() => {
                    console.log("Token refresh failed, using embedded token");
                    cb(token);
                });
        },
        volume: 0.8,
    });

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

    player.addListener("player_state_changed", (state) => {
        if (state && !state.paused) {
            setPlayingStatus();
        }
    });

    player.addListener("ready", ({ device_id }) => {
        console.log("Spotify player ready, device:", device_id);
        currentDeviceId = device_id;
        document.getElementById("device-id").value = device_id;
        setPlayerStatus("Player ready");
        document.getElementById("play-track-form").requestSubmit();
    });

    player.addListener("not_ready", () => {
        setPlayerStatus("Player went offline", true);
    });

    player.addListener("initialization_error", ({ message }) => {
        console.error("Spotify init error:", message);
        setPlayerStatus("Init error: " + message, true);
    });

    player.addListener("authentication_error", ({ message }) => {
        console.error("Spotify auth error:", message);
        setPlayerStatus("Auth error: " + message, true);
    });

    player.addListener("account_error", ({ message }) => {
        console.error("Spotify account error:", message);
        setPlayerStatus(
            "Account error (Premium required): " + message,
            true,
        );
    });

    player.connect();
};
