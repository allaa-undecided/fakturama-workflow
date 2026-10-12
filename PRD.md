# Fakturama Image-to-Cash

Turn one synthetic order image into a saved Fakturama order and its follow-up invoice. Extraction is offline OCR plus a deterministic parser. The live UI is driven with the macOS Accessibility API and on-screen text. There is no Microsoft UI Automation on macOS, and no language-model API.

## Source document

`samples/order_northstar.png`

| Field | Value |
| --- | --- |
| Reference | WEB-2026-0714-A17 |
| Order date | 2026-07-14 (shown as Jul 14, 2026) |
| Currency in the image | EUR. This Fakturama workspace displays amounts with $ |
| Debtor | Northstar Office GmbH, Marta Klein, alias NORTHSTAR-BERLIN |
| Phone | +49 30 5550 1420 |
| Billing | Friedrichstrasse 88, 10117 Berlin, Germany |
| Delivery | Northstar Office Warehouse, Beusselstrasse 44, 10553 Berlin, Germany |
| Payment | Bank Transfer, code Credit transfer, PAID on 2026-07-18 |
| Chair | CHR-ERG-01, qty 2, net 250.00, discount 10%, VAT 19%, line 450.00, product gross 297.50 |
| Mat | MAT-DESK-02, qty 3, net 40.00, discount 0%, VAT 19%, line 120.00, product gross 47.60 |
| Totals | net 570.00, VAT 108.30, gross 678.30 |

The source customer id CUST-1007 is never typed. Fakturama assigns its own id.

## What was posted

| Record | Result |
| --- | --- |
| Payment term | Bank Transfer, code Credit transfer, numeric fields left at zero |
| VAT | VAT 19%, description VAT 19%, code S (Standard rate), value 19%. Not set as the workspace standard |
| Debtor | CUST000006, Northstar Office GmbH, Marta Klein, alias NORTHSTAR-BERLIN, discount 0%, Net, payment Bank Transfer |
| Billing address | Friedrichstrasse 88, 10117 Berlin, Germany, phone +49 30 5550 1420 |
| Delivery address | additional address #1, Northstar Office Warehouse, Beusselstrasse 44, 10553 Berlin, Germany, address type Delivery address |
| Products | Ergonomic Desk Chair CHR-ERG-01 gross 297.50, VAT 19%, cost 0, stock 0. Anti-Fatigue Desk Mat MAT-DESK-02 gross 47.60, VAT 19%, cost 0, stock 0 |
| Order | PO000004, date Jul 14, 2026, Cust.Ref. WEB-2026-0714-A17, price mode Net, both lines, totals 570.00 / 108.30 / 678.30. Saved once |
| Invoice | INV000003, created with the order's follow-up Invoice action. Invoice date left as Oct 12, 2026. Paid, Bank Transfer, payment date Jul 18, 2026, value 678.30. Saved once |

Documents lists PO000004 under Orders (678.30) and INV000003 under Invoices/paid (paid, 678.30). PO000002 / INV000002 and PO000003 from earlier passes in this workspace are also listed. No delivery note, invoice correction, or dunning was created.

## Step status

| Steps | Status |
| --- | --- |
| 1.3-1.8 New Order header | Done. The proposed number is not edited. A date that already reads Jul 14, 2026 is left in place |
| 2.1-2.4 Select debtor | Done. The address dialog matched the 10117 Berlin row. Company text is truncated to Northstar O... |
| 2.5-2.9 Debtor, both addresses, miscellaneous | Done on the debtor. Main address is the invoice address. The second address holds the warehouse |
| 2.10-2.13 Payment and save | Bank Transfer already existed and was selected. The debtor was saved. The order shows the invoice address |
| 3.1-3.17 Products and lines | Done. VAT 19% was created because a search-box false match had earlier claimed it existed. Both products were created with that VAT, selected onto the order, and the lines match 450.00 and 120.00 |
| 4.1-4.7 Save order and follow-up invoice | Done. The common-data section had to be expanded before the reference and address were visible. Follow-up Invoice was the icon under "Create a follow-up document", not the toolbar Invoice button |
| 5.1-5.7 Paid invoice and documents | Done on INV000003. Invoice date stayed Oct 12, 2026. The paid date is the field after "at", set to Jul 18, 2026, with value 678.30. Bank Transfer was chosen from the combo beside paid |

