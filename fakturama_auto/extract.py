"""Extract a structured order from a document image.

Tesseract word boxes are the source for parsing, because the item table is set
in gray type that line-level OCR drops. Apple Vision is run as a cross-check
on the reference, the dates and the totals. Parsing follows labels: a value is
the text sitting under a heading in the same column. Line math is checked
before anything is typed into Fakturama.
"""

from __future__ import annotations

import re
from decimal import Decimal, InvalidOperation
from pathlib import Path

from fakturama_auto.models import Address, Item, OrderData, money


def _tesseract_words(path: Path) -> list[dict]:
    import cv2
    import pytesseract
    from pytesseract import Output

    image = cv2.imread(str(path))
    if image is None:
        raise RuntimeError(f"Could not read image {path}")
    gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
    scaled = cv2.resize(gray, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)
    data = pytesseract.image_to_data(scaled, config="--psm 6", output_type=Output.DICT)
    words = []
    for i, raw in enumerate(data["text"]):
        text = str(raw).strip()
        if not text:
            continue
        words.append({
            "text": text,
            "x": data["left"][i] / 2,
            "y": data["top"][i] / 2,
            "right": (data["left"][i] + data["width"][i]) / 2,
            "bottom": (data["top"][i] + data["height"][i]) / 2,
        })
    words.sort(key=lambda word: (word["y"], word["x"]))
    return words


def _vision_text(path: Path) -> str:
    """All text Vision can read. Empty when Vision cannot open the image."""
    try:
        import Quartz
        import Vision
        from Foundation import NSURL
    except ImportError:
        return ""
    url = NSURL.fileURLWithPath_(str(path.resolve()))
    source = Quartz.CGImageSourceCreateWithURL(url, None)
    if source is None:
        return ""
    image = Quartz.CGImageSourceCreateImageAtIndex(source, 0, None)
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(1)
    request.setUsesLanguageCorrection_(False)
    handler = Vision.VNImageRequestHandler.alloc().initWithCGImage_options_(image, None)
    ok, _error = handler.performRequests_error_([request], None)
    if not ok:
        return ""
    return "\n".join(str(obs.topCandidates_(1)[0].string()) for obs in (request.results() or []))


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().casefold().rstrip(":.")


def _amount(text: str) -> Decimal:
    match = re.search(r"-?\d+(?:[.,]\d+)?", text.replace(" ", ""))
    if not match:
        raise ValueError(f"No amount in {text!r}")
    try:
        return money(match.group(0).replace(",", "."))
    except InvalidOperation as exc:
        raise ValueError(f"Bad amount {text!r}") from exc


def _percent(text: str) -> Decimal:
    match = re.search(r"(\d+(?:[.,]\d+)?)\s*%", text)
    if not match:
        raise ValueError(f"No percent in {text!r}")
    return Decimal(match.group(1).replace(",", "."))


def _find_phrase(words: list[dict], phrase: str) -> dict:
    """First left-to-right run of words equal to phrase, on one line."""
    parts = [_norm(part) for part in phrase.split()]
    for index, word in enumerate(words):
        if _norm(word["text"]) != parts[0]:
            continue
        matched = [word]
        cursor = index + 1
        ok = True
        for part in parts[1:]:
            followers = [
                candidate for candidate in words[cursor:cursor + 4]
                if abs(candidate["y"] - word["y"]) < 12 and candidate["x"] >= matched[-1]["x"]
            ]
            followers.sort(key=lambda candidate: candidate["x"])
            if not followers or _norm(followers[0]["text"]) != part:
                ok = False
                break
            matched.append(followers[0])
            cursor = words.index(followers[0]) + 1
        if ok:
            return {
                "text": " ".join(item["text"] for item in matched),
                "x": matched[0]["x"],
                "y": min(item["y"] for item in matched),
                "right": matched[-1]["right"],
                "bottom": max(item["bottom"] for item in matched),
            }
    raise ValueError(f"Label {phrase!r} was not found")


