# Googlarr

> A chaotic and deeply unnecessary tool that applies googly eyes to your Plex posters on a schedule.  
> You were warned.

---

## WARNING — THIS PROJECT MAY RUIN YOUR POSTERS

Googlarr uses the Plex API to modify the posters for your Plex media items **in place**. It tries to save and restore the originals, but:

- It might miss a poster
- It might fail to restore properly
- Plex might cache something weird
- You might regret everything

**Use at your own risk. This project is for prank purposes only. I cannot provide support in case of failure.**

I highly recommend testing this on a dummy library in Plex before rolling it out for real. Create a new minimal library with just a handful of media items, and set that up in the config. Set up a very brief cron window to test it (e.g. starting at 10am today, and ending at 10.15am), to ensure that paths etc. are set up properly and poster restore works properly at the end of the time.

![image](https://github.com/user-attachments/assets/b9b659b5-9339-49db-8836-d0eb18624c7a)

---

## What It Does

Googlarr is a scheduled prank daemon that:

1. Scans your Plex libraries for movies and/or shows
2. Detects faces and eye positions in poster and background (art) images
3. Applies googly eyes using image overlays
4. Swaps the posters and backgrounds on a cron-based schedule
5. Restores the originals after the prank window

---

## Setup

1. Clone this repository locally
2. Configure your `config.yml`
3. `./build.sh`
4. `./run.sh`
5. Pray

---

## Docker Compose

1. Clone this repository locally
2. Set up your Docker Compose (see included `docker-compose.yml`)
3. Configure your `config.yml`
4. `docker compose build googlarr`
5. `docker compose up -d`
6. Cross your fingers

### Resetting the prank (let Plex re-fetch artwork and wipe cache)

If you want to immediately stop the prank and allow Plex to re-select posters and backgrounds from its metadata agents (without using any local original images) — and wipe the local prank image cache so it will be re-generated next time — run the reset command via Docker Compose:

```
docker compose run --rm googlarr python -m googlarr.reset
```

What this does:
- Triggers a Plex metadata refresh for each item so Plex’s agents re-fetch/select posters and backgrounds. No local original images are uploaded.
- Clears the local prank cache folders (`data/posters/prank` and `data/backgrounds/prank`) so images are regenerated on the next run.
- Resets internal state so items are ready to be prankified again when the schedule triggers.

Note: Artwork changes are subject to your Plex agent settings; if artwork fields are locked in Plex, you may need to unlock them for agents to update on refresh.

---

## Setup details

The script works by kicking off a number of workers. First it will sync poster info to a small database, and then download all the relevant posters. It took my low powered server about 30 minutes to process about 5000 items, with a poster success rate of about 75%. (Some posters don't have any faces, some detection just fails).

Based on the cron schedule in the config file, it will "sleep" a worker to start at that schedule time, at which point it will wake up and switch out all your posters.

To that end, I recommend setting the "start" schedule time to an hour or two in the future, then starting the container. That will give it time to process all the posters before switching them out.

---

## Example Config

```yaml
plex:
  url: http://your.plex.server:32400
  token: your_plex_token
  libraries:
    - Movies
    - TV Shows

paths:
  originals_dir: data/posters/originals
  prank_dir: data/posters/prank
  backgrounds_originals_dir: data/backgrounds/originals
  backgrounds_prank_dir: data/backgrounds/prank

database: "data/googlarr.db"

schedule:
  on: "0 9 * * *"    # Apply prank at 9am daily
  off: "0 17 * * *"  # Restore at 5pm daily

detection:
  face_detection_confidence: 0.5
  landmark_detection_confidence: 0.5
  scale_by_face_size: true
  face_based_eye_scale: 0.35
  use_same_size_for_both_eyes: true
  debug_draw_faces: false
```

## Development

Portions of this project were created with ChatGPT code generation. I am a veteran software engineer however, and have code inspected the output and run extensive testing on multiple libraries.

## License
MIT. See `LICENSE`.

Portions of `overlay.py` and `detector.py` were adapted from MIT-licensed sources. See `LICENSES/` for attribution.