## Known gaps

- Documents opens on unpaid invoices. The order is under the Orders category. The paid invoice is under Invoices/paid. A selected category is white on blue, so that tree label is not read; the view title Orders or Invoices/paid means that category is already open. paid is the child under Invoices. The run does not click Invoices again when that child is already visible, because that click collapses the tree. The customer reference is truncated in that list, so the row is recognized by WEB-202 and the gross total. The toolbar search is gray placeholder text, not a label, and the run does not look for a Search label there. The Documents view is opened from the Data menu when that tab is not already open. After the order is saved its tab title is the document number, and the follow-up Invoice action is used on that tab.
- The invoice has no Payment label. Before it is marked paid the method combo shows between the paid checkbox and Due, often as Pay Cash. The run opens that combo and chooses Bank Transfer. Ticking paid reveals the payment date after the word "at" and the value. The invoice date in the header is left alone.
- The order shows one address tab. The address list has one row per address, and the first row is the billing address. The warehouse address remains on the debtor. The address box on the order shows the company, the contact, and the street. The order check uses that billing street. Item numbers are truncated, and a selected row hides its price, so each row and the totals are read in turn.
- `marta.klein@example.test` does not remain after save. Fakturama validates email addresses before save and rejects the `.test` domain.
- Amounts were checked as numbers. The workspace currency symbol is `$`, not EUR.
- A 10% line discount is displayed as `-10.00 %`. The line net of 450.00 confirms it is a discount.
- The common-data section starts collapsed and hides Cust.Ref. and the address. The run opens the disclosure triangle at the right end of that bar before it looks for the contact icon. Once open, OCR may read the tab as "Addresses invoice", or as the separate words Invoice and address; either still counts. Cust.Ref. on that bar means the section is open, and the triangle is not clicked again.
- Country is a dropdown on the same row as Mobile. The run clicks that dropdown, types the country name, and presses Enter. The pointer stays on the arrow. A terminal line that starts with Country is not the form label. It waits a second before those keystrokes so they are not taken as a macOS notification, and it does not select all first, because that replaces the city. The name is not chosen by scrolling the full list. If the keystrokes change the city field, the city is restored and the run stops. ZIP and City are often read as two separate words; either spelling of that label is the same row. Alias and name are read the same way. Net or Gross is often three words; the run selects Net with one Down from the default blank value.
- Address type is pasted into the white text field and confirmed with Enter. The suggestion checkboxes are not clicked, and the Street label is not clicked, because that click clears the type. After Enter the field's accessibility value is empty, so the run checks that the role is visible on that row. When the address list has two rows, the invoice one is selected.
- The add-address control is the plus at the right end of the Main address tab, in a light button a few dozen points from the screen edge. OCR splits that label, so the run pairs the Main and address words and clicks the dark plus glyph on that row, starting just to the right of the label and continuing to the screen edge. A search that stops well short of the edge cuts through the glyph. An extra address tab is only the one on that same bar. The form label "additional name" is not that tab. If the tab is already open, the run uses it instead of clicking plus again. The Street label on that tab can read as "stree", and the same label is sometimes read twice. The run treats one row as one Street. On that extra address the street is the row under additional name; the warehouse name goes in additional name, and the street is not written into that upper field. Billing is written on the Main address tab. When Street or ZIP is already visible, the Addresses section is already open and that tab is not clicked again. The editor can be left on Miscellaneous.
- The product search is typed with a real keystroke after the field is clicked. An accessibility write or a synthesized key press hits OK and inserts the highlighted row. A unique match closes the dialog and places that product on the order. The new line is selected in blue, so its column is read from the gray header and its row from that highlight. Qty on that header is often not read as the word Qty; it is the column immediately left of Item No, and the position heading further left is not that column. The quantity number is right-aligned, immediately left of the item number, so the heading is the empty left side of the cell. A click on the heading, or on the first digit near it, writes into the item number: the quantity stays 1.00 and the line price stays the single-unit net (225.00 instead of 450.00). The run clicks that decimal quantity, and it types only when the opened cell already shows a decimal such as 1.00. Enter then clears the blue row, so the unit price and the discount use that same row instead of searching again. The terminal repeats the item number, and those copies are not extra lines. If the line price is still the single-unit amount, it sets the quantity once more. A line that is already on the order but does not yet show its line price is completed in place. The selected row is read by turning its white glyphs black, then with Apple Vision, across the items row including the Price column. The blue highlight is found by its blue pixels, so a wide window does not hide the price.
- The address search is pasted into the field the dialog already focused. The field sits in the dialog title bar, and clicking it drags the window off the screen. The list is read again until a row appears, because the filter draws after the paste. If the full company name still shows nothing, the run searches the first word of the company. A blank result is then read with the search cleared. If that full list is readable and has no Northstar row, the run creates the Debtor. The invoice address is the row with the billing street or ZIP. The warehouse shares the city, so the first Berlin row is not enough. Two rows with the same customer number are that debtor's two addresses, and the upper row is the invoice address. The order check looks for that invoice street, the way the run did when Friedrichstrasse 88 was on the order. A filtered row that shows the contact name, city, and the start of the company is the saved debtor even when the ZIP is not read. It stops only when a populated list cannot be read.
- NatTable cells and several SWT combos are absent from the accessibility tree until they are opened. Writes are read back. An ambiguous match stops the run. A label that OCR misses entirely is read once more before the run stops.
- The payment combo on the debtor is filled when that editor opens. A term created afterward is selected after the debtor is saved and opened again. The saved editor tab is titled with the company and the contact name. The payment-term editor opens on the left side of the window. Its payment-code label is often one garbled word, and the run types the code into the value already shown on that row.

