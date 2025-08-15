import os
import cv2
import requests
from googlarr.detector import FaceDetector
from googlarr.overlay import process_image

overlay_img = None
face_detector = None


def initialize_detector_and_overlay(config):
    global face_detector, overlay_img
    face_detector = FaceDetector(config)
    overlay_img = cv2.imread("assets/eye.png", cv2.IMREAD_UNCHANGED)


def download_poster(plex, item, save_path, config):
    plex_item = plex.fetchItem(int(item['item_id']))
    url = plex_item.thumbUrl
    headers = {'Accept': 'image/jpeg'}
    response = requests.get(url, headers=headers, stream=True)
    if response.status_code == 200:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)  # Ensure directory exists
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)

def download_background(plex, item, save_path, config):
    plex_item = plex.fetchItem(int(item['item_id']))
    # Use artUrl if available
    url = getattr(plex_item, 'artUrl', None)
    if not url:
        return
    headers = {'Accept': 'image/jpeg'}
    response = requests.get(url, headers=headers, stream=True)
    if response.status_code == 200:
        os.makedirs(os.path.dirname(save_path), exist_ok=True)
        with open(save_path, 'wb') as f:
            for chunk in response.iter_content(1024):
                f.write(chunk)

def generate_prank_poster(original_path, prank_path, config):

    global face_detector, overlay_img

    img_bgr = cv2.imread(original_path)
    if img_bgr is None:
        print(f"[PRANK] Failed to read image: {original_path}")
        return

    # Detect eyes using face detector
    eye_locations = face_detector.detect_eyes(img_bgr, config['detection'])
    if not eye_locations:
        print(f"[PRANK] No eyes detected in {original_path}")
        return

    img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)

    # Apply googly eyes
    try:
        prank_img_rgb = process_image(
            base_image=img_rgb,
            overlay_image=overlay_img,
            eye_locations=eye_locations,
            config=config['detection']
        )
    except Exception as e:
        print(f"[PRANK] Error applying googly eyes: {e}")
        return

    # Convert and save
    prank_img_bgr = cv2.cvtColor(prank_img_rgb, cv2.COLOR_RGB2BGR)
    os.makedirs(os.path.dirname(prank_path), exist_ok=True)
    cv2.imwrite(prank_path, prank_img_bgr)
    print(f"[PRANK] Wrote prankified poster to {prank_path}")


def set_poster(plex_item, image_path):
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Poster image not found: {image_path}")

    plex_item.uploadPoster(filepath=str(image_path))


def set_background(plex_item, image_path):
    if not os.path.exists(image_path):
        raise FileNotFoundError(f"Background image not found: {image_path}")

    # PlexAPI supports uploading background art via uploadArt
    plex_item.uploadArt(filepath=str(image_path))


def refresh_artwork(plex_item):
    """
    Ask Plex to refresh metadata/artwork for the item. This avoids using any local files
    and lets Plex/agents select artwork again.
    """
    try:
        # Force agent refresh; Plex will re-query providers and may change posters/backgrounds
        plex_item.refresh(force=True)
    except Exception as e:
        print(f"[PRANK] Failed to refresh artwork: {e}")


def clear_artwork(plex_item, kind: str):
    """
    Clear current artwork so Plex can choose defaults again.
    Calls the PlexAPI methods directly for the known environment and falls back to a refresh on error.
    """
    try:
        if kind == 'poster':
            plex_item.editPoster(None)
        else:
            plex_item.editArt(None)

        # After edit, attempt to reload/refresh metadata to apply
        try:
            plex_item.reload()
        except Exception:
            pass
        try:
            plex_item.refresh()
        except Exception:
            pass
    except Exception as e:
        print(f"[PRANK] Failed to clear artwork ({kind}): {e}. Falling back to refresh.")
        return refresh_artwork(plex_item)

