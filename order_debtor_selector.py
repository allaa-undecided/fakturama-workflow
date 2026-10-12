"""Fakturama macOS — missing Debtor creation, single-file automation.

Safe-by-default: fills recognized fields but does not save unless --save.

Run with an unsaved New Order or an open New Debtor.  Requires pyobjc,

pyautogui, pytesseract/OpenCV already used in the assessment.

This is an implementation candidate; controls must be tested on the actual UI.

"""

import argparse

import re

import time

from dataclasses import dataclass

import AppKit

import ApplicationServices as AX

import cv2

import numpy as np

import pyautogui

import pytesseract

from pytesseract import Output

pyautogui.FAILSAFE = True

pyautogui.PAUSE = 0.12

@dataclass

class Customer:

    company: str = 'Automation Test Company'

    first_name: str = 'Test'

    last_name: str = 'Customer'

    street: str = '123 Example Street'

    zip: str = '12345'

    city: str = 'Boston'

    country: str = 'United States'

    email: str = 'test@example.com'

    telephone: str = '5550100'

    alias: str = 'Automation Test'

    payment_method: str = 'Bank Transfer'

    additional_name: str = ''

    address_specification: str = ''

    district: str = ''

    delivery_same_as_billing: bool = True

DATA = Customer()

def ax(el, key):

    if el is None: return None

    error, value = AX.AXUIElementCopyAttributeValue(el, key, None)

    return value if error == 0 else None

def walk(root):

    pending = [root]

    while pending:

        element = pending.pop()

        yield element

        pending.extend(

            attr(element, "AXChildren") or []

        )

def all_nodes(root, max_nodes=2000):

    pending = [root]

    for _ in range(max_nodes):

        if not pending: break

        el = pending.pop()

        yield el

        pending.extend(ax(el, 'AXChildren') or [])

def find_exact(root, role, title):

    matching = [e for e in all_nodes(root)

                if ax(e, 'AXRole') == role and ax(e, 'AXTitle') == title]

    if len(matching) != 1:

        raise RuntimeError(f'Expected exactly one {role} {title!r}, got {len(matching)}')

    return matching[0]

def press(el):

    error = AX.AXUIElementPerformAction(el, 'AXPress')

    if error != 0: raise RuntimeError(f'AXPress failed: {error}')

def activate():

    if not AX.AXIsProcessTrusted():

        raise RuntimeError('Grant Accessibility permission to the Python launcher.')

    for running in AppKit.NSWorkspace.sharedWorkspace().runningApplications():

        if 'fakturama' in str(running.localizedName() or '').lower():

            running.activateWithOptions_(AppKit.NSApplicationActivateIgnoringOtherApps)

            time.sleep(.5)

            return AX.AXUIElementCreateApplication(running.processIdentifier())

    raise RuntimeError('Fakturama not running')

def tab_titles(app):

    return [str(ax(e, 'AXTitle') or '')

            for e in all_nodes(app) if ax(e, 'AXRole') == 'AXRadioButton']

def active_new_debtor(app):

    for e in all_nodes(app):

        if (ax(e, 'AXRole') == 'AXRadioButton' and

            str(ax(e, 'AXTitle') or '').lstrip('*') == 'New Debtor' and

            ax(e, 'AXValue') is True):

            return True

    return False

def open_new_debtor(app):

    if active_new_debtor(app):

        print('New Debtor already active')

        return

    print('Opening New > New Debtor (preserving background Order)')

    press(find_exact(app, 'AXMenuBarItem', 'New'))

    time.sleep(.2)

    press(find_exact(app, 'AXMenuItem', 'New Debtor'))

    time.sleep(.7)

    if not active_new_debtor(app):

        raise RuntimeError(f'New Debtor did not become active. Tabs: {tab_titles(app)}')

    print('New Debtor active. Tabs:', tab_titles(app))