## Architecture

```
samples/order_northstar.png
  extract.py     Apple Vision OCR, section parser, Decimal checks
  flow.py        steps 1.3, 2.1, 2.5, 2.10, 2.11, 3.1, 4.1, 4.5, 5.1
  ax.py          Accessibility roles, titles, focus, read-back
  screen.py      OCR anchors, field pixels, screenshots
  ui.py          menus, search fields, combos, one Save click
  steps/         header, debtor, payment term, VAT, product, order, invoice
```

Controls are found by role and title first. If SWT does not expose the control, the label is found with OCR and the click is placed relative to that label. Absolute screen coordinates are not the design. Every text write is read back. Save is one click per record. The order tab stays open while master data is created.

## Decisions

- Order first, then debtor, payment term, VAT, products, save, then the follow-up invoice.
- Parser checks line math and the three totals before any UI write. A mismatch raises and nothing is posted.
- Payment code for Bank Transfer is Credit transfer. The run clicks that combo, waits a second, and types the code so a macOS notification does not take the keystrokes. A shortened reading such as "Credit trar" still counts. The term is not duplicated if it already exists. The debtor Payment list is filled when that editor opens, so a term created afterward is missing and the list shows only Pay Cash. The run then saves, closes, waits, opens Debtors, and searches that CUST number. The same number in the search box is not a second row. It waits for the customer row and for the editor to open. It waits again for the Payment list to draw, clicks the Bank row under that field, or types Bank Transfer into the combo and presses Enter. A terminal line that starts with Payment is not the form label. The id it reopens is the CUST number, not the Customer label. A zero in that number read as the letter O is searched as a zero.
- Product price entered in Fakturama is the gross price (`net x 1.19`, half-up to cents), in the field labeled Price (gross). The price (net) field is not typed. On a Net document the line unit price becomes the net amount.
- The line VAT list is loaded when the order editor opens. A VAT created later is invisible on that editor until the product is saved with the new VAT and the line is added again. A VAT search reuses the one table row named VAT 19%. The search box is not a second row, and the description on that same row is not a second VAT. The value field shows a percent sign after the number, so a read-back of 19% counts as 19. A terminal line that repeats Name or Description from that VAT step is not the product field. The product selector is the document icon above the green plus. The click is that icon's center. The red delete mark below the plus is not clicked. The product VAT combo lists VAT 19% and VAT Free Tax. The editor tab named VAT 19% is not that list. The product selects VAT 19%.
- Address type is pasted and confirmed with Enter, then Tab so the field loses focus. The suggestion checkboxes are not clicked.
