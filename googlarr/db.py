import sqlite3
import os
from pathlib import Path


def init_db(db_path):
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    with sqlite3.connect(db_path) as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS library_items (
                item_id TEXT,
                title TEXT,
                library TEXT,
                kind TEXT DEFAULT 'poster',
                original_path TEXT,
                prank_path TEXT,
                status TEXT,
                PRIMARY KEY (item_id, kind)
            )
        """)
        # Add remote_signature column if it doesn't exist (simple migration)
        try:
            conn.execute("ALTER TABLE library_items ADD COLUMN remote_signature TEXT")
        except sqlite3.OperationalError:
            # Column likely already exists
            pass
        conn.commit()


def reset_working_tasks(db_path):
    with sqlite3.connect(db_path) as conn:
        conn.execute("UPDATE library_items SET status = 'NEW' WHERE status = 'WORKING_DOWNLOAD'")
        conn.execute("UPDATE library_items SET status = 'ORIGINAL_DOWNLOADED' WHERE status = 'WORKING_PRANKIFY'")
        conn.commit()


def sync_library_with_plex(config, plex):

    poster_originals_dir = config['paths']['originals_dir']
    poster_prank_dir = config['paths']['prank_dir']
    bg_originals_dir = config['paths'].get('backgrounds_originals_dir', 'data/backgrounds/originals')
    bg_prank_dir = config['paths'].get('backgrounds_prank_dir', 'data/backgrounds/prank')

    for lib_name in config['plex']['libraries']:
        print(f"[SYNC] Syncing library: {lib_name}")
        library = plex.library.section(lib_name)

        with sqlite3.connect(config['database']) as conn:
            conn.row_factory = sqlite3.Row
            c = conn.cursor()

            def upsert_item(item_id, title, lib_name, kind, original_path, prank_path, signature):
                # Insert if missing, including remote_signature
                c.execute(
                    "INSERT OR IGNORE INTO library_items (item_id, title, library, kind, original_path, prank_path, status, remote_signature) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                    (
                        item_id,
                        title,
                        lib_name,
                        kind,
                        original_path,
                        prank_path,
                        'NEW',
                        signature,
                    )
                )
                # Check existing row
                c.execute("SELECT status, remote_signature, original_path, prank_path FROM library_items WHERE item_id = ? AND kind = ?", (item_id, kind))
                row = c.fetchone()
                if not row:
                    return
                existing_sig = row["remote_signature"]
                if existing_sig != signature:
                    # Only consider artwork change if prank is NOT currently applied
                    if row["status"] == 'PRANK_APPLIED':
                        print(f"[SYNC] Artwork change detected for {title} ({kind}) but prank is applied; deferring until restore.")
                        return
                    # Detected artwork change — reset to NEW, update signature, remove cached files
                    print(f"[SYNC] Detected artwork change for {title} ({kind}). Re-queuing for re-prank.")
                    # Remove cached files if any
                    try:
                        if row["original_path"] and os.path.exists(row["original_path"]):
                            os.remove(row["original_path"])
                    except Exception:
                        pass
                    try:
                        if row["prank_path"] and os.path.exists(row["prank_path"]):
                            os.remove(row["prank_path"])
                    except Exception:
                        pass
                    c.execute("UPDATE library_items SET status = 'NEW', remote_signature = ?, title = ?, library = ?, original_path = ?, prank_path = ? WHERE item_id = ? AND kind = ?",
                              (signature, title, lib_name, original_path, prank_path, item_id, kind))

            for item in library.all():
                item_id = str(item.ratingKey)
                title = item.title

                # Posters
                poster_sig = getattr(item, 'thumb', None)
                upsert_item(
                    item_id,
                    title,
                    lib_name,
                    'poster',
                    f"{poster_originals_dir}/{item_id}.jpg",
                    f"{poster_prank_dir}/{item_id}.jpg",
                    poster_sig,
                )

                # Backgrounds (art)
                art = getattr(item, 'art', None)
                if art:
                    upsert_item(
                        item_id,
                        title,
                        lib_name,
                        'background',
                        f"{bg_originals_dir}/{item_id}.jpg",
                        f"{bg_prank_dir}/{item_id}.jpg",
                        art,
                    )
                else:
                    print(f"[SYNC] Skipping background for {title}: No art")

                # Seasons
                if hasattr(item, 'seasons'):
                    for season in item.seasons():
                        season_id = str(season.ratingKey)
                        season_title = f"{item.title} - {season.title}"

                        # Poster for season
                        if not season.thumb:
                            print(f"[SYNC] Skipping season poster {season_title}: No poster")
                        else:
                            season_poster_sig = getattr(season, 'thumb', None)
                            upsert_item(
                                season_id,
                                season_title,
                                lib_name,
                                'poster',
                                f"{poster_originals_dir}/{season_id}.jpg",
                                f"{poster_prank_dir}/{season_id}.jpg",
                                season_poster_sig,
                            )
                        # Background for season (art)
                        season_art = getattr(season, 'art', None)
                        show_art = getattr(item, 'art', None)
                        if season_art and season_art != show_art:
                            upsert_item(
                                season_id,
                                season_title,
                                lib_name,
                                'background',
                                f"{bg_originals_dir}/{season_id}.jpg",
                                f"{bg_prank_dir}/{season_id}.jpg",
                                season_art,
                            )
                        else:
                            reason = "No art" if not season_art else "Inherited show art; skipping duplicate"
                            print(f"[SYNC] Skipping season background {season_title}: {reason}")

            conn.commit()


def claim_next_task(db_path, kind):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()

        # Try to claim a NEW item for downloading
        c.execute("""
            UPDATE library_items
            SET status = 'WORKING_DOWNLOAD'
            WHERE (item_id, kind) = (
                SELECT item_id, kind FROM library_items
                WHERE status = 'NEW' AND kind = ?
                LIMIT 1
            )
            RETURNING *
        """, (kind,))
        row = c.fetchone()
        if row:
            return dict(row)

        # Try to claim an ORIGINAL_DOWNLOADED item for prankifying
        c.execute("""
            UPDATE library_items
            SET status = 'WORKING_PRANKIFY'
            WHERE (item_id, kind) = (
                SELECT item_id, kind FROM library_items
                WHERE status = 'ORIGINAL_DOWNLOADED' AND kind = ?
                LIMIT 1
            )
            RETURNING *
        """, (kind,))
        row = c.fetchone()
        return dict(row) if row else None


def update_item_status(db_path, item_id, kind, new_status):
    with sqlite3.connect(db_path) as conn:
        c = conn.cursor()
        c.execute("UPDATE library_items SET status = ? WHERE item_id = ? AND kind = ?", (new_status, item_id, kind))
        conn.commit()


def get_items_for_update(db_path, kind):
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        c = conn.cursor()
        c.execute("SELECT * FROM library_items WHERE status IN ('PRANK_GENERATED', 'PRANK_APPLIED') AND kind = ?", (kind,))
        return [dict(row) for row in c.fetchall()]