def _same_column(word: dict, anchor: dict, slack: float = 30) -> bool:
    return word["x"] >= anchor["x"] - 8 and word["x"] <= anchor["right"] + slack


def _line_under(words: list[dict], anchor: dict, stop_y: float, slack: float = 80) -> str:
    below = [
        word for word in words
        if anchor["bottom"] - 2 < word["y"] < min(anchor["bottom"] + 48, stop_y)
        and _same_column(word, anchor, slack)
    ]
    if not below:
        raise ValueError(f"No value under {anchor['text']!r}")
    below.sort(key=lambda word: (word["y"], word["x"]))
    first_y = below[0]["y"]
    line = [word for word in below if abs(word["y"] - first_y) < 10]
    line.sort(key=lambda word: word["x"])
    return " ".join(word["text"] for word in line)


def _block_under(words: list[dict], anchor: dict, stop_y: float, column_right: float) -> list[str]:
    below = [
        word for word in words
        if anchor["bottom"] - 2 < word["y"] < stop_y
        and anchor["x"] - 8 <= word["x"] < column_right
    ]
    below.sort(key=lambda word: (word["y"], word["x"]))
    lines: list[list[dict]] = []
    for word in below:
        if lines and abs(word["y"] - lines[-1][0]["y"]) < 10:
            lines[-1].append(word)
        else:
            lines.append([word])
    texts = []
    for line in lines:
        line.sort(key=lambda word: word["x"])
        text = " ".join(word["text"] for word in line).strip()
        if text:
            texts.append(text)
    return texts


def _address(lines: list[str], heading: str) -> Address:
    if len(lines) < 4:
        raise ValueError(f"{heading} block too short: {lines}")
    company, street, zip_city, country = lines[0], lines[1], lines[2], lines[3]
    match = re.match(r"(\d{4,6})\s+(.+)", zip_city)
    if not match:
        raise ValueError(f"{heading} ZIP/City not parsed from {zip_city!r}")
    return Address(
        company=company,
        street=street,
        zip_code=match.group(1),
        city=match.group(2).strip(),
        country=country,
    )


def _items(words: list[dict], top: float, bottom: float) -> list[Item]:
    band = [word for word in words if top < word["y"] < bottom]
    band.sort(key=lambda word: (word["y"], word["x"]))
    rows: list[list[dict]] = []
    for word in band:
        if rows and abs(word["y"] - rows[-1][0]["y"]) < 12:
            rows[-1].append(word)
        else:
            rows.append([word])
    items = []
    for row in rows:
        row.sort(key=lambda word: word["x"])
        tokens = [word["text"] for word in row]
        if not tokens or not re.fullmatch(r"\d{1,2}", tokens[0]):
            continue
        body = tokens[1:]
        if not body or not re.search(r"[A-Z]{2,}", body[0]):
            continue
        sku = body[0]
        rest = body[1:]
        # From the right: line net, VAT %, discount %, unit net, unit, quantity.
        try:
            line_net = _amount(rest[-1])
            vat = _percent(rest[-2])
            discount = _percent(rest[-3])
            unit_net = _amount(rest[-4])
            quantity = _amount(rest[-6])
        except (IndexError, ValueError) as exc:
            raise ValueError(f"Item row {tokens} could not be split: {exc}") from exc
        description = " ".join(rest[:-6]).strip()
        if not description:
            raise ValueError(f"Item {sku} has no description: {tokens}")
        items.append(Item(
            sku=sku,
            description=description,
            quantity=quantity,
            unit=rest[-5],
            unit_net=unit_net,
            discount_percent=discount,
            vat_percent=vat,
            line_net=line_net,
        ))
    if not items:
        raise ValueError("No item rows parsed")
    return items


def _split_contact(name: str) -> tuple[str, str]:
    parts = name.split()
    if len(parts) < 2:
        raise ValueError(f"Contact name needs a first and last name, got {name!r}")
    return parts[0], " ".join(parts[1:])


