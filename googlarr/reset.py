import os
import sys
import sqlite3
import shutil
from plexapi.server import PlexServer
from googlarr.config import load_config
from googlarr.prank import refresh_artwork, clear_artwork


def _wipe_directory_contents(path: str):
    if not path:
        return
    if not os.path.exists(path):
        return
    for entry in os.listdir(path):
        full = os.path.join(path, entry)
        try:
            if os.path.isfile(full) or os.path.islink(full):
                os.remove(full)
            elif os.path.isdir(full):
                shutil.rmtree(full)
        except Exception as e:
            print(f"[RESET] Failed to remove {full}: {e}")


def main():
    """
    Reset all prank artwork back to the original in Plex and wipe local prank caches.

    Usage:
        python -m googlarr.reset
    """
    config = load_config()

    # Paths
    posters_prank = config['paths'].get('prank_dir', 'data/posters/prank')
    backgrounds_prank = config['paths'].get('backgrounds_prank_dir', 'data/backgrounds/prank')

    db_path = config['database']

    # Connect to Plex
    plex = PlexServer(config['plex']['url'], config['plex']['token'])

    # Process DB rows
    with sqlite3.connect(db_path) as conn:
        conn.row_factory = sqlite3.Row
        cur = conn.cursor()
        cur.execute("SELECT * FROM library_items")
        rows = [dict(r) for r in cur.fetchall()]

        refreshed = 0
        skipped = 0

        for row in rows:
            item_id = row['item_id']
            kind = row['kind']
            title = row.get('title') or item_id

            try:
                plex_item = plex.fetchItem(int(item_id))
            except Exception as e:
                print(f"[RESET] Could not fetch item {item_id} ({title}): {e}")
                skipped += 1
                continue

            # Do not rely on local originals. Ask Plex to clear metadata artwork then refresh.
            try:
                clear_artwork(plex_item, kind)
                refreshed += 1
                # Mark as NEW so the pipeline re-processes as needed on next cycles
                cur.execute(
                    "UPDATE library_items SET status = 'NEW' WHERE item_id = ? AND kind = ?",
                    (item_id, kind),
                )
            except Exception as e:
                print(f"[RESET] Failed to clear/refresh for {kind} on {title}: {e}")
                skipped += 1

        conn.commit()

    # Wipe prank caches
    print(f"[RESET] Wiping prank cache: {posters_prank}")
    _wipe_directory_contents(posters_prank)
    print(f"[RESET] Wiping prank cache: {backgrounds_prank}")
    _wipe_directory_contents(backgrounds_prank)

    print(f"[RESET] Completed. Refreshed: {refreshed}. Skipped: {skipped}.")


if __name__ == "__main__":
    main()