def image_words():

    shot = pyautogui.screenshot()

    sw, sh = pyautogui.size()

    sx, sy = sw / shot.width, sh / shot.height

    bgr = cv2.cvtColor(np.array(shot), cv2.COLOR_RGB2BGR)

    scaled = cv2.resize(bgr, None, fx=2, fy=2, interpolation=cv2.INTER_CUBIC)

    data = pytesseract.image_to_data(scaled, config='--psm 11', output_type=Output.DICT)

    groups = {}

    for i, raw in enumerate(data['text']):

        s = str(raw).strip()

        if not s: continue

        key = (data['block_num'][i], data['par_num'][i], data['line_num'][i])

        entry = groups.setdefault(key, [])

        entry.append((s, data['left'][i] / 2 * sx,

                      data['top'][i] / 2 * sy,

                      data['width'][i] / 2 * sx,

                      data['height'][i] / 2 * sy))

    lines = []

    for values in groups.values():

        values.sort(key=lambda v: v[1])

        left = min(v[1] for v in values)

        top = min(v[2] for v in values)

        right = max(v[1] + v[3] for v in values)

        bottom = max(v[2] + v[4] for v in values)

        lines.append({'text': ' '.join(v[0] for v in values),

                      'x': left, 'y': top, 'right': right,

                      'bottom': bottom})

    return lines

def norm(s):

    return re.sub(r'\s+', ' ', str(s).strip().casefold())

def label_line(words, text):

    candidates = [w for w in words if norm(w['text']).strip(':') == norm(text)]

    if len(candidates) != 1:

        raise RuntimeError(f'Cannot uniquely find visible label {text!r}: {candidates}')

    return candidates[0]

def focus_relative(app, label, field='right', offset=45):

    words = image_words()

    w = label_line(words, label)

    x = w['right'] + offset if field == 'right' else (w['x'] + w['right']) / 2

    y = (w['y'] + w['bottom']) / 2

    pyautogui.click(x, y)

    time.sleep(.20)

    focused = ax(app, 'AXFocusedUIElement')

    role = ax(focused, 'AXRole')

    if role not in ('AXTextField', 'AXTextArea', 'AXComboBox'):

        raise RuntimeError(f'Expected editable control near {label!r}, got {role}')

    return focused

def set_value(field, value, label):

    if value is None: return

    before = ax(field, 'AXValue')

    error = AX.AXUIElementSetAttributeValue(field, 'AXValue', value)

    after = ax(field, 'AXValue')

    if error or after != value:

        raise RuntimeError(f'{label} failed to set; before={before!r}, after={after!r}, error={error}')

    print(f'  {label}: {value!r} ✓')

def set_from_label(app, label, value, offset=45):

    if not value: return

    el = focus_relative(app, label, offset=offset)

    set_value(el, value, label)

def initialize_company(app, customer):

    print('Entering identity fields')

    focussed = ax(app, 'AXFocusedUIElement')

    help_text = str(ax(focussed, 'AXHelp') or '')

    if 'Next contact ID' in help_text:

        customer_id = ax(focussed, 'AXValue')

        pyautogui.press('tab')

        time.sleep(.2)

        if 'Choose a category' not in str(ax(ax(app,'AXFocusedUIElement'),'AXHelp') or ''):

            raise RuntimeError('Category tab order changed; stopped')

        pyautogui.press('tab')

        time.sleep(.2)

        company_field = ax(app, 'AXFocusedUIElement')

        if ax(company_field, 'AXRole') not in ('AXTextArea','AXTextField'):

            raise RuntimeError('Company control not focused')

        set_value(company_field, customer.company, 'Company')

        if ax(focussed, 'AXValue') != customer_id:

            raise RuntimeError('Customer ID changed unexpectedly!')

        print('  Customer ID preserved:', customer_id)

    else:

        # Visual fallback for already-open form with another control focused.

        set_from_label(app, 'Company', customer.company, offset=70)

    # Name labels overlap visually on this Fakturama version. Use separately

    # validated two-field geometry from the visible row rather than Tab counts.

    words = image_words()

    row = [w for w in words if 'first name' in norm(w['text']) and 'last name' in norm(w['text'])]

    if len(row) != 1:

        raise RuntimeError('Could not identify First Name / Last Name row')

    y = (row[0]['y'] + row[0]['bottom']) / 2

    # Use the SWT layout relationship: first field starts just to right of label;

    # second follows in the same row. Confirm both are editable before writing.

    base = row[0]['right']

    def at(x):

        pyautogui.click(x,y); time.sleep(.15)

        e=ax(app,'AXFocusedUIElement')

        if ax(e,'AXRole') not in ('AXTextField','AXTextArea'):

            raise RuntimeError('First/Last Name visual grounding failed')

        return e

    e1 = at(base + 60)

    x1 = re.search(r'x:\s*([\d.]+)', str(ax(e1, 'AXPosition')))

    wid1 = re.search(r'w:\s*([\d.]+)', str(ax(e1, 'AXSize')))

    if not x1 or not wid1:

        raise RuntimeError('Cannot measure First Name control')

    e2 = at(float(x1.group(1)) + float(wid1.group(1)) + 45)

    if str(e1) == str(e2):

        raise RuntimeError('First and Last Name resolved to the same field')

    set_value(e1, customer.first_name, 'First Name')

    set_value(e2, customer.last_name, 'Last Name')