def _section_y(words: list[dict], heading: str) -> float:
    hits = [word for word in words if _norm(word["text"]) == _norm(heading) and word["x"] < 200]
    if not hits:
        raise ValueError(f"Section {heading!r} not found")
    return min(word["y"] for word in hits)


def parse_words(words: list[dict]) -> OrderData:
    addresses_y = _section_y(words, "ADDRESSES")
    payment_y = _section_y(words, "PAYMENT")
    items_y = _section_y(words, "ITEMS")
    net_label = _find_phrase(words, "NET TOTAL")

    reference = _line_under(words, _find_phrase(words, "EXTERNAL REFERENCE"), addresses_y)
    order_date = _line_under(words, _find_phrase(words, "ORDER DATE"), addresses_y)
    customer_id = _line_under(words, _find_phrase(words, "CUSTOMER ID"), addresses_y)
    currency = _line_under(words, _find_phrase(words, "CURRENCY"), addresses_y)
    company = _line_under(words, _find_phrase(words, "COMPANY"), addresses_y, slack=160)
    contact = _line_under(words, _find_phrase(words, "CONTACT NAME"), addresses_y, slack=120)
    email = _line_under(words, _find_phrase(words, "EMAIL"), payment_y, slack=220)
    alias = _line_under(words, _find_phrase(words, "CUSTOMER ALIAS"), payment_y, slack=160)
    telephone = _line_under(words, _find_phrase(words, "PHONE"), addresses_y + 400, slack=180)

    delivery_label = _find_phrase(words, "DELIVERY ADDRESS")
    billing_lines = _block_under(
        words, _find_phrase(words, "BILLING ADDRESS"), payment_y, delivery_label["x"] - 20,
    )
    delivery_lines = _block_under(
        words, delivery_label, payment_y, delivery_label["x"] + 500,
    )
    payment_method = _line_under(words, _find_phrase(words, "PAYMENT METHOD"), items_y, slack=80)
    paid_status = _line_under(words, _find_phrase(words, "PAID STATUS"), items_y, slack=40)
    payment_date = _line_under(words, _find_phrase(words, "PAYMENT DATE"), items_y, slack=40)

    net = _amount(_line_under(words, net_label, net_label["bottom"] + 60, slack=40))
    vat = _amount(_line_under(words, _find_phrase(words, "VAT TOTAL"), net_label["bottom"] + 60, slack=40))
    gross = _amount(_line_under(words, _find_phrase(words, "GROSS TOTAL"), net_label["bottom"] + 60, slack=40))

    first, last = _split_contact(contact)
    order = OrderData(
        external_reference=reference,
        order_date=order_date,
        source_customer_id=customer_id,
        currency=currency,
        company=company,
        first_name=first,
        last_name=last,
        alias=alias,
        email=email,
        telephone=telephone,
        billing=_address(billing_lines, "billing address"),
        delivery=_address(delivery_lines, "delivery address"),
        payment_method=payment_method,
        paid_status=paid_status,
        payment_date=payment_date,
        items=_items(words, items_y, net_label["y"] - 4),
        net_total=net,
        vat_total=vat,
        gross_total=gross,
    )
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", order.order_date):
        raise ValueError(f"Order date is not YYYY-MM-DD: {order.order_date!r}")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", order.payment_date):
        raise ValueError(f"Payment date is not YYYY-MM-DD: {order.payment_date!r}")
    order.validate()
    return order


def _cross_check(order: OrderData, vision_text: str) -> None:
    if not vision_text:
        return
    folded = vision_text.casefold()
    required = [
        order.external_reference,
        order.order_date,
        order.payment_date,
        f"{order.net_total:.2f}",
        f"{order.vat_total:.2f}",
        f"{order.gross_total:.2f}",
    ]
    missing = [value for value in required if value.casefold() not in folded]
    if missing:
        raise ValueError(f"Vision cross-check missed {missing}")


def extract_order(path: str | Path) -> OrderData:
    image = Path(path)
    if not image.is_file():
        raise FileNotFoundError(image)
    order = parse_words(_tesseract_words(image))
    _cross_check(order, _vision_text(image))
    return order
