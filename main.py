import os
import re
import webbrowser
import secrets
from datetime import datetime
from dotenv import load_dotenv
import asyncio
import aiohttp
from aiohttp import web
import spotipy
from spotipy.oauth2 import SpotifyOAuth
from urllib.parse import urlencode, parse_qs

# Load environment variables
load_dotenv()

# Twitch credentials
TWITCH_CLIENT_ID = os.getenv('TWITCH_CLIENT_ID')
TWITCH_CLIENT_SECRET = os.getenv('TWITCH_CLIENT_SECRET')
TWITCH_REDIRECT_URI = os.getenv('TWITCH_CALLBACK_URL')

# Spotify credentials
SPOTIFY_CLIENT_ID = os.getenv('SPOTIFY_CLIENT_ID')
SPOTIFY_CLIENT_SECRET = os.getenv('SPOTIFY_CLIENT_SECRET')
SPOTIFY_REDIRECT_URI = os.getenv('SPOTIFY_CALLBACK_URL')

# Configuration
REWARD_NAME = "song request bot"
TWITCH_SCOPES = "channel:read:redemptions"


class TwitchOAuth:
    """Handles Twitch OAuth flow with local callback server"""

    def __init__(self, client_id, client_secret, redirect_uri):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.access_token = None
        self.refresh_token = None
        self.state = None
        self.auth_code = None
        self.app = None
        self.runner = None

    async def oauth_callback(self, request):
        """Handle OAuth callback from Twitch"""
        params = request.rel_url.query

        # Check for errors
        if 'error' in params:
            error_description = params.get('error_description', 'Unknown error')
            return web.Response(text=f"❌ Authorization failed: {error_description}", status=400)

        # Verify state
        if params.get('state') != self.state:
            return web.Response(text="❌ State mismatch - possible CSRF attack", status=400)

        # Get authorization code
        self.auth_code = params.get('code')

        if not self.auth_code:
            return web.Response(text="❌ No authorization code received", status=400)

        # Exchange code for token
        success = await self.exchange_code_for_token()

        if success:
            # Return success page
            html = """
            <html>
                <head><title>Twitch Authorization Success</title></head>
                <body style="font-family: Arial; text-align: center; padding: 50px;">
                    <h1 style="color: #9146FF;">✓ Authorization Successful!</h1>
                    <p>You can close this window and return to the application.</p>
                </body>
            </html>
            """
            return web.Response(text=html, content_type='text/html')
        else:
            return web.Response(text="❌ Failed to exchange authorization code for token", status=500)

    async def exchange_code_for_token(self):
        """Exchange authorization code for access token"""
        url = "https://id.twitch.tv/oauth2/token"
        data = {
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': self.auth_code,
            'grant_type': 'authorization_code',
            'redirect_uri': self.redirect_uri
        }

        async with aiohttp.ClientSession() as session:
            async with session.post(url, data=data) as response:
                if response.status == 200:
                    token_data = await response.json()
                    self.access_token = token_data.get('access_token')
                    self.refresh_token = token_data.get('refresh_token')
                    print(f"✓ Obtained Twitch user access token")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Token exchange failed: {error_text}")
                    return False

    async def start_oauth_flow(self):
        """Start the OAuth flow by opening browser and starting callback server"""
        # Generate random state for CSRF protection
        self.state = secrets.token_urlsafe(32)

        # Build authorization URL
        auth_params = {
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'response_type': 'code',
            'scope': TWITCH_SCOPES,
            'state': self.state
        }
        auth_url = f"https://id.twitch.tv/oauth2/authorize?{urlencode(auth_params)}"

        # Start local callback server
        self.app = web.Application()
        self.app.router.add_get('/twitch/callback', self.oauth_callback)

        self.runner = web.AppRunner(self.app)
        await self.runner.setup()

        # Parse port from redirect_uri
        port = 5000  # Default
        if 'localhost:' in self.redirect_uri:
            port = int(self.redirect_uri.split(':')[-1].split('/')[0])

        site = web.TCPSite(self.runner, 'localhost', port)
        await site.start()

        print(f"\n🔐 Starting Twitch OAuth flow...")
        print(f"📡 Callback server started on port {port}")
        print(f"🌐 Opening browser for authorization...")

        # Open browser
        webbrowser.open(auth_url)

        # Wait for callback (with timeout)
        timeout = 120  # 2 minutes
        for _ in range(timeout):
            await asyncio.sleep(1)
            if self.access_token:
                break

        # Cleanup
        await self.runner.cleanup()

        if not self.access_token:
            print("❌ OAuth timeout - authorization not completed")
            return False

        return True


