# Fakturama image-to-cash

Posts the Northstar order in `samples/order_northstar.png` into the open Fakturama workspace: debtor, VAT, products, a saved order, and a paid follow-up invoice.

macOS has no Microsoft UI Automation. This project drives Fakturama 2.2.0 with the macOS Accessibility API (the AX roles on the process whose bundle id is `Fakturama.ID`) and with on-screen text when SWT does not expose a control. Requirements, the source fields, and the posted records are in [PRD.md](PRD.md).

## Setup

You need a Mac with Fakturama 2.2.0 already open on the workspace you want to post into. Leave that window in front of other apps while the script runs. The script activates `Fakturama.ID` itself.

Grant two privacy permissions to the terminal or IDE that runs Python:

- **Accessibility**, so the script can read AX roles, focus fields, and type into them.
- **Screen Recording**, so it can screenshot the window for OCR and for the pixel scans that find buttons SWT does not expose.

Python 3.12, Tesseract, and the packages in `requirements.txt`:

```bash
brew install tesseract
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

What each piece is for:

| Piece | Role |
| --- | --- |
| Apple Vision (`pyobjc-framework-Vision`) | Reads the order image, and reads a selected blue grid row after its white glyphs are painted black |
| Tesseract | Reads dialog tables and on-screen labels. A full-screen pass is slow |
| OpenCV and Pillow | Pixel scans for the disclosure triangle, the add-address plus, and the blue row highlight |
| pyautogui | Clicks and keystrokes, in logical points. Screenshots are often retina 2x, so pixel positions are scaled back to those points |
| pyperclip | Pastes into fields where a click would drag a window or where a synthesized key press hits the wrong control |
| ApplicationServices / Cocoa | Accessibility tree: roles, titles, focus, and read-back after each write |

Checks that do not touch the UI:

```bash
python -m pytest tests
```

## Run

```bash
python run.py --probe
python run.py samples/order_northstar.png --dry-run
python run.py samples/order_northstar.png
python run.py samples/order_northstar.png --from-step 3.1
```

`--probe` prints the open tabs and windows and saves a screenshot. `--dry-run` fills editors and does not click Save.

`--from-step` accepts `1.3`, `2.1`, `2.5`, `2.10`, `2.11`, `3.1`, `4.1`, `4.5`, or `5.1`. Each step leaves Fakturama ready for the next one. An exact debtor match skips `2.5`, `2.10`, and `2.11`, then checks that the order shows the invoice street.

This workspace already contains the Northstar debtor, both products, VAT 19%, Bank Transfer, and several posted orders and invoices from earlier runs (see [PRD.md](PRD.md)). A full run again creates another order against that same debtor and those products. If an unsaved New Debtor editor is still open, close it without saving before you start, so the run does not leave a second empty editor behind.

Annotated captures from the live runs are in `docs/screenshots/`.

## What the run does

The parser checks line math and the three totals before any UI write. A mismatch stops the run and nothing is posted. Every text write is read back. Save is one click per record. The order tab stays open while master data is created.

| Step | What happens |
| --- | --- |
| 1.3 | Opens a New Order. Sets the date to Jul 14, 2026 when it is not already that date, sets Cust.Ref. `WEB-2026-0714-A17`, and selects Net. The proposed document number is left as Fakturama assigned it |
| 2.1 | Opens the contact selector and searches the debtor. Two rows with the same customer number are one debtor: the upper row is the invoice address (Friedrichstrasse 88 / 10117). The warehouse row is not selected onto the order |
| 2.5 | Creates the debtor only when no exact row exists. Fills identity and the main (invoice) address, then the warehouse as a second address, then miscellaneous |
| 2.10 | Selects Bank Transfer. The term is created once, with code Credit transfer, and is not duplicated |
| 2.11 | Saves the debtor and selects it on the order. The order check requires the invoice street. The delivery street stays on the debtor |
| 3.1 | Creates VAT 19% and both products when they are missing, then completes each line: quantity, unit price, and discount |
| 4.1 | Checks the order (reference, Net, both lines, totals 570.00 / 108.30 / 678.30) and saves it |
| 4.5 | Opens Documents, confirms the order row, and creates the follow-up invoice from the icon under "Create a follow-up document" |
| 5.1 | Sets Bank Transfer, marks the invoice paid on Jul 18, 2026 for 678.30, saves it, and confirms both documents |

### Debtor and addresses

The address search is pasted into the field the dialog already focused. Clicking that field drags the window. The list is read again until a row appears. If the full company name shows nothing, the run searches the first word. A blank ZIP column does not hide a row that shows the contact, the city, and the start of the company.

The add-address control is the plus at the right end of the Main address tab, in a light button a few dozen points from the screen edge. It is not in the accessibility tree. The run finds the dark plus on that tab row, starting just to the right of the words "Main address" and continuing to the screen edge. If an additional address tab is already open, that tab is used and the plus is not clicked again. The form label "additional name" is not a tab. On the extra address the warehouse name goes in additional name, and the street (Beusselstrasse 44) is the row under it. Address type is pasted into the white field and confirmed with Enter. The suggestion checkboxes are not clicked.

Country is the dropdown on the Mobile row. The run clicks the arrow, types the country, and presses Enter. It waits a second first so macOS does not take the keystrokes as a notification.

### Product lines

| Line | Item | Qty | Net | Discount | Line net | Product gross |
| --- | --- | --- | --- | --- | --- | --- |
| Chair | CHR-ERG-01 | 2 | 250.00 | 10% | 450.00 | 297.50 |
| Mat | MAT-DESK-02 | 3 | 40.00 | 0% | 120.00 | 47.60 |

Totals are net 570.00, VAT 108.30, gross 678.30. The image says EUR. This workspace displays `$`. A 10% discount is shown as `-10.00 %`.

The quantity cell expects a decimal such as `1.00`. The number is right-aligned, immediately left of the item number. The gray "Qty." heading is the empty left side of that cell. A click on the heading writes into the item number, the quantity stays 1.00, and the chair price stays the single-unit net 225.00 instead of 450.00. The run clicks the decimal quantity, and it types only when the opened cell already shows a decimal. Enter clears the blue row highlight, so the unit price and the discount reuse that same row. If the grid still shows the single-unit amount, the quantity is set once more. The selected row is read with Apple Vision after its white-on-blue glyphs are painted black. The terminal repeats item numbers; those copies are not extra lines.

Product search is a real keystroke after the field is clicked. An accessibility write hits OK and inserts the highlighted row. The product price entered in Fakturama is the gross price (`net × 1.19`).

### Documents and the paid invoice

Documents has no Search label. The gray toolbar text is a placeholder. The order is under Orders. The paid invoice is under Invoices, then the child `paid`. A selected tree row is white on blue, so that label is often unreadable. The view title "Orders" or "Invoices/paid" means that category is already open. Clicking Invoices while it is expanded collapses the tree and hides `paid`, so the run clicks Invoices only when the paid child is not already visible. The customer reference is truncated to something like `WEB-202…`. The row is matched on `WEB-202` plus the gross total 678.30.

The invoice has no Payment label. The method combo sits between the paid checkbox and Due. The run chooses Bank Transfer, ticks paid, and sets the date after the word "at" to Jul 18, 2026 with value 678.30. The invoice date in the header is left alone.

## What the run does not do

- It does not type the source customer id `CUST-1007`. Fakturama assigns its own id.
- It does not change the proposed document numbers.
- It does not create a delivery note, an invoice correction, or a dunning document.
- It does not delete other debtors or earlier orders in the workspace.
- It does not put the warehouse street on the order. The order shows the invoice address. The warehouse stays on the debtor as the delivery address.
- It does not force the workspace currency. Amounts are checked as numbers. The symbol on this workspace is `$`.
- It does not keep `marta.klein@example.test`. Fakturama rejects the `.test` domain on save and clears that field.

## Layout

```
samples/order_northstar.png
  extract.py          Apple Vision OCR, section parser, Decimal checks
  flow.py             steps 1.3, 2.1, 2.5, 2.10, 2.11, 3.1, 4.1, 4.5, 5.1
  ax.py               Accessibility roles, titles, focus, read-back
  screen.py           OCR anchors, pixel geometry, screenshots
  ui.py               menus, search fields, combos, one Save click
  steps/              header, debtor, payment term, VAT, product, order, invoice
```

Controls are found by role and title first. When SWT does not expose the control, the label is found with OCR and the click is placed relative to that label. A label that OCR misses is read once more before the run stops. An ambiguous match stops the run.
