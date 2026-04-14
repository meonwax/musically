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

    player.addListener("ready", ({ device_id }) => {
        console.log("Spotify player ready, device:", device_id);
        currentDeviceId = device_id;
        document.getElementById("device-id").value = device_id;
        document.getElementById("player-status").textContent = "Player ready";
        document.getElementById("play-track-form").requestSubmit();
    });

    player.addListener("not_ready", () => {
        document.getElementById("player-status").textContent =
            "Player went offline";
    });

    player.addListener("initialization_error", ({ message }) => {
        console.error("Spotify init error:", message);
        document.getElementById("player-status").textContent =
            "Init error: " + message;
    });

    player.addListener("authentication_error", ({ message }) => {
        console.error("Spotify auth error:", message);
        document.getElementById("player-status").textContent =
            "Auth error: " + message;
    });

    player.addListener("account_error", ({ message }) => {
        console.error("Spotify account error:", message);
        document.getElementById("player-status").textContent =
            "Account error (Premium required): " + message;
    });

    player.connect();
};