class TwitchAPI:
    """Handler for Twitch API calls"""

    def __init__(self, client_id, client_secret, access_token=None):
        self.client_id = client_id
        self.client_secret = client_secret
        self.access_token = access_token
        self.base_url = "https://api.twitch.tv/helix"

    async def get_broadcaster_id(self, broadcaster_login):
        """Get broadcaster ID from login name"""
        headers = {
            'Client-ID': self.client_id,
            'Authorization': f'Bearer {self.access_token}'
        }

        url = f"{self.base_url}/users"
        params = {'login': broadcaster_login}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                data = await response.json()
                if data.get('data'):
                    return data['data'][0]['id']
                return None

    async def get_custom_rewards(self, broadcaster_id):
        """Get all custom rewards for a broadcaster"""
        headers = {
            'Client-ID': self.client_id,
            'Authorization': f'Bearer {self.access_token}'
        }

        url = f"{self.base_url}/channel_points/custom_rewards"
        params = {'broadcaster_id': broadcaster_id}

        async with aiohttp.ClientSession() as session:
            async with session.get(url, headers=headers, params=params) as response:
                data = await response.json()
                return data.get('data', [])

    async def get_reward_redemptions(self, broadcaster_id, reward_id, statuses=None):
        """Get redemptions for a specific reward across multiple statuses"""
        if statuses is None:
            statuses = ['CANCELED', 'FULFILLED', 'UNFULFILLED']

        all_redemptions = []

        # Fetch redemptions for each status
        for status in statuses:
            headers = {
                'Client-ID': self.client_id,
                'Authorization': f'Bearer {self.access_token}'
            }

            url = f"{self.base_url}/channel_points/custom_rewards/redemptions"
            params = {
                'broadcaster_id': broadcaster_id,
                'reward_id': reward_id,
                'status': status,
                'first': 50
            }

            async with aiohttp.ClientSession() as session:
                while True:
                    async with session.get(url, headers=headers, params=params) as response:
                        data = await response.json()
                        redemptions = data.get('data', [])
                        all_redemptions.extend(redemptions)

                        # Check for pagination
                        cursor = data.get('pagination', {}).get('cursor')
                        if cursor:
                            params['after'] = cursor
                        else:
                            break

        return all_redemptions