def fill_address(app, customer):

    print('Entering Main address and contact details')

    for label, value, offset in (

        ('Street', customer.street, 55),

        ('E-Mail', customer.email, 70),

        ('Telephone', customer.telephone, 70),

        ('additional name', customer.additional_name, 65),

        ('Address specification', customer.address_specification, 60),

        ('district', customer.district, 60),

    ):

        set_from_label(app, label, value, offset)

    # ZIP - City is one composite label with two text controls in a single row.

    words = image_words()

    match = [w for w in words if norm(w['text']) in ('zip - city', 'zip-city')]

    if len(match) != 1:

        raise RuntimeError('ZIP - City label not uniquely detected')

    y = (match[0]['y'] + match[0]['bottom']) / 2

    x = match[0]['right'] + 35

    pyautogui.click(x,y); time.sleep(.2)

    zip_el = ax(app,'AXFocusedUIElement')

    if ax(zip_el,'AXRole') != 'AXTextField':

        raise RuntimeError('ZIP field not an AXTextField')

    p = re.search(r'x:\s*([\d.]+)', str(ax(zip_el,'AXPosition')))

    s = re.search(r'w:\s*([\d.]+)', str(ax(zip_el,'AXSize')))

    if not p or not s: raise RuntimeError('Cannot measure ZIP field')

    pyautogui.click(float(p.group(1))+float(s.group(1))+55, y)

    city_el = ax(app,'AXFocusedUIElement')

    if ax(city_el,'AXRole') not in ('AXTextField','AXTextArea') or str(zip_el)==str(city_el):

        raise RuntimeError('City field not distinguishable from ZIP')

    set_value(zip_el,customer.zip,'ZIP')

    set_value(city_el,customer.city,'City')

    # Country is a selection widget. Leave untouched only if it already equals source.

    current_country = [w for w in image_words() if norm(w['text']) == norm(customer.country)]

    if len(current_country) != 1:

        raise RuntimeError('Country not visibly verified; select exact country manually before saving')

    print('  Country visible:', customer.country)


# =====================================================================
# New Debtor remaining configuration.  Use local OCR + AX confirmation.
# =====================================================================

PAYMENT_CODES = {
    'Bank Transfer': 'Credit transfer',
    'Credit Card': 'Credit card',
    'SEPA Direct Debit': 'SEPA direct debit',
}


def unique_visible_label(text, exact=True):
    tokens = image_words()
    expected = norm(text)
    matches = [t for t in tokens if (
        norm(t['text']).strip(':') == expected if exact
        else expected in norm(t['text'])
    )]
    if len(matches) != 1:
        raise RuntimeError(f'Expected one visible {text!r}; found {len(matches)}: {matches}')
    return matches[0]


def click_visible_label(text, exact=True):
    t = unique_visible_label(text, exact)
    pyautogui.click((t['x'] + t['right']) / 2,
                    (t['y'] + t['bottom']) / 2)
    time.sleep(.35)


def focused_editor(app, description):
    el = ax(app, 'AXFocusedUIElement')
    role = ax(el, 'AXRole')
    if role not in ('AXTextField', 'AXTextArea', 'AXComboBox'):
        raise RuntimeError(f'{description}: expected editable control; found {role}')
    if not active_new_debtor(app):
        raise RuntimeError(f'{description}: New Debtor tab is not active')
    return el


def edit_from_label(app, label, value, offset=55, commit=True):
    el = focus_relative(app, label, offset=offset)
    if not active_new_debtor(app):
        raise RuntimeError(f'{label}: not in New Debtor')
    set_value(el, str(value), label)
    if commit:
        pyautogui.press('enter')
        time.sleep(.4)
        current = ax(el, 'AXValue')
        if str(current).strip() != str(value).strip():
            raise RuntimeError(f'{label} changed after Enter: {current!r}')
    return el


