"""MIT License

Copyright (c) 2022 Vocard Development

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
"""

import re
import time
import aiohttp

from base64 import b64encode
from typing import (
    List,
    Dict,
    Union,
    Optional
)

from .objects import Track, Album, Artist, Playlist, Category
from .exceptions import InvalidSpotifyURL, SpotifyRequestException 

BASE_URL = "https://api.spotify.com/v1/"
GRANT_URL = "https://accounts.spotify.com/api/token"
ANONYMOUS_GRANT_URL = "https://open.spotify.com/get_access_token"
REQUEST_URL = BASE_URL + "{type}s/{id}"
SEARCH_URL = BASE_URL + "search?q={query}&type={type}&limit={limit}"
SUGGESTION_URL = BASE_URL + "recommendations?limit={limit}&seed_tracks={seed_tracks}"
SPOTIFY_URL_REGEX = re.compile(
    r"https?://open.spotify.com/(?P<type>album|playlist|track|artist)/(?P<id>[a-zA-Z0-9]+)"
)

class Client:
    """The base client for the Spotify module of Voicelink.
       This class will do all the heavy lifting of getting all the metadata 
       for any Spotify URL you throw at it.
    """

    def __init__(self, client_id: str, client_secret: str) -> None:
        self._client_id: Optional[str] = client_id
        self._client_secret: Optional[str] = client_secret

        self.session: aiohttp.ClientSession = aiohttp.ClientSession()

        self._bearer_token: str = None
        self._expiry: int = 0
        self._auth_token: bytes = b64encode(f"{self._client_id}:{self._client_secret}".encode())
        self._grant_headers: Dict[str, str] = {"Authorization": f"Basic {self._auth_token.decode()}"}
        self._bearer_headers: Dict[str, str] = None

        self._categories: List[Category] = []

    async def _fetch_bearer_token(self) -> None:
        """Fetches and stores a bearer token for API authentication."""
        if self._client_id and self._client_secret:
            url, data = GRANT_URL, {"grant_type": "client_credentials"}
        else:
            url, data = ANONYMOUS_GRANT_URL, None

        async with self.session.post(url, data=data, headers=self._grant_headers) if data else self.session.get(url) as resp:
            if resp.status != 200:
                raise SpotifyRequestException(
                    f"Error fetching bearer token: {resp.status} {resp.reason}"
                )

            response_data: Dict = await resp.json()

        if self._client_id and self._client_secret:
            self._bearer_token = response_data["access_token"]
            self._expiry = time.time() + int(response_data["expires_in"]) - 10
        else:
            self._bearer_token = response_data["accessToken"]
            self._expiry = response_data["accessTokenExpirationTimestampMs"] / 1000

        self._bearer_headers = {"Authorization": f"Bearer {self._bearer_token}"}

    async def get_request(self, url: str) -> Dict:
        """Performs a GET request to the specified URL with authorization headers."""
        if not self._bearer_token or time.time() >= self._expiry:
            await self._fetch_bearer_token()

        async with self.session.get(url, headers=self._bearer_headers) as resp:
            if resp.status != 200:
                raise SpotifyRequestException(
                    f"Error while fetching results: {resp.status} {resp.reason}"
                )
            
            return await resp.json()

    async def track_search(self, query: str, track: str = "track", limit: int = 10) -> List[Track]:
        """Searches for tracks based on the provided query and returns a list of Track objects."""
        request_url = SEARCH_URL.format(query=query, type=track, limit=limit)
        data = await self.get_request(request_url)
        return [ Track(track) for track in data['tracks']['items'] ]

    async def similar_track(self, seed_tracks: str, *, limit: int = 10) -> List[Track]:
        """Retrieves tracks similar to the provided seed tracks and returns them as Track objects."""
        request_url = SUGGESTION_URL.format(limit=limit, seed_tracks=seed_tracks)
        data = await self.get_request(request_url)
        return [ Track(track) for track in data['tracks'] ]
            
    async def search(self, *, query: str) -> Union[Track, Album, Playlist]:
        """Searches for an item (track, album, artist, or playlist) by query and returns the corresponding object."""
        result = SPOTIFY_URL_REGEX.match(query)
        if not result:
            raise InvalidSpotifyURL("The Spotify link provided is not valid.")

        spotify_type = result.group("type")
        spotify_id = result.group("id")
        request_url = REQUEST_URL.format(type=spotify_type, id=spotify_id)

        if isArtist := (spotify_type == "artist"):
            request_url += "/top-tracks?market=US"

        data = await self.get_request(request_url)

        if spotify_type == "track":
            return Track(data)
        elif spotify_type == "album":
            return Album(data)
        elif isArtist:
            return Artist(data)
        
        tracks = [
            Track(track["track"])
            for track in data["tracks"]["items"] if track.get("track") is not None
        ]

        if not tracks:
            raise SpotifyRequestException("This playlist is empty and therefore cannot be queued.")

        next_page_url = data["tracks"].get("next")

        while next_page_url:
            next_data = await self.get_request(next_page_url)
            tracks.extend([
                Track(track["track"])
                for track in next_data.get("items", []) if track.get("track") is not None
            ])
            next_page_url = next_data.get("next")

        return Playlist(data, tracks)
    
    async def get_categories(self) -> List[Category]:
        """Fetches and returns available music categories from the Spotify API."""
        if not self._categories:
            request_url = f"{BASE_URL}browse/categories"
            
            while request_url:
                data = await self.get_request(request_url)
                items = data.get("categories", {}).get("items", [])
                self._categories.extend(Category(item) for item in items)
                request_url = data.get("categories", {}).get("next")

        return self._categories
    
    async def close(self) -> None:
        """Closes the HTTP session used for making API requests."""
        await self.session.close()