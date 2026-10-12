"""Screen OCR and screenshot capture in macOS logical points."""

from __future__ import annotations

import re
import time
from pathlib import Path

import cv2
import numpy as np
import pyautogui
import pytesseract
from pytesseract import Output

pyautogui.FAILSAFE = True
pyautogui.PAUSE = 0.12

SHOTS = Path(__file__).resolve().parents[1] / "docs" / "screenshots"


def norm(text: str) -> str:
    return re.sub(r"\s+", " ", str(text)).strip().casefold().rstrip(":")


def geometry():
    shot = pyautogui.screenshot()
    screen_w, screen_h = pyautogui.size()
    return shot, screen_w / shot.width, screen_h / shot.height


def tokens() -> list[dict]:
    """Single OCR tokens in the same coordinate space as pyautogui."""
    shot, scale_x, scale_y = geometry()
    image = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    scaled = cv2.resize(image, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    data = pytesseract.image_to_data(scaled, config="--psm 11", output_type=Output.DICT)
    found = []
    for i, raw in enumerate(data["text"]):
        text = str(raw).strip()
        if not text:
            continue
        left = data["left"][i] / 2 * scale_x
        top = data["top"][i] / 2 * scale_y
        width = data["width"][i] / 2 * scale_x
        height = data["height"][i] / 2 * scale_y
        found.append({
            "text": text,
            "x": left,
            "y": top,
            "right": left + width,
            "bottom": top + height,
            "conf": float(data["conf"][i]),
        })
    return found


def lines() -> list[dict]:
    """Tokens joined into visual lines."""
    groups: dict[tuple, list] = {}
    for token in tokens():
        key = round(token["y"] / 8)
        groups.setdefault(key, []).append(token)
    rows = []
    for group in groups.values():
        group.sort(key=lambda token: token["x"])
        # Split a visual row when a large horizontal gap separates regions.
        chunks: list[list] = [[group[0]]]
        for token in group[1:]:
            if token["x"] - chunks[-1][-1]["right"] > 28:
                chunks.append([token])
            else:
                chunks[-1].append(token)
        for chunk in chunks:
            rows.append({
                "text": " ".join(token["text"] for token in chunk),
                "x": min(token["x"] for token in chunk),
                "y": min(token["y"] for token in chunk),
                "right": max(token["right"] for token in chunk),
                "bottom": max(token["bottom"] for token in chunk),
                "tokens": chunk,
            })
    rows.sort(key=lambda row: (row["y"], row["x"]))
    return rows


def find_lines(text: str, exact: bool = True, region=None) -> list[dict]:
    wanted = norm(text)
    found = []
    for row in lines():
        if region and not region(row):
            continue
        haystack = norm(row["text"])
        if (haystack == wanted) if exact else (wanted in haystack):
            found.append(row)
    return found


def line_starting(text: str, region=None) -> dict:
    """A visual line whose text starts with the label, so 'No PO000001' matches 'No'."""
    wanted = norm(text)
    found = []
    for row in lines():
        if region and not region(row):
            continue
        haystack = norm(row["text"])
        if haystack == wanted or haystack.startswith(wanted + " ") or haystack.startswith(wanted + "."):
            found.append(row)
    if len(found) != 1:
        sample = [row["text"] for row in found[:8]]
        raise RuntimeError(f"Expected one line starting with {text!r}, found {len(found)}: {sample}")
    return found[0]


def unique_line(text: str, exact: bool = True, region=None) -> dict:
    found = find_lines(text, exact=exact, region=region)
    if len(found) != 1:
        sample = [row["text"] for row in found[:8]]
        raise RuntimeError(f"Expected one visible {text!r}, found {len(found)}: {sample}")
    return found[0]


def _label_anchor_once(text: str, region=None) -> dict:
    """The label's own end, even when OCR joins it to the value on the same line.

    ``right`` is the end of the label, not the end of the value after it.
    """
    wanted = norm(text).split()
    found = []
    for row in lines():
        if region and not region(row):
            continue
        parts = [norm(token["text"]) for token in row["tokens"]]
        if parts[: len(wanted)] != wanted:
            continue
        last = row["tokens"][len(wanted) - 1]
        found.append({
            **row,
            "x": row["tokens"][0]["x"],
            "right": last["right"],
            "label_right": last["right"],
        })
    if len(found) != 1:
        sample = [row["text"] for row in found[:8]]
        raise RuntimeError(f"Expected one label {text!r}, found {len(found)}: {sample}")
    return found[0]


def label_anchor(text: str, region=None) -> dict:
    """Find a label. A single empty OCR pass is read again before giving up."""
    try:
        return _label_anchor_once(text, region)
    except RuntimeError as exc:
        if "found 0" not in str(exc):
            raise
        time.sleep(0.45)
        return _label_anchor_once(text, region)


def white_field_on_row(anchor: dict) -> dict:
    """The white input on the same row as a label, in logical points.

    SWT often leaves the focused control elsewhere, so the field is found
    from its pixels rather than from the focused element.
    """
    shot, scale_x, scale_y = geometry()
    array = np.array(shot.convert("RGB"))
    y = (anchor["y"] + anchor["bottom"]) / 2
    pixel_y = int(y / scale_y)
    if pixel_y < 0 or pixel_y >= array.shape[0]:
        raise RuntimeError(f"Label {anchor['text']!r} is off the screen")
    white = np.all(array[pixel_y] > 245, axis=1)
    start_at = int((anchor["label_right"] + 6) / scale_x)
    run_start = None
    best = None
    for index in range(start_at, white.shape[0]):
        if white[index] and run_start is None:
            run_start = index
        elif not white[index] and run_start is not None:
            if index - run_start > 24 and best is None:
                best = (run_start, index)
                break
            run_start = None
    if best is None and run_start is not None and white.shape[0] - run_start > 24:
        best = (run_start, white.shape[0] - 1)
    if best is None:
        raise RuntimeError(f"No input field on the {anchor['text']!r} row")
    left, right = best
    return {
        "x": left * scale_x,
        "right": right * scale_x,
        "y": anchor["y"],
        "bottom": anchor["bottom"],
    }


def click_line(row: dict) -> None:
    pyautogui.click((row["x"] + row["right"]) / 2, (row["y"] + row["bottom"]) / 2)
    time.sleep(0.3)


def visible_text() -> str:
    return " ".join(norm(row["text"]) for row in lines())


def capture(name: str, note: str = "") -> Path:
    """Save a screenshot. The note is burned into the top bar so the set is annotated."""
    SHOTS.mkdir(parents=True, exist_ok=True)
    shot = pyautogui.screenshot()
    image = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    if note:
        bar = np.full((36, image.shape[1], 3), 32, dtype=np.uint8)
        cv2.putText(
            bar, note[:140], (12, 24), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1, cv2.LINE_AA,
        )
        image = np.vstack([bar, image])
    path = SHOTS / f"{name}.png"
    cv2.imwrite(str(path), image)
    print(f"screenshot: {path.name} — {note}", flush=True)
    return path


def match_template(template_path: Path, threshold: float = 0.72) -> list[tuple[float, float, float]]:
    """Return (x, y, score) centers of template matches, in logical points."""
    shot, scale_x, scale_y = geometry()
    screen = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)
    templ = cv2.imread(str(template_path))
    if templ is None:
        raise RuntimeError(f"Template missing: {template_path}")
    # Screenshot pixels and the template are both in device pixels.
    result = cv2.matchTemplate(screen, templ, cv2.TM_CCOEFF_NORMED)
    locations = np.where(result >= threshold)
    hits = []
    height, width = templ.shape[:2]
    for py, px in zip(*locations):
        score = float(result[py, px])
        hits.append(((px + width / 2) * scale_x, (py + height / 2) * scale_y, score))
    hits.sort(key=lambda item: -item[2])
    # Collapse neighbors of the same icon.
    unique = []
    for hit in hits:
        if all(abs(hit[0] - kept[0]) > 12 or abs(hit[1] - kept[1]) > 12 for kept in unique):
            unique.append(hit)
    return unique


def green_plus_buttons(x_min_ratio=0.0, y_min_ratio=0.0, x_max_ratio=1.0, y_max_ratio=1.0):
    """Centers of small green circular '+' controls, in logical points."""
    shot, scale_x, scale_y = geometry()
    array = np.array(shot.convert("RGB"))
    height, width = array.shape[:2]
    x0, x1 = int(width * x_min_ratio), int(width * x_max_ratio)
    y0, y1 = int(height * y_min_ratio), int(height * y_max_ratio)
    roi = array[y0:y1, x0:x1]
    hsv = cv2.cvtColor(roi, cv2.COLOR_RGB2HSV)
    mask = cv2.inRange(hsv, np.array([30, 40, 40]), np.array([100, 255, 255]))
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    found = []
    for contour in contours:
        x, y, w, h = cv2.boundingRect(contour)
        if 6 <= w <= 48 and 6 <= h <= 48 and 0.6 <= w / h <= 1.6:
            found.append(((x0 + x + w / 2) * scale_x, (y0 + y + h / 2) * scale_y, w * h))
    return found