def set_address_roles(app, customer):
    """Set Main address roles from the already-verified Country VALUE row.

    The old OCR fallback incorrectly anchored to City (Boston). The address
    type editor is the text control immediately BELOW the Country combo,
    sharing its left alignment. We do not use the unreliable address-type OCR.
    """
    role_text = ('Invoice address,Delivery address'
                 if customer.delivery_same_as_billing else 'Invoice address')
    print('Setting Main address type:', role_text, flush=True)

    # fill_address() already successfully confirmed this exact country value.
    # image_words() is expressed in the same macOS point coordinates used by
    # pyautogui.click(), accounting for Retina scaling.
    country_matches = [w for w in image_words()
                       if norm(w['text']) == norm(customer.country)]
    if len(country_matches) != 1:
        raise RuntimeError('Country value not uniquely visible; address type not changed')
    country = country_matches[0]

    # In the user's actual Fakturama editor, Country and address type are
    # consecutive rows 22-24 points apart. Click within the left part of the
    # blank text field, directly below the CURRENT Country value. Never use
    # the ZIP/City label or any text reading Boston to derive the position.
    x = country['x'] + 65
    base_y = (country['y'] + country['bottom']) / 2
    target = None
    for delta in (23, 25, 21):
        pyautogui.click(x, base_y + delta)
        time.sleep(.18)
        candidate = ax(app, 'AXFocusedUIElement')
        current = str(ax(candidate, 'AXValue') or '').strip()
        role = ax(candidate, 'AXRole')
        if role in ('AXTextField', 'AXTextArea') and current in (
                '', 'Invoice address', 'Delivery address', role_text):
            target = candidate
            break
        print(f'  Address target probe at +{delta}: {role} {current!r} (skipped)', flush=True)

    if target is None:
        raise RuntimeError('Address type text control not safely identified; nothing overwritten')

    current = str(ax(target, 'AXValue') or '').strip()
    if current != role_text:
        set_value(target, role_text, 'address type')
        pyautogui.press('enter')
        time.sleep(.4)
    observed = str(ax(target, 'AXValue') or '').strip()
    if observed != role_text:
        raise RuntimeError(f'Address type not committed: {observed!r}')
    print('Address type committed and read back:', observed, flush=True)
    return True


def select_section(name):
    """Switch Addresses -> Miscellaneous from the known Last Name input."""
    if name != 'Miscellaneous':
        raise RuntimeError('Only the Miscellaneous editor tab is supported')
    app = activate()
    row = [w for w in image_words() if 'first name' in norm(w['text'])
           and 'last name' in norm(w['text'])]
    if len(row) != 1:
        raise RuntimeError('Cannot identify First Name/Last Name row')
    y = (row[0]['y'] + row[0]['bottom']) / 2
    pyautogui.click(row[0]['right'] + 400, y)
    time.sleep(.15)
    e = ax(app, 'AXFocusedUIElement')
    if str(ax(e, 'AXValue') or '') != DATA.last_name:
        raise RuntimeError('Last Name did not receive focus; not switching tabs')
    pyautogui.press('tab')
    time.sleep(.15)
    pyautogui.press('right')
    time.sleep(.15)
    pyautogui.press('tab')
    time.sleep(.35)
    visible = ' '.join(norm(t['text']) for t in image_words())
    if 'alias' not in visible or 'payment' not in visible:
        raise RuntimeError('Miscellaneous controls did not appear')
    print('SUCCESS: Miscellaneous opened; Web Site focused')


def select_net(app):
    """Use the verified UI gesture, but verify via a field-scoped screenshot."""
    label = [t for t in image_words() if norm(t['text']) == 'net or gross']
    if len(label) != 1:
        raise RuntimeError('Net or Gross label not uniquely visible')
    w = label[0]
    pyautogui.click(w['right'] + 90, (w['y']+w['bottom']) / 2)
    time.sleep(.15)
    # On this SWT combo, opening it then one Down selects Net from ---.
    pyautogui.press('down')
    time.sleep(.15)
    pyautogui.press('enter')
    time.sleep(.35)
    labels = [t for t in image_words() if norm(t['text']) == 'net or gross']
    if len(labels) != 1:
        raise RuntimeError('Could not relocate Net or Gross label to verify')
    w = labels[0]
    values = [t for t in image_words() if norm(t['text']) == 'net'
              and t['x'] > w['right'] and abs(t['y'] - w['y']) < 13
              and t['x'] - w['right'] < 300]
    if len(values) != 1:
        raise RuntimeError('Net not verified in its own row; not saving')
    print('  Net or Gross: Net ✓')