def parse_spotify_url(text):
    """Extract Spotify track ID from various URL formats"""
    if not text:
        return None

    # Pattern for spotify URLs
    # Matches: https://open.spotify.com/track/ID or spotify:track:ID
    patterns = [
        r'https?://open\.spotify\.com/track/([a-zA-Z0-9]+)',
        r'spotify:track:([a-zA-Z0-9]+)',
        r'track/([a-zA-Z0-9]+)'
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return match.group(1)

    return None


async def get_song_requests_from_twitch(broadcaster_login):
    """Fetch all song requests from Twitch channel points redemptions"""
    print(f"\n🎵 Fetching song requests for {broadcaster_login}...")

    # Start OAuth flow to get user access token
    oauth = TwitchOAuth(TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, TWITCH_REDIRECT_URI)
    success = await oauth.start_oauth_flow()

    if not success:
        print("❌ Failed to authenticate with Twitch")
        return [], []

    # Create API instance with user access token
    twitch = TwitchAPI(TWITCH_CLIENT_ID, TWITCH_CLIENT_SECRET, oauth.access_token)

    # Get broadcaster ID
    broadcaster_id = await twitch.get_broadcaster_id(broadcaster_login)
    if not broadcaster_id:
        print(f"❌ Could not find broadcaster: {broadcaster_login}")
        return [], []

    print(f"✓ Found broadcaster ID: {broadcaster_id}")

    # Get all custom rewards
    rewards = await twitch.get_custom_rewards(broadcaster_id)
    print(f"✓ Found {len(rewards)} custom rewards")

    # Find the song request reward
    song_reward = None
    for reward in rewards:
        if reward['title'].lower() == REWARD_NAME.lower():
            song_reward = reward
            break

    if not song_reward:
        print(f"❌ Could not find reward named '{REWARD_NAME}'")
        print(f"Available rewards: {[r['title'] for r in rewards]}")
        return [], []

    print(f"✓ Found '{song_reward['title']}' reward (ID: {song_reward['id']})")

    # Get redemptions for this reward (all statuses)
    print("📥 Fetching redemptions for all statuses (CANCELED, FULFILLED, UNFULFILLED)...")
    redemptions = await twitch.get_reward_redemptions(broadcaster_id, song_reward['id'])
    print(f"✓ Found {len(redemptions)} total redemptions")

    # Parse Spotify URLs from redemptions
    song_requests = []
    search_requests = []  # For requests that need Spotify search

    for redemption in redemptions:
        user_input = redemption.get('user_input', '')
        track_id = parse_spotify_url(user_input)

        if track_id:
            song_requests.append({
                'track_id': track_id,
                'user': redemption['user_name'],
                'redeemed_at': redemption['redeemed_at'],
                'status': redemption['status'],
                'original_input': user_input,
                'method': 'direct_url'
            })
        else:
            # Check if input contains a URL (might be non-Spotify URL)
            if 'http://' in user_input.lower() or 'https://' in user_input.lower() or 'www.' in user_input.lower():
                print(f"⚠️  Skipping non-Spotify URL: {user_input[:50]}...")
            elif user_input.strip():  # Has text but no URL - try search
                search_requests.append({
                    'search_query': user_input,
                    'user': redemption['user_name'],
                    'redeemed_at': redemption['redeemed_at'],
                    'status': redemption['status']
                })
            else:
                print(f"⚠️  Empty input from {redemption['user_name']}")

    print(f"✓ Successfully parsed {len(song_requests)} Spotify track URLs")
    print(f"📝 Found {len(search_requests)} requests that need Spotify search")

    return song_requests, search_requests


def create_spotify_playlist(song_requests, search_requests, broadcaster_name):
    """Create a Spotify playlist and add songs to it"""
    print(f"\n🎧 Creating Spotify playlist...")

    # Set up Spotify authentication with required scopes
    scope = "playlist-modify-public playlist-modify-private"
    sp = spotipy.Spotify(auth_manager=SpotifyOAuth(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
        redirect_uri=SPOTIFY_REDIRECT_URI,
        scope=scope
    ))

    # Get current user
    current_user = sp.current_user()
    user_id = current_user['id']
    print(f"✓ Authenticated as Spotify user: {current_user['display_name']}")

    # Create playlist
    playlist_name = f"{broadcaster_name} - Community Song Requests"
    playlist_description = f"Community requested songs from Twitch channel points. Created on {datetime.now().strftime('%Y-%m-%d')}"

    playlist = sp.user_playlist_create(
        user=user_id,
        name=playlist_name,
        public=True,
        description=playlist_description
    )

    print(f"✓ Created playlist: {playlist['name']}")
    print(f"  URL: {playlist['external_urls']['spotify']}")

    # Process direct URL tracks first
    track_uris = [f"spotify:track:{req['track_id']}" for req in song_requests]

    # Process search requests
    print(f"\n🔍 Searching Spotify for {len(search_requests)} text-based requests...")
    search_results = []

    for search_req in search_requests:
        query = search_req['search_query']
        try:
            results = sp.search(q=query, type='track', limit=1)
            if results['tracks']['items']:
                track = results['tracks']['items'][0]
                track_uri = track['uri']
                search_results.append({
                    'track_id': track['id'],
                    'track_uri': track_uri,
                    'track_name': track['name'],
                    'artist': track['artists'][0]['name'],
                    'user': search_req['user'],
                    'search_query': query,
                    'method': 'search'
                })
                print(f"  ✓ Found: '{track['name']}' by {track['artists'][0]['name']} (query: '{query[:40]}...')")
            else:
                print(f"  ❌ No results for: '{query[:50]}...'")
        except Exception as e:
            print(f"  ❌ Search error for '{query[:50]}...': {e}")

    print(f"✓ Found {len(search_results)} tracks via search")

    # Add search results to the track list
    search_track_uris = [result['track_uri'] for result in search_results]
    all_track_uris = track_uris + search_track_uris

    all_track_uris = list(dict.fromkeys(all_track_uris))  # Remove duplicates while preserving order

    # Spotify allows max 100 tracks per request, so we batch them
    batch_size = 100
    added_count = 0
    failed_tracks = []

    print(f"\n📝 Adding {len(all_track_uris)} total tracks to playlist...")

    for i in range(0, len(all_track_uris), batch_size):
        batch = all_track_uris[i:i + batch_size]
        try:
            sp.playlist_add_items(playlist['id'], batch)
            added_count += len(batch)
            print(f"✓ Added {len(batch)} tracks (total: {added_count}/{len(all_track_uris)})")
        except Exception as e:
            print(f"❌ Error adding batch: {e}")
            failed_tracks.extend(batch)

    # Print summary
    print(f"\n📊 Summary:")
    print(f"  Direct URL tracks: {len(song_requests)}")
    print(f"  Search-based tracks: {len(search_results)}")
    print(f"  Total tracks added: {added_count}")
    if failed_tracks:
        print(f"  Failed to add: {len(failed_tracks)}")

    # Print some track details
    if song_requests:
        print(f"\n🎵 Sample of direct URL requests:")
        for req in song_requests[:3]:
            print(f"  - Track ID: {req['track_id']} (requested by {req['user']}, status: {req['status']})")

    if search_results:
        print(f"\n🔍 Sample of search-based requests:")
        for result in search_results[:3]:
            print(f"  - '{result['track_name']}' by {result['artist']} (query: '{result['search_query'][:40]}...', requested by {result['user']})")

    return playlist


async def main():
    """Main execution function"""
    print("=" * 60)
    print("🎵 Twitch Community Playlist Maker 🎵")
    print("=" * 60)

    # Get broadcaster login name from user
    broadcaster_login = input("\nEnter Twitch channel name: ").strip()

    if not broadcaster_login:
        print("❌ No channel name provided")
        return

    # Fetch song requests from Twitch
    result = await get_song_requests_from_twitch(broadcaster_login)

    if not result:
        print("\n❌ Failed to fetch song requests. Exiting.")
        return

    song_requests, search_requests = result

    if not song_requests and not search_requests:
        print("\n❌ No valid song requests found. Exiting.")
        return

    # Create Spotify playlist
    playlist = create_spotify_playlist(song_requests, search_requests, broadcaster_login)

    print("\n" + "=" * 60)
    print("✅ Playlist created successfully!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())