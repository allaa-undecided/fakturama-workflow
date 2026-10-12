"""The add-address plus sits a few dozen points from the screen edge."""

from pathlib import Path

import numpy as np
from PIL import Image

from fakturama_auto.steps.debtor import _add_address_plus

SHOT = Path(__file__).resolve().parents[1] / "docs" / "screenshots" / "05-main-address.png"


def test_plus_is_the_glyph_at_the_right_end_of_the_tab():
    image = np.array(Image.open(SHOT).convert("RGB"))
    # Retina capture of a 1920-point screen. The words "Main address" end near
    # pixel 1506, and the plus glyph is the dark mark around pixel 3704.
    scale = 1920 / image.shape[1]
    tab = {
        "y": 1111 * scale,
        "bottom": 1128 * scale,
        "label_right": 1506 * scale,
    }
    click_x, click_y = _add_address_plus(image, scale, scale, tab, 1920)
    assert 1835 < click_x < 1870
    assert 545 < click_y < 575