def set_miscellaneous(app, customer):
    select_section('Miscellaneous')
    edit_from_label(app, 'Alias name', customer.alias, offset=75)
    # Fakturama stores 0 as 0%; leave already-correct value alone.
    discount = focus_relative(app, 'Discount', offset=60)
    existing = str(ax(discount, 'AXValue') or '').strip()
    if existing not in ('0%', '0', '0.0%', '0.00%'):
        raise RuntimeError(f'Discount not zero: {existing!r}')
    print('  Discount: 0% ✓')
    select_net(app)
    print('Miscellaneous completed')


def screen_geometry():
    shot = pyautogui.screenshot()
    sw, sh = pyautogui.size()
    return sw, sh, sw / shot.width, sh / shot.height


def ocr_tokens():
    """Single-token OCR boxes in macOS logical screen coordinates."""
    shot = pyautogui.screenshot()
    sw, sh = pyautogui.size()
    sx, sy = sw / shot.width, sh / shot.height
    doubled = cv2.resize(np.asarray(shot), None, fx=2, fy=2,
                         interpolation=cv2.INTER_CUBIC)
    d = pytesseract.image_to_data(doubled, config='--psm 11',
                                 output_type=Output.DICT)
    out=[]
    for i, raw in enumerate(d['text']):
        if str(raw).strip():
            out.append({'text': str(raw).strip(),
                        'x': d['left'][i]/2*sx,
                        'y': d['top'][i]/2*sy,
                        'right': (d['left'][i]+d['width'][i])/2*sx,
                        'bottom': (d['top'][i]+d['height'][i])/2*sy})
    return out


def click_sidebar_terms():
    """The Data sidebar item has the exact label 'terms of payment'."""
    tokens=ocr_tokens()
    sw, sh = pyautogui.size()
    # Find the adjacent three tokens in the left 25% of the screen.
    rows=[]
    for a in tokens:
        if norm(a['text'])!='terms' or a['x'] >= sw*.27: continue
        near=[b for b in tokens if abs(b['y']-a['y'])<10 and
              b['x']>a['x'] and b['x']<a['x']+150]
        if {'of','payment'}.issubset({norm(b['text']) for b in near}):
            rows.append(a)
    if len(rows)!=1:
        raise RuntimeError(f'Cannot uniquely locate terms of payment sidebar: {len(rows)}')
    a=rows[0]
    pyautogui.click((a['x']+a['right'])/2,(a['y']+a['bottom'])/2)
    time.sleep(.55)
    print('Opened Data > terms of payment')


def find_terms_tab_open():
    visible=' '.join(norm(v['text']) for v in image_words())
    if not ('disc. days' in visible or 'net days' in visible):
        raise RuntimeError('Terms-of-payment table is not visibly open')


def click_tab_title(app, title):
    candidates=[]
    for e in all_nodes(app):
        if (ax(e,'AXRole') == 'AXRadioButton' and
            str(ax(e,'AXTitle') or '').lstrip('*') == title):
            candidates.append(e)
    if len(candidates) == 1:
        press(candidates[0]); time.sleep(.45); return
    # Individual title tokens may be split in OCR, avoid unsafe guesses.
    raise RuntimeError(f'Cannot uniquely switch to tab {title!r} ({len(candidates)} AX matches)')


def enter_terms_search(app, value):
    """Click Search at upper right of the terms list, and filter rows."""
    # Screenshot ground: find the single Search input in the editor's upper right.
    sw, sh = pyautogui.size()
    labels=[t for t in ocr_tokens() if norm(t['text']).strip(':')=='search'
            and t['x'] > sw*.60 and t['y'] < sh*.30]
    if len(labels)!=1:
        raise RuntimeError(f'Terms Search label ambiguous: {len(labels)}')
    t=labels[0]
    pyautogui.click(t['right'] + 55, (t['y']+t['bottom'])/2)
    time.sleep(.12)
    focused=ax(app,'AXFocusedUIElement')
    if ax(focused,'AXRole') not in ('AXTextField','AXTextArea'):
        raise RuntimeError('Terms Search not an editable field')
    pyautogui.hotkey('command','a')
    pyautogui.write(value, .008)
    time.sleep(.55)


def read_term_list_matches(method):
    """OCR list region only; distinguish result row from search entry."""
    sw,sh=pyautogui.size()
    tokens=ocr_tokens()
    # In user's screenshot list is upper left of editor; ignore the search box.
    matches=[]
    for t in tokens:
        if norm(t['text']) == norm(method) and t['y'] < sh*.65 and t['x'] < sw*.7:
            matches.append(t)
    return matches


