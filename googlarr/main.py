import traceback
import asyncio
import os
import time
from datetime import datetime, timedelta
from croniter import croniter

from plexapi.server import PlexServer
from googlarr.config import load_config
from googlarr.db import (
    init_db,
    sync_library_with_plex,
    claim_next_task,
    update_item_status,
    get_items_for_update,
    reset_working_tasks
)
from googlarr.prank import download_poster, download_background, generate_prank_poster, set_poster, set_background, initialize_detector_and_overlay

# --- CONFIG ---
SYNC_INTERVAL_MINUTES = 60
POSTER_WORKERS = 1
BACKGROUND_WORKERS = 1


async def sync_task(config, plex):
    while True:
        print("[SYNC] Syncing library with Plex...")
        sync_library_with_plex(config, plex)
        await asyncio.sleep(SYNC_INTERVAL_MINUTES * 60)


async def poster_worker(worker_id, config, plex):
    kind = 'poster'
    while True:
        item = claim_next_task(config['database'], kind)

        if not item:
            print(f"[POSTER-{worker_id}] Sleeping...")
            await asyncio.sleep(360)
            continue

        print(f"[POSTER-{worker_id}] Working on item {item['title']} ({item['status']})")

        try:
            if item['status'] == 'WORKING_DOWNLOAD':
                await asyncio.to_thread(download_poster, plex, item, item['original_path'], config)
                update_item_status(config['database'], item['item_id'], kind, 'ORIGINAL_DOWNLOADED')

            elif item['status'] == 'WORKING_PRANKIFY':
                await asyncio.to_thread(generate_prank_poster, item['original_path'], item['prank_path'], config)
                update_item_status(config['database'], item['item_id'], kind, 'PRANK_GENERATED')

        except Exception as e:
            tb = traceback.format_exc()
            print(f"[POSTER-{worker_id}] Error processing {item['title']}: {e.__class__.__name__}: {e}")
            print(tb)

            update_item_status(config['database'], item['item_id'], kind, 'FAILED')


async def background_worker(worker_id, config, plex):
    kind = 'background'
    while True:
        item = claim_next_task(config['database'], kind)

        if not item:
            print(f"[BG-{worker_id}] Sleeping...")
            await asyncio.sleep(360)
            continue

        print(f"[BG-{worker_id}] Working on item {item['title']} ({item['status']})")

        try:
            if item['status'] == 'WORKING_DOWNLOAD':
                await asyncio.to_thread(download_background, plex, item, item['original_path'], config)
                update_item_status(config['database'], item['item_id'], kind, 'ORIGINAL_DOWNLOADED')

            elif item['status'] == 'WORKING_PRANKIFY':
                await asyncio.to_thread(generate_prank_poster, item['original_path'], item['prank_path'], config)
                update_item_status(config['database'], item['item_id'], kind, 'PRANK_GENERATED')

        except Exception as e:
            tb = traceback.format_exc()
            print(f"[BG-{worker_id}] Error processing {item['title']}: {e.__class__.__name__}: {e}")
            print(tb)

            update_item_status(config['database'], item['item_id'], kind, 'FAILED')


async def update_posters_task(config, plex):
    print("[UPDATE] Starting cron-driven poster/background updater")
    while True:
        now = datetime.now()

        cron_on = croniter(config['schedule']['start'], now)
        cron_off = croniter(config['schedule']['stop'], now)

        next_on = cron_on.get_next(datetime)
        next_off = cron_off.get_next(datetime)

        print(f"[UPDATE] Next on: {next_on}. Next off: {next_off}")

        # Decide which event is next
        if next_on < next_off:
            next_event = next_on
            action = "apply"
        else:
            next_event = next_off
            action = "restore"

        sleep_duration = (next_event - now).total_seconds()
        print(f"[UPDATE] Next action: {action.upper()} at {next_event}. Current time: {now}. Sleeping for {sleep_duration:.0f} seconds...")
        await asyncio.sleep(sleep_duration)

        # Do the update for posters and backgrounds
        for kind in ('poster', 'background'):
            items = get_items_for_update(config['database'], kind)
            for item in items:
                plex_item = plex.fetchItem(int(item['item_id']))

                try:
                    if action == "apply" and item['status'] == 'PRANK_GENERATED':
                        if kind == 'poster':
                            set_poster(plex_item, item['prank_path'])
                            print(f"[UPDATE] Applied prank poster to {item['title']}")
                        else:
                            set_background(plex_item, item['prank_path'])
                            print(f"[UPDATE] Applied prank background to {item['title']}")
                        update_item_status(config['database'], item['item_id'], kind, 'PRANK_APPLIED')

                    elif action == "restore" and item['status'] == 'PRANK_APPLIED':
                        if kind == 'poster':
                            set_poster(plex_item, item['original_path'])
                            print(f"[UPDATE] Restored original poster for {item['title']}")
                        else:
                            set_background(plex_item, item['original_path'])
                            print(f"[UPDATE] Restored original background for {item['title']}")
                        update_item_status(config['database'], item['item_id'], kind, 'PRANK_GENERATED')

                except Exception as e:
                    print(f"[UPDATE] Error updating {kind} for {item['title']}: {e}")



async def main():
    config = load_config()
    init_db(config['database'])
    reset_working_tasks(config['database'])
    initialize_detector_and_overlay(config['detection'])
    plex = PlexServer(config['plex']['url'], config['plex']['token'])

    await asyncio.gather(
        sync_task(config, plex),
        update_posters_task(config, plex),
        *[poster_worker(i, config, plex) for i in range(POSTER_WORKERS)],
        *[background_worker(i, config, plex) for i in range(BACKGROUND_WORKERS)]
    )


if __name__ == "__main__":
    asyncio.run(main())

