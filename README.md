# vaarattu-community-playlist-maker

A Python script that creates Spotify playlists from Twitch channel points redemptions. This tool fetches song requests submitted through a Twitch channel points reward and compiles them into a Spotify playlist.

## Features

- 🎮 Fetches Twitch channel points redemptions using the Twitch Helix API with OAuth
- 🔐 Secure OAuth 2.0 authentication for both Twitch and Spotify
- 🎵 Parses Spotify track URLs from redemption messages
- 📝 Creates a new Spotify playlist with all requested songs
- ✅ Handles pagination for large numbers of redemptions
- 🔄 Supports multiple Spotify URL formats (open.spotify.com and spotify:track:)
- 🌐 Built-in local callback server for OAuth flows

## Prerequisites

- Python 3.7+
- Twitch Developer Application (for Client ID and Secret)
- Spotify Developer Application (for Client ID and Secret)
- A Twitch channel with a channel points reward named "song request bot"

## Setup

1. **Clone the repository:**

   ```bash
   git clone https://github.com/Koodattu/vaarattu-community-playlist-maker.git
   cd vaarattu-community-playlist-maker
   ```

2. **Install dependencies:**

   ```bash
   pip install -r requirements.txt
   ```

3. **Configure environment variables:**

   Create a `.env` file in the project root with your credentials:

   ```env
   TWITCH_CLIENT_ID=your_twitch_client_id
   TWITCH_CLIENT_SECRET=your_twitch_client_secret

   SPOTIFY_CLIENT_ID=your_spotify_client_id
   SPOTIFY_CLIENT_SECRET=your_spotify_client_secret

   SPOTIFY_CALLBACK_URL=http://localhost:5000/spotify/callback
   TWITCH_CALLBACK_URL=http://localhost:5000/twitch/callback
   ```

### Getting Twitch Credentials

1. Go to [Twitch Developer Console](https://dev.twitch.tv/console)
2. Register a new application
3. Set OAuth Redirect URL to `http://localhost:5000/twitch/callback`
4. Copy the Client ID and generate a Client Secret

### Getting Spotify Credentials

1. Go to [Spotify Developer Dashboard](https://developer.spotify.com/dashboard)
2. Create a new app
3. Add `http://localhost:5000/spotify/callback` to Redirect URIs
4. Copy the Client ID and Client Secret

## Usage

Run the script:

```bash
python main.py
```

When prompted, enter the Twitch channel name you want to fetch redemptions from.

The script will:

1. Open your browser for Twitch OAuth authentication (requires `channel:read:redemptions` scope)
2. Start a local callback server to receive the OAuth token
3. Get the broadcaster ID from the channel name
4. List all custom channel points rewards
5. Find the reward named "song request bot"
6. Fetch all fulfilled redemptions for that reward
7. Parse Spotify URLs from the redemptions
8. Open your browser for Spotify OAuth authentication (first time only)
9. Create a new playlist named "{channel_name} - Community Song Requests"
10. Add all valid tracks to the playlist

## How It Works

### Twitch Integration

The script uses the **Twitch Helix API with OAuth 2.0 Authorization Code Flow** to:

- Authenticate the user with the `channel:read:redemptions` scope
- Get the broadcaster ID from the channel name
- List all custom channel points rewards
- Find the reward named "song request bot"
- Fetch all fulfilled redemptions for that reward

**Important:** The script requires **user access token** (not app access token) because reading channel points redemptions requires user authorization.

### Spotify Integration

The script uses Spotipy (Spotify Python library) to:

- Authenticate using OAuth 2.0
- Create a public playlist
- Add tracks in batches (max 100 per request)

### URL Parsing

The script can parse Spotify track IDs from:

- Full URLs: `https://open.spotify.com/track/TRACK_ID`
- URI format: `spotify:track:TRACK_ID`
- Short format: `track/TRACK_ID`

## Configuration

You can modify these variables in `main.py`:

- `REWARD_NAME`: The name of the channel points reward to fetch (default: "song request bot")

## Troubleshooting

**"Could not find reward named 'song request bot'"**

- Make sure the channel has a channel points reward with that exact name
- The script will print available rewards if it can't find the target reward

**"Could not parse Spotify URL"**

- Some redemptions may contain invalid or non-Spotify URLs
- These will be skipped with a warning message

**Authentication issues**

- Make sure your `.env` file has the correct credentials
- Ensure redirect URLs match in both the `.env` file and developer consoles

## License

MIT License - see LICENSE file for details