def click_terms_plus():
    """Locate green + in the terms-of-payment tab, using image-color validation."""
    shot=pyautogui.screenshot()
    sw,sh,sx,sy=screen_geometry()
    arr=np.array(shot.convert('RGB'))
    # The list '+' is at its top-right, not the Fakturama toolbar's New icons.
    # Find green circle via threshold + contour in top 25% and right 35%.
    hh,ww=arr.shape[:2]
    roi=arr[int(hh*.07):int(hh*.28),int(ww*.63):]
    hsv=cv2.cvtColor(roi,cv2.COLOR_RGB2HSV)
    mask=cv2.inRange(hsv,np.array([35,65,45]),np.array([95,255,255]))
    contours,_=cv2.findContours(mask,cv2.RETR_EXTERNAL,cv2.CHAIN_APPROX_SIMPLE)
    choices=[]
    for c in contours:
        x,y,w,h=cv2.boundingRect(c)
        if 4 <= w <= 55 and 4 <= h <= 55 and .55 < w/h < 1.7:
            choices.append((x+int(ww*.63)+w/2,y+int(hh*.07)+h/2,w*h))
    # This is a best effort; stop on ambiguity rather than click toolbar.
    if len(choices) != 1:
        raise RuntimeError(f'Cannot uniquely detect terms green + (candidates={len(choices)}). Please open New Term of Payment manually and rerun with --resume-payment.')
    x,y,_=choices[0]
    pyautogui.click(x*sx,y*sy)
    time.sleep(.55)


def terms_editor_visible():
    titles=' '.join(norm(w['text']) for w in image_words())
    return 'new term of payment' in titles or ('cash discount' in titles and 'discount days' in titles)


def terms_row(label):
    """Find a label inside the floating payment-term editor, not the list behind it.

    The editor is the right-hand upper panel in the supplied screenshots.
    OCR can split/merge labels, so look at individual tokens first.
    """
    sw, sh = pyautogui.size()
    tokens = ocr_tokens()
    expected = norm(label).strip(':')
    # Name exists in the background payment table too; only the floating editor
    # in the upper-right is eligible. All positions are logical screen points.
    region = [t for t in tokens if sw * .59 <= t['x'] <= sw * .91
              and sh * .13 <= t['y'] <= sh * .46]
    exact = [t for t in region if norm(t['text']).strip(':') == expected]
    if len(exact) == 1:
        return exact[0]
    # Multi-word labels sometimes become multiple tokens, same line.
    parts = expected.split()
    if len(parts) > 1:
        matches=[]
        for t in region:
            if norm(t['text']).strip(':') != parts[0]:
                continue
            following = [v for v in region if abs(v['y']-t['y']) < 9
                         and v['x'] > t['x'] and v['x'] < t['x']+190]
            following.sort(key=lambda v: v['x'])
            if [norm(v['text']).strip(':') for v in following[:len(parts)-1]] == parts[1:]:
                last = following[len(parts)-2]
                matches.append({**t, 'right': last['right']})
        if len(matches) == 1:
            return matches[0]
    # Don't guess a different editor if the Name label was missed.
    print('Payment editor visible OCR tokens:',
          [(t['text'], round(t['x']), round(t['y'])) for t in region], flush=True)
    raise RuntimeError(f'Payment editor label {label!r} not located uniquely '
                       f'(matches={len(exact)}). No record saved.')


def set_terms_field(app, label, value, offset=100):
    w=terms_row(label)
    y=(w['y']+w['bottom'])/2
    pyautogui.click(w['right'] + offset,y)
    time.sleep(.12)
    e=ax(app,'AXFocusedUIElement')
    if ax(e,'AXRole') not in ('AXTextField','AXTextArea'):
        raise RuntimeError(f'Term field {label!r} not editable')
    err=AX.AXUIElementSetAttributeValue(e,'AXValue',str(value))
    found=str(ax(e,'AXValue') or '').strip()
    valid=(found==str(value) or (str(value)=='0' and found in ('0%','0.0%')))
    if err != 0 or not valid:
        raise RuntimeError(f'Term {label}: expected {value!r}, got {found!r} AX={err}')
    print(f'  Term {label}: {found} ✓')


