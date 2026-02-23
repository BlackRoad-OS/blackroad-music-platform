"""Music platform backend for BlackRoad."""

import sqlite3
import json
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Optional, List, Dict
from pathlib import Path
import argparse
from collections import Counter

# Database setup
DB_PATH = Path.home() / ".blackroad" / "music.db"


@dataclass
class Track:
    """Track dataclass."""
    id: str
    title: str
    artist: str
    album: str
    genre: str
    duration_s: int
    plays: int = 0
    likes: int = 0
    file_path: str = ""
    uploaded_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())


def init_db():
    """Initialize database tables."""
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS tracks (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            artist TEXT NOT NULL,
            album TEXT NOT NULL,
            genre TEXT NOT NULL,
            duration_s INTEGER NOT NULL,
            plays INTEGER DEFAULT 0,
            likes INTEGER DEFAULT 0,
            file_path TEXT,
            uploaded_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS play_history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            track_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            played_at TEXT NOT NULL,
            FOREIGN KEY (track_id) REFERENCES tracks(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS likes (
            track_id TEXT NOT NULL,
            user_id TEXT NOT NULL,
            liked_at TEXT NOT NULL,
            PRIMARY KEY (track_id, user_id),
            FOREIGN KEY (track_id) REFERENCES tracks(id)
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS playlists (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            name TEXT NOT NULL,
            created_at TEXT NOT NULL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS playlist_tracks (
            playlist_id TEXT NOT NULL,
            track_id TEXT NOT NULL,
            added_at TEXT NOT NULL,
            PRIMARY KEY (playlist_id, track_id),
            FOREIGN KEY (playlist_id) REFERENCES playlists(id),
            FOREIGN KEY (track_id) REFERENCES tracks(id)
        )
    """)

    conn.commit()
    conn.close()


class MusicPlatform:
    """Music platform backend."""

    def __init__(self):
        """Initialize the music platform."""
        init_db()

    def upload_track(
        self, title: str, artist: str, album: str, genre: str, duration_s: int, file_path: str = ""
    ) -> str:
        """Upload a track.
        
        Args:
            title: Track title
            artist: Artist name
            album: Album name
            genre: Genre
            duration_s: Duration in seconds
            file_path: Optional file path
            
        Returns:
            Track ID
        """
        track_id = f"track_{int(datetime.utcnow().timestamp())}"
        uploaded_at = datetime.utcnow().isoformat()

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()
        cursor.execute("""
            INSERT INTO tracks (id, title, artist, album, genre, duration_s, file_path, uploaded_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
        """, (track_id, title, artist, album, genre, duration_s, file_path, uploaded_at))
        conn.commit()
        conn.close()

        return track_id

    def play_track(self, track_id: str, user_id: str) -> bool:
        """Play a track and log history.
        
        Args:
            track_id: Track ID
            user_id: User ID
            
        Returns:
            True if successful
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Add to play history
        cursor.execute("""
            INSERT INTO play_history (track_id, user_id, played_at)
            VALUES (?, ?, ?)
        """, (track_id, user_id, datetime.utcnow().isoformat()))

        # Increment play count
        cursor.execute("""
            UPDATE tracks SET plays = plays + 1 WHERE id = ?
        """, (track_id,))

        conn.commit()
        conn.close()
        return True

    def like_track(self, track_id: str, user_id: str) -> bool:
        """Like a track.
        
        Args:
            track_id: Track ID
            user_id: User ID
            
        Returns:
            True if successful
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT OR IGNORE INTO likes (track_id, user_id, liked_at)
            VALUES (?, ?, ?)
        """, (track_id, user_id, datetime.utcnow().isoformat()))

        # Update like count
        cursor.execute("""
            UPDATE tracks SET likes = (
                SELECT COUNT(*) FROM likes WHERE track_id = ?
            ) WHERE id = ?
        """, (track_id, track_id))

        conn.commit()
        conn.close()
        return True

    def search(self, query: str, genre: Optional[str] = None) -> List[dict]:
        """Search tracks by title, artist, or album.
        
        Args:
            query: Search query
            genre: Optional genre filter
            
        Returns:
            List of matching track dicts
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        search_pattern = f"%{query}%"
        if genre:
            cursor.execute("""
                SELECT * FROM tracks
                WHERE (title LIKE ? OR artist LIKE ? OR album LIKE ?)
                AND genre = ?
                ORDER BY plays DESC
            """, (search_pattern, search_pattern, search_pattern, genre))
        else:
            cursor.execute("""
                SELECT * FROM tracks
                WHERE title LIKE ? OR artist LIKE ? OR album LIKE ?
                ORDER BY plays DESC
            """, (search_pattern, search_pattern, search_pattern))

        cols = [description[0] for description in cursor.description]
        tracks = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()
        return tracks

    def get_trending(self, genre: Optional[str] = None, n: int = 10) -> List[dict]:
        """Get trending tracks by play count in last 7 days.
        
        Args:
            genre: Optional genre filter
            n: Number of tracks to return
            
        Returns:
            List of trending track dicts
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        week_ago = (datetime.utcnow() - timedelta(days=7)).isoformat()

        if genre:
            cursor.execute("""
                SELECT t.* FROM tracks t
                WHERE t.genre = ?
                AND EXISTS (
                    SELECT 1 FROM play_history ph
                    WHERE ph.track_id = t.id AND ph.played_at > ?
                )
                ORDER BY t.plays DESC
                LIMIT ?
            """, (genre, week_ago, n))
        else:
            cursor.execute("""
                SELECT t.* FROM tracks t
                WHERE EXISTS (
                    SELECT 1 FROM play_history ph
                    WHERE ph.track_id = t.id AND ph.played_at > ?
                )
                ORDER BY t.plays DESC
                LIMIT ?
            """, (week_ago, n))

        cols = [description[0] for description in cursor.description]
        tracks = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()
        return tracks

    def get_recommendations(self, user_id: str, n: int = 5) -> List[dict]:
        """Get recommendations based on listening history genre weights.
        
        Args:
            user_id: User ID
            n: Number of recommendations
            
        Returns:
            List of recommended track dicts
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Get user's genre preferences
        cursor.execute("""
            SELECT t.genre, COUNT(*) as count
            FROM play_history ph
            JOIN tracks t ON ph.track_id = t.id
            WHERE ph.user_id = ?
            GROUP BY t.genre
            ORDER BY count DESC
            LIMIT 3
        """, (user_id,))

        genres = [row[0] for row in cursor.fetchall()]

        if not genres:
            # If no history, recommend trending tracks
            cursor.execute("""
                SELECT * FROM tracks
                ORDER BY plays DESC
                LIMIT ?
            """, (n,))
        else:
            # Get tracks in favorite genres not yet played by user
            placeholders = ",".join("?" * len(genres))
            cursor.execute(f"""
                SELECT DISTINCT t.* FROM tracks t
                WHERE t.genre IN ({placeholders})
                AND t.id NOT IN (
                    SELECT track_id FROM play_history WHERE user_id = ?
                )
                ORDER BY t.plays DESC
                LIMIT ?
            """, (*genres, user_id, n))

        cols = [description[0] for description in cursor.description]
        tracks = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()
        return tracks

    def create_playlist(self, user_id: str, name: str, track_ids: List[str] = []) -> str:
        """Create a playlist.
        
        Args:
            user_id: User ID
            name: Playlist name
            track_ids: Optional list of track IDs to add
            
        Returns:
            Playlist ID
        """
        playlist_id = f"playlist_{int(datetime.utcnow().timestamp())}"
        created_at = datetime.utcnow().isoformat()

        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            INSERT INTO playlists (id, user_id, name, created_at)
            VALUES (?, ?, ?, ?)
        """, (playlist_id, user_id, name, created_at))

        # Add tracks if provided
        for track_id in track_ids:
            cursor.execute("""
                INSERT INTO playlist_tracks (playlist_id, track_id, added_at)
                VALUES (?, ?, ?)
            """, (playlist_id, track_id, created_at))

        conn.commit()
        conn.close()
        return playlist_id

    def get_playlist(self, playlist_id: str) -> Dict:
        """Get playlist details.
        
        Args:
            playlist_id: Playlist ID
            
        Returns:
            Playlist dict with tracks
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        cursor.execute("""
            SELECT id, user_id, name, created_at FROM playlists WHERE id = ?
        """, (playlist_id,))

        playlist_row = cursor.fetchone()
        if not playlist_row:
            return {}

        playlist_id, user_id, name, created_at = playlist_row

        cursor.execute("""
            SELECT t.* FROM tracks t
            JOIN playlist_tracks pt ON t.id = pt.track_id
            WHERE pt.playlist_id = ?
            ORDER BY pt.added_at
        """, (playlist_id,))

        cols = [description[0] for description in cursor.description]
        tracks = [dict(zip(cols, row)) for row in cursor.fetchall()]
        conn.close()

        return {
            "id": playlist_id,
            "user_id": user_id,
            "name": name,
            "created_at": created_at,
            "tracks": tracks,
        }

    def get_user_stats(self, user_id: str) -> Dict:
        """Get user statistics.
        
        Args:
            user_id: User ID
            
        Returns:
            Stats dict with total plays, fav genres, top artists
        """
        conn = sqlite3.connect(DB_PATH)
        cursor = conn.cursor()

        # Total plays
        cursor.execute("""
            SELECT COUNT(*) FROM play_history WHERE user_id = ?
        """, (user_id,))
        total_plays = cursor.fetchone()[0]

        # Favorite genres
        cursor.execute("""
            SELECT t.genre, COUNT(*) as count
            FROM play_history ph
            JOIN tracks t ON ph.track_id = t.id
            WHERE ph.user_id = ?
            GROUP BY t.genre
            ORDER BY count DESC
            LIMIT 3
        """, (user_id,))
        fav_genres = [row[0] for row in cursor.fetchall()]

        # Top artists
        cursor.execute("""
            SELECT t.artist, COUNT(*) as count
            FROM play_history ph
            JOIN tracks t ON ph.track_id = t.id
            WHERE ph.user_id = ?
            GROUP BY t.artist
            ORDER BY count DESC
            LIMIT 5
        """, (user_id,))
        top_artists = [row[0] for row in cursor.fetchall()]

        conn.close()

        return {
            "total_plays": total_plays,
            "favorite_genres": fav_genres,
            "top_artists": top_artists,
        }


def main():
    """CLI interface for music platform."""
    parser = argparse.ArgumentParser(description="BlackRoad Music Platform")
    subparsers = parser.add_subparsers(dest="command", help="Command")

    # trending command
    trending_parser = subparsers.add_parser("trending", help="Get trending tracks")
    trending_parser.add_argument("--genre", default=None, help="Optional genre filter")
    trending_parser.add_argument("--count", type=int, default=10, help="Number of tracks")

    # search command
    search_parser = subparsers.add_parser("search", help="Search tracks")
    search_parser.add_argument("query", help="Search query")
    search_parser.add_argument("--genre", default=None, help="Optional genre filter")

    # stats command
    stats_parser = subparsers.add_parser("stats", help="Get user statistics")
    stats_parser.add_argument("user_id", help="User ID")

    args = parser.parse_args()
    platform = MusicPlatform()

    if args.command == "trending":
        tracks = platform.get_trending(args.genre, args.count)
        print(json.dumps(tracks, indent=2))
    elif args.command == "search":
        tracks = platform.search(args.query, args.genre)
        print(json.dumps(tracks, indent=2))
    elif args.command == "stats":
        stats = platform.get_user_stats(args.user_id)
        print(json.dumps(stats, indent=2))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