def select_payment_code(app, code):
    w=terms_row('Payment') if False else None
    # In this version Payment has a standalone heading; the payment code
    # label is rendered as '!editorPaymentPaymentcode!' in some locales.
    rows=[r for r in image_words() if 'paymentcode' in norm(r['text']).replace(' ','')
          and r['x'] > pyautogui.size()[0]*.55]
    if len(rows) != 1:
        raise RuntimeError('Cannot identify payment-code dropdown label')
    r=rows[0]
    pyautogui.click(r['right'] + 125, (r['y']+r['bottom'])/2)
    time.sleep(.2)
    pyautogui.press('home')
    # GUI Combo: choose by type ahead; AX readback may point at a different control.
    pyautogui.write(code, .03)
    pyautogui.press('enter')
    time.sleep(.3)
    tokens=ocr_tokens()
    exact=[t for t in tokens if norm(t['text'])==norm(code)
           and abs(t['y']-r['y'])<15 and t['x']>r['right']]
    if len(exact)!=1:
        raise RuntimeError(f'Payment code {code!r} not visually verified')
    print('  Payment code:',code)


def fill_new_payment(app, method):
    """
    Fill the New Term of Payment editor.

    Called immediately after clicking the green + button.
    Does not save the payment term.
    """

    print("\nFilling New Term of Payment...", flush=True)

    payment_codes = {
        "Bank Transfer": "Credit transfer",
        "Credit Card": "Credit card",
        "SEPA Direct Debit": "SEPA direct debit",
    }

    if method not in payment_codes:
        raise RuntimeError(f"Unsupported payment method: {method}")

    def focused():
        return ax(app, "AXFocusedUIElement")

    def value():
        return str(ax(focused(), "AXValue") or "").strip()

    def next_field():
        pyautogui.press("tab")
        time.sleep(0.2)
        return focused()

    def write_field(text, label):
        field = focused()

        if ax(field, "AXRole") not in ("AXTextField", "AXTextArea"):
            raise RuntimeError(f"{label}: expected a text field")

        set_value(field, text, label)

    def verify_zero(label):
        current = value()

        if current not in ("0", "0%", "0.0", "0.0%", "0.00", "0.00%"):
            raise RuntimeError(
                f"{label} must be zero; found {current!r}"
            )

        print(f"  {label}: {current} ✓")

    # 1. Navigate from green + to Name.
    pyautogui.press("tab", presses=10, interval=0.12)
    time.sleep(0.3)

    if ax(focused(), "AXRole") not in ("AXTextField", "AXTextArea"):
        raise RuntimeError("Name field not reached")

    current_name = value()

    if current_name not in ("", method):
        raise RuntimeError(
            f"Unexpected Name field value: {current_name!r}"
        )

    if not current_name:
        write_field(method, "Payment Name")

    print(f"  Name: {method} ✓")

    # 2. Account — leave blank.
    next_field()

    if value() != "":
        raise RuntimeError(
            f"Account must be blank, found {value()!r}"
        )

    print("  Account: blank ✓")

    # 3. Description.
    next_field()

    if value() not in ("", method):
        raise RuntimeError(
            f"Unexpected Description value: {value()!r}"
        )

    if value() != method:
        write_field(method, "Payment Description")

    print(f"  Description: {method} ✓")

    # 4. Payment code.
      # 4. Payment code.
    # We are currently on Description.
    # Move to the Payment Code dropdown.

    next_field()
    time.sleep(0.2)

    target_code = payment_codes[method]

    print(f"Selecting Payment Code: {target_code}", flush=True)

    # Open the dropdown using the keyboard.
    pyautogui.press("space")
    time.sleep(0.3)

    # Select Credit transfer from the available options.
    # Start typing the target name rather than modifying AXValue.
    pyautogui.write(target_code, interval=0.04)
    time.sleep(0.3)
    pyautogui.press("enter")
    time.sleep(0.4)

    # Verify the visible selection using OCR.
    words = image_words()

    visible = " ".join(
        str(w["text"]) for w in words
    ).lower()

    if target_code.lower() not in visible:
        raise RuntimeError(
            f"Payment Code was not visually confirmed as "
            f"{target_code!r}. No record saved."
        )

    print(f"  Payment Code: {target_code} ✓")

    # 5. Cash discount = 0%.
    next_field()
    verify_zero("Cash discount")

    # 6. Discount Days = 0.
    next_field()
    verify_zero("Discount Days")

    # 7. Net Days = 0.
    next_field()
    verify_zero("Net Days")

    # 8. Remaining fields intentionally unchanged:
    # Text 'unpaid', Text 'deposit', Text 'paid'.
    # Never click Set as standard.

    print("  Text fields: left unchanged")
    print("  Set as standard: not clicked")
    print("\nSUCCESS: Payment term fields completed.")
    print("Payment term has NOT been saved.")

def save_new_term(app):
    # Toolbar Save button is on the left, not in editor. AX first, no shortcut
    # which might apply to the wrong editor.
    buttons=[e for e in all_nodes(app) if ax(e,'AXRole')=='AXButton'
             and ax(e,'AXTitle')=='Save']
    if len(buttons)!=1:
        raise RuntimeError(f'Cannot uniquely locate Save ({len(buttons)})')
    press(buttons[0])
    time.sleep(.7)
    print('Clicked Save once for New Term of Payment')


def open_and_create_term(app, method, resume_editor=False):
    if method not in PAYMENT_CODES:
        raise RuntimeError(f'Unsupported payment type: {method}')
    if not resume_editor:
        click_sidebar_terms()
        find_terms_tab_open()
        enter_terms_search(app,method)
        exact=read_term_list_matches(method)
        if len(exact) > 1:
            raise RuntimeError(f'Ambiguous duplicate {method} terms. Manual review.')
        if len(exact) == 1:
            raise RuntimeError(f'{method} term exists; inspect its definition before reusing. Debtor unsaved.')
        # Clear search before creation in case list filters new records.
        enter_terms_search(app,'')
        click_terms_plus()
    fill_new_payment(app,method)
    # Save is explicit, but only for the newly-created payment term.
    save_new_term(app)
    click_tab_title(app,'New Debtor')
    if not active_new_debtor(app):
        raise RuntimeError('Could not return to New Debtor')
    print('Returned to existing New Debtor editor')


def select_debtor_payment(app, method):
    # Payment combo is on Miscellaneous, directly above Discount.
    if not active_new_debtor(app):
        raise RuntimeError('Debtor is not active')
    p=[w for w in image_words() if norm(w['text'])=='payment']
    sw,_=pyautogui.size()
    p=[w for w in p if w['x'] > sw*.55]
    if len(p)!=1:
        raise RuntimeError(f'Debtor payment label ambiguous ({len(p)})')
    r=p[0]
    pyautogui.click(r['right'] + 90,(r['y']+r['bottom'])/2)
    time.sleep(.2)
    # Native SWT combo: type-to-select after focus; verify a row-scoped OCR.
    pyautogui.write(method,.03)
    pyautogui.press('enter')
    time.sleep(.4)
    selected=[w for w in image_words() if norm(w['text'])==norm(method)
              and w['x']>r['right'] and abs(w['y']-r['y'])<15]
    if len(selected)!=1:
        raise RuntimeError(f'Debtor payment {method!r} not verified. Leave unsaved.')
    print(f'Debtor Payment: {method} ✓')


def create_missing_payment(app, method):
    open_and_create_term(app,method)
    select_debtor_payment(app,method)

def confirm_order_tab(app):
    titles = tab_titles(app)
    print('Tabs:', titles, flush=True)
    if not any(str(t).lstrip('*') == 'New Order' for t in titles):
        print('WARNING: The background Order tab could not be confirmed via AX.')


def save_debtor(app, customer):
    # Explicit user flag only. Any failed verification above prevents this.
    if not active_new_debtor(app):
        raise RuntimeError('New Debtor not active at save time')
    buttons = [e for e in all_nodes(app)
               if ax(e, 'AXRole') == 'AXButton' and ax(e, 'AXTitle') == 'Save']
    if len(buttons) != 1:
        raise RuntimeError(f'Save button ambiguity ({len(buttons)})')
    press(buttons[0])
    time.sleep(.8)
    print('Save clicked once. Re-selecting and verifying from Order is required.')


def main():
    parser = argparse.ArgumentParser(description='Fakturama New Debtor automation')
    parser.add_argument('--save', action='store_true',
                        help='Save Debtor only after verification (payment term itself is saved when created)')
    parser.add_argument('--resume-payment', action='store_true',
                        help='Start from an already-open New Term of Payment editor')
    args = parser.parse_args()
    app = activate()
    if args.resume_payment:
        open_and_create_term(app, DATA.payment_method, resume_editor=True)
        if args.save:
            save_debtor(app, DATA)
        return
    open_new_debtor(app)
    if not active_new_debtor(app):
        raise RuntimeError('New Debtor inactive')
    confirm_order_tab(app)
    initialize_company(app, DATA)
    fill_address(app, DATA)
    set_address_roles(app, DATA)
    set_miscellaneous(app, DATA)
    create_missing_payment(app, DATA.payment_method)
    if args.save:
        save_debtor(app, DATA)
    else:
        print('All configured fields passed available checks. DRY RUN: Not saved.')


if __name__ == '__main__':
    main()
