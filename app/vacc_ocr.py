"""
vacc_ocr.py — OCR extraction for vaccination records.
Extracts vaccine names, dates administered, and expiration dates
from uploaded images or PDFs.

Handles formats from:
  - Standard vaccination certificates (Pooler Vet, Port City, Rice Hope)
  - Boarder/groomer export PDFs (Banfield/bhere)
  - Vet invoice/receipt PDFs with embedded vaccine line items
  - Reminder-only formats where only expiry dates are present
  - Single-vaccine rabies certificates
  - Photo-based vaccination reminder cards

Place at: C:\\RuffLifeRetreat\\app\\vacc_ocr.py
"""

import re
import logging
from datetime import datetime, date
from pathlib import Path

logger = logging.getLogger(__name__)

TESSERACT_CMD = r'C:\Program Files\Tesseract-OCR\tesseract.exe'
POPPLER_PATH  = r'C:\poppler\poppler-26.02.0\Library\bin'

# ── Vaccine name patterns ─────────────────────────────────────────────────────
# Each entry: (regex, canonical_name)
# Order matters — more specific patterns first
VACCINE_PATTERNS = [
    # Rabies
    (r'\brabies\b',                                          'Rabies'),

    # DHPP / DAPP family — many aliases
    (r'\bdhpp\b|\bdhlpp\b|\bda2pp\b|\bda2ppv\b',            'DHPP'),
    (r'\bdapp\b|\bdappv\b|\bdappv\+l4\b|\bdapp\+l4\b',      'DAPP'),
    (r'\bdistemper[/ ]adeno[- ]?2[/ ]parvo\b',              'DHPP'),
    (r'\bdistemper[/ ]adenoviru',                            'DHPP'),
    (r'\bdistemper\b',                                       'Distemper/Parvo'),
    (r'\bparvo(?:virus)?\b',                                 'Distemper/Parvo'),

    # Bordetella
    (r'\bbordet(?:e|a)lla\b',                                'Bordetella'),
    (r'\bkennel\s*cough\b',                                  'Bordetella'),
    (r'\bbordet(?:e|a)lla\s*(?:&|and|bi-?annual|intra\s*nasal|oral|bi\s*annual)?\b', 'Bordetella'),

    # Leptospirosis
    (r'\blepto(?:spirosis)?\b|\blepto\s*4\b|\blepto4\b',     'Leptospirosis'),

    # Influenza
    (r'\binfluenza\b|\bcanine\s*flu\b',                      'Influenza'),

    # Lyme
    (r'\blyme\b',                                            'Lyme'),

    # Parainfluenza (standalone — usually bundled in DHPP)
    (r'\bparainfluenza\b',                                   'Parainfluenza'),
]

# ── Items that look like vaccines but are NOT — exclude from results ──────────
NON_VACCINE_KEYWORDS = [
    r'\bheartworm\s*(prevention|test|screening|antigen|check)\b',
    r'\bfecal\b',
    r'\bintestinal\s*parasite\b',
    r'\bparasite\s*(screen|test|control)\b',
    r'\bwellness\s*(exam|package|blood|profile)\b',
    r'\bcbc\b',
    r'\bchem\b',
    r'\bbravecto\b',          # flea/tick preventative
    r'\bsimparica\b',         # flea/tick preventative
    r'\bnexgard\b',           # flea/tick preventative
    r'\bproheart\b',          # heartworm injectable — not a vaccine
    r'\bdental\b',
    r'\bmicrochip\b',
    r'\bexamination\b',
    r'\bbloodwork\b',
    r'\bidexx\b',
    r'\bunited\s*states\b',
    r'\bsuite\b',
    r'\bparkway\b',
    r'\bhighway\b',
    r'\bpharmacy\b',
    r'\bpyrantel\b',
    r'\bdewormer\b',
    r'\bflea\b',
    r'\btick\b',
    r'\bhookworm\b',
    r'\broundworm\b',
]

# ── Column header → semantic meaning ─────────────────────────────────────────
# Used to decide whether a date column contains given-dates or expiry-dates
EXPIRY_HEADER_PATTERNS = [
    r'date\s*due',
    r'due\s*date',
    r'date\s*expires',
    r'expir(?:es|ation|y)',
    r'next\s*(?:vaccine\s*)?due',
    r'valid\s*(?:through|until)',
    r'current\s*until',
    r'reminders?',
]

GIVEN_HEADER_PATTERNS = [
    r'date\s*(?:given|vaccinated|administered|of\s*vaccination)',
    r'last\s*date\s*given',
    r'vaccination\s*date',
    r'date\s*vaccinated',
    r'administered',
]

# ── Date patterns ─────────────────────────────────────────────────────────────
DATE_PATTERNS = [
    # MM/DD/YYYY or M/D/YYYY
    r'\b(\d{1,2})[/\-](\d{1,2})[/\-](20\d{2})\b',
    # Month DD, YYYY (e.g. "March 27, 2026")
    r'\b(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{1,2}),?\s+(20\d{2})\b',
    # DD Month YYYY
    r'\b(\d{1,2})\s+(January|February|March|April|May|June|July|August|September|October|November|December)\s+(20\d{2})\b',
    # Abbreviated month: Jan 20, 2026
    r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(20\d{2})\b',
    # YYYY-MM-DD (ISO)
    r'\b(20\d{2})[/\-](\d{1,2})[/\-](\d{1,2})\b',
    # M/D/YY short year (e.g. 1/20/26) — treat as 20xx
    r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})\b',
]

MONTH_MAP = {
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
    'jan': 1, 'feb': 2, 'mar': 3, 'apr': 4,
    'jun': 6, 'jul': 7, 'aug': 8, 'sep': 9, 'oct': 10, 'nov': 11, 'dec': 12,
}


# ── Internal helpers ──────────────────────────────────────────────────────────

def _ocr_image(image_path):
    try:
        import pytesseract
        from PIL import Image
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
        img = Image.open(image_path)
        # pytesseract only handles 1, L, RGB, RGBA — convert anything else (e.g. CMYK, P)
        if img.mode not in ('1', 'L', 'RGB', 'RGBA'):
            img = img.convert('RGB')
        text = pytesseract.image_to_string(img, config='--psm 6')
        return text
    except Exception as e:
        logger.error(f'OCR image error: {e}')
        return ''


def _ocr_pdf(pdf_path):
    try:
        from pdf2image import convert_from_path
        pages = convert_from_path(str(pdf_path), dpi=200, poppler_path=POPPLER_PATH)
        text_parts = []
        for page in pages:
            import pytesseract
            pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD
            if page.mode not in ('1', 'L', 'RGB', 'RGBA'):
                page = page.convert('RGB')
            text_parts.append(pytesseract.image_to_string(page, config='--psm 6'))
        return '\n'.join(text_parts)
    except Exception as e:
        logger.error(f'OCR PDF error: {e}')
        return ''


def _parse_date(s):
    """
    Try to parse a date string into a date object.
    Handles MM/DD/YYYY, Month DD YYYY, abbreviated months, ISO, short year.
    Returns None on failure.
    """
    s = s.strip()

    # MM/DD/YYYY or M/D/YYYY
    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](20\d{2})$', s)
    if m:
        try:
            return date(int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass

    # M/D/YY (short year — treat as 2000+)
    m = re.match(r'^(\d{1,2})[/\-](\d{1,2})[/\-](\d{2})$', s)
    if m:
        try:
            return date(2000 + int(m.group(3)), int(m.group(1)), int(m.group(2)))
        except ValueError:
            pass

    # Month DD, YYYY or Month DD YYYY
    m = re.match(
        r'^(January|February|March|April|May|June|July|August|September|October|November|December|'
        r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(20\d{2})$',
        s, re.IGNORECASE
    )
    if m:
        mo = MONTH_MAP.get(m.group(1).lower())
        if mo:
            try:
                return date(int(m.group(3)), mo, int(m.group(2)))
            except ValueError:
                pass

    # ISO: YYYY-MM-DD
    m = re.match(r'^(20\d{2})[/\-](\d{1,2})[/\-](\d{1,2})$', s)
    if m:
        try:
            return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
        except ValueError:
            pass

    return None


def _extract_all_dates(text):
    """
    Find every date-like string in the text.
    Returns list of (position, date_object).
    """
    results = []
    seen_positions = set()

    # Numeric dates: MM/DD/YYYY, M/D/YYYY, M/D/YY
    for m in re.finditer(r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\b', text):
        if m.start() in seen_positions:
            continue
        raw = m.group(0)
        d = _parse_date(raw)
        if d:
            results.append((m.start(), d))
            seen_positions.add(m.start())

    # Month-name dates
    month_re = (
        r'\b(January|February|March|April|May|June|July|August|September|October|November|December|'
        r'Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)\.?\s+(\d{1,2}),?\s+(20\d{2})\b'
    )
    for m in re.finditer(month_re, text, re.IGNORECASE):
        if m.start() in seen_positions:
            continue
        d = _parse_date(m.group(0))
        if d:
            results.append((m.start(), d))
            seen_positions.add(m.start())

    results.sort(key=lambda x: x[0])
    return results


def _is_non_vaccine(text):
    """Return True if the text matches a non-vaccine keyword (medication, test, etc.)."""
    tl = text.lower()
    for pattern in NON_VACCINE_KEYWORDS:
        if re.search(pattern, tl):
            return True
    return False


def _match_vaccine_name(text):
    """
    Try to match a canonical vaccine name from raw text.
    Returns canonical name string or None.
    """
    tl = text.lower()
    # First check if it's explicitly a non-vaccine item
    if _is_non_vaccine(tl):
        return None
    for pattern, canonical in VACCINE_PATTERNS:
        if re.search(pattern, tl, re.IGNORECASE):
            return canonical
    return None


def _classify_column_header(header_text):
    """
    Given a column header string, return 'given', 'expiry', or 'unknown'.
    """
    tl = header_text.lower()
    for p in EXPIRY_HEADER_PATTERNS:
        if re.search(p, tl):
            return 'expiry'
    for p in GIVEN_HEADER_PATTERNS:
        if re.search(p, tl):
            return 'given'
    return 'unknown'


# ── Document structure detectors ─────────────────────────────────────────────

def _is_reminder_only_format(text):
    """
    Detect documents that only have reminder/due dates (no given date column).
    Examples: Pooler Vet certificate, Waffles-style reminder card.
    """
    tl = text.lower()
    has_due = bool(re.search(r'date\s*due|due\s*date|current\s*until|reminders?', tl))
    has_given = bool(re.search(r'date\s*(given|vaccinated|administered)|last\s*date\s*given|vaccination\s*date', tl))
    return has_due and not has_given


def _is_invoice_format(text):
    """
    Detect vet invoice/receipt format — has billing line items.
    """
    tl = text.lower()
    return bool(re.search(r'invoice|receipt|subtotal|amount\s*(paid|remaining)|payment\s*history', tl))


def _is_two_column_format(text):
    """
    Detect records with explicit last-given + due-date columns (Banfield/bhere style).
    """
    tl = text.lower()
    return bool(re.search(r'last\s*date\s*given|date\s*vaccinated', tl))


def _is_single_vaccine_cert(text):
    """
    Detect single-vaccine rabies certificates with labeled fields.
    """
    tl = text.lower()
    return bool(
        re.search(r'vaccination\s*date\s*:', tl) and
        re.search(r'next\s*vaccine\s*due|tag\s*(expiration|number)', tl)
    )


# ── Parsing strategies ────────────────────────────────────────────────────────

def _parse_two_column(text):
    """
    Parse records with 'Last date given' + 'Due date' columns (Banfield/bhere).
    Rows look like:
        Leptospirosis     March 27, 2026    March 27, 2027
        Rabies            April 14, 2025    April 14, 2028
    Strategy: find vaccine name + two nearby dates, first = given, second = expiry.
    """
    results = []
    lines = text.split('\n')

    for line in lines:
        # Skip header lines
        if re.search(r'vaccine\s*name|last\s*date|due\s*date', line, re.IGNORECASE):
            continue

        vaccine = _match_vaccine_name(line)
        if not vaccine:
            continue

        # Find all dates in this line
        dates_in_line = _extract_all_dates(line)

        if len(dates_in_line) >= 2:
            given  = dates_in_line[0][1]
            expiry = dates_in_line[1][1]
            results.append({
                'vaccine_name':     vaccine,
                'vaccination_date': given,
                'expiration_date':  expiry,
                'confidence':       'high',
            })
        elif len(dates_in_line) == 1:
            d = dates_in_line[0][1]
            today = date.today()
            results.append({
                'vaccine_name':     vaccine,
                'vaccination_date': d if d <= today else None,
                'expiration_date':  d if d >  today else None,
                'confidence':       'low',
            })

    return results


def _split_columns(line):
    """
    Split a line that may have multiple space-separated columns into segments.
    Splits on 2+ consecutive spaces so each "column" can be evaluated independently.
    """
    return [seg.strip() for seg in re.split(r'  +', line) if seg.strip()]


def _parse_reminder_only(text):
    """
    Parse records where dates are all expiry/due dates — no given date column.
    Formats:
      - "Vaccine Name    1/20/2029"   (name then date)
      - "1/20/2029       Vaccine Name" (date then name — Pooler reminder-style)
      - Two vaccine columns per line (Waffles/Black Creek photo style)
    """
    results = []
    lines = text.split('\n')
    last_seen_date = None  # carry forward for date-less lines (Zoey/invoice reminders)

    for line in lines:
        # Skip obvious header/footer lines
        if re.search(r'vaccine\s*desc|date\s*due|due\s*date|reminder|current\s*until', line, re.IGNORECASE):
            continue
        if len(line.strip()) < 4:
            continue

        # Split multi-column lines (e.g. Waffles image: two vaccines per row)
        segments = _split_columns(line)

        # Update last_seen_date from any date on this full line
        all_dates_on_line = _extract_all_dates(line)
        if all_dates_on_line:
            last_seen_date = all_dates_on_line[-1][1]

        for segment in segments:
            vaccine = _match_vaccine_name(segment)
            if not vaccine:
                continue

            dates_in_seg = _extract_all_dates(segment)
            if dates_in_seg:
                expiry = dates_in_seg[-1][1]
            elif last_seen_date:
                # Date was on the line but in a different segment (e.g. "05/12/2027  Leptospirosis Vaccination")
                expiry = last_seen_date
            else:
                expiry = None

            # DHPP family dedup: 'Distemper/Parvo' is a subset of DHPP/DAPP — skip if already captured
            DHPP_FAMILY = {'DHPP', 'DAPP', 'Distemper/Parvo'}
            if vaccine in DHPP_FAMILY and any(r['vaccine_name'] in DHPP_FAMILY for r in results):
                continue

            if vaccine not in [r['vaccine_name'] for r in results]:
                results.append({
                    'vaccine_name':     vaccine,
                    'vaccination_date': None,
                    'expiration_date':  expiry,
                    'confidence':       'high' if expiry else 'low',
                })

    return results


def _parse_explicit_columns(text):
    """
    Parse records with 'Date Vaccinated' + 'Date Expires' / 'Date Expires' columns.
    Formats: Rice Hope, Port City vaccination record.
    Rows look like:
        12/26/2025   Bordatella Intra Nasal 12 month   12/26/2026
        3/9/2026     DAPPV+L4 Booster     85729   3/9/2029
    Strategy: find rows with vaccine name + two dates in any order.
    """
    results = []
    lines = text.split('\n')

    for line in lines:
        if re.search(r'date\s*vaccinated|date\s*expires|vaccination\s*record|vaccine\b.*\btag\b', line, re.IGNORECASE):
            continue
        if len(line.strip()) < 4:
            continue

        vaccine = _match_vaccine_name(line)
        if not vaccine:
            continue

        dates_in_line = _extract_all_dates(line)
        if len(dates_in_line) >= 2:
            # First date = given, last date = expiry
            given  = dates_in_line[0][1]
            expiry = dates_in_line[-1][1]
            # Sanity check: given should be before expiry
            if given > expiry:
                given, expiry = expiry, given
            results.append({
                'vaccine_name':     vaccine,
                'vaccination_date': given,
                'expiration_date':  expiry,
                'confidence':       'high',
            })
        elif len(dates_in_line) == 1:
            d = dates_in_line[0][1]
            today = date.today()
            results.append({
                'vaccine_name':     vaccine,
                'vaccination_date': d if d <= today else None,
                'expiration_date':  d if d >  today else None,
                'confidence':       'low',
            })

    return results


def _parse_single_cert(text):
    """
    Parse single-vaccine certificates (rabies certs).
    Looks for labeled fields:
      Vaccination Date: 3/9/2026
      Next Vaccine Due By Date: 3/9/2029
    """
    results = []

    # Try to find labeled vaccination date
    given_match = re.search(
        r'(?:vaccination\s*date|date\s*vaccinated|tag\s*issue\s*date)\s*[:\-]?\s*'
        r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
        text, re.IGNORECASE
    )
    expiry_match = re.search(
        r'(?:next\s*vaccine\s*due[\s\w]*|tag\s*expiration\s*date|date\s*expires|expir[^\n]*)\s*[:\-]?\s*'
        r'(\d{1,2}[/\-]\d{1,2}[/\-]\d{2,4})',
        text, re.IGNORECASE
    )

    # Identify the vaccine type
    vaccine = None
    for pattern, canonical in VACCINE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            vaccine = canonical
            break

    if vaccine or given_match or expiry_match:
        given  = _parse_date(given_match.group(1))  if given_match  else None
        expiry = _parse_date(expiry_match.group(1)) if expiry_match else None
        results.append({
            'vaccine_name':     vaccine or '',
            'vaccination_date': given,
            'expiration_date':  expiry,
            'confidence':       'high' if (given and expiry) else 'low',
        })

    return results


def _parse_invoice_format(text):
    """
    Parse vet invoices / receipts.
    Vaccines show up as line items — we capture name + the reminder due dates.
    Strategy:
      1. Scan line items for vaccine names, note the visit date.
      2. Find reminders section and pair vaccine names to their due dates.
    """
    results = []
    today = date.today()

    # Try to find a visit/invoice date (first date mentioned near the top)
    all_dates = _extract_all_dates(text)
    visit_date = None
    for _, d in all_dates:
        if d <= today:
            visit_date = d
            break

    # ── Strategy A: Reminders section ────────────────────────────────────────
    # Match lines like "05/12/2027   Bordetella & PI Oral 1yr"
    # or "Bordetella Vaccine    2/12/2027"
    reminder_section = re.search(r'reminder[s]?\s*\n(.*?)(?:\n\n|\Z)', text, re.IGNORECASE | re.DOTALL)
    if reminder_section:
        reminder_text = reminder_section.group(1)
        lines = reminder_text.split('\n')
        last_reminder_date = None
        for line in lines:
            if len(line.strip()) < 4:
                continue
            # Update last seen date from this line
            dates_on_line = _extract_all_dates(line)
            if dates_on_line:
                last_reminder_date = dates_on_line[-1][1]

            vaccine = _match_vaccine_name(line)
            if not vaccine:
                continue
            # Use date from this line, or carry forward from previous line
            expiry = dates_on_line[-1][1] if dates_on_line else last_reminder_date
            results.append({
                'vaccine_name':     vaccine,
                'vaccination_date': visit_date,
                'expiration_date':  expiry,
                'confidence':       'high' if (visit_date and expiry) else 'low',
            })

    # ── Strategy B: Line items (if reminders didn't produce results) ─────────
    if not results:
        lines = text.split('\n')
        for line in lines:
            if re.search(r'\$\d|\binv\b', line, re.IGNORECASE):
                vaccine = _match_vaccine_name(line)
                if vaccine:
                    results.append({
                        'vaccine_name':     vaccine,
                        'vaccination_date': visit_date,
                        'expiration_date':  None,
                        'confidence':       'low',
                    })

    # De-duplicate by vaccine name, keeping highest confidence
    seen = {}
    for r in results:
        name = r['vaccine_name']
        if name not in seen or (r['confidence'] == 'high' and seen[name]['confidence'] == 'low'):
            seen[name] = r
    return list(seen.values())


def _fallback_parse(text):
    """
    Generic fallback: find all vaccine names and dates, pair by proximity.
    Used when document format can't be classified.
    """
    results = []
    today = date.today()
    all_dates = _extract_all_dates(text)
    past_dates   = [d for _, d in all_dates if d <= today]
    future_dates = [d for _, d in all_dates if d >  today]

    vaccines = []
    for pattern, canonical in VACCINE_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            if canonical not in vaccines:
                vaccines.append(canonical)

    if vaccines:
        for i, vaccine in enumerate(vaccines):
            given  = past_dates[i]   if i < len(past_dates)   else (past_dates[-1]   if past_dates   else None)
            expiry = future_dates[i] if i < len(future_dates) else (future_dates[-1] if future_dates else None)
            results.append({
                'vaccine_name':     vaccine,
                'vaccination_date': given,
                'expiration_date':  expiry,
                'confidence':       'high' if (given and expiry) else 'low',
            })
    elif all_dates:
        results.append({
            'vaccine_name':     '',
            'vaccination_date': past_dates[-1]   if past_dates   else None,
            'expiration_date':  future_dates[0]  if future_dates else None,
            'confidence':       'low',
        })

    return results


# ── Main entry point ──────────────────────────────────────────────────────────

def extract_vaccination_data(file_path):
    """
    Main entry point. Given a path to an uploaded vaccination record
    (image or PDF), returns a list of extracted vaccination dicts:

    [
        {
            'vaccine_name':     'Rabies',
            'vaccination_date': date(2026, 1, 20),   # or None
            'expiration_date':  date(2029, 1, 20),   # or None
            'confidence':       'high' | 'low',
        },
        ...
    ]

    Returns empty list if extraction fails or no data found.
    """
    path = Path(file_path)
    if not path.exists():
        logger.warning(f'File not found: {file_path}')
        return []

    suffix = path.suffix.lower()

    if suffix == '.pdf':
        text = _ocr_pdf(path)
    elif suffix in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp'):
        text = _ocr_image(path)
    else:
        logger.warning(f'Unsupported file type: {suffix}')
        return []

    if not text.strip():
        logger.warning('OCR returned no text')
        return []

    logger.debug(f'OCR extracted text ({len(text)} chars):\n{text[:500]}')

    # ── Classify document type and route to appropriate parser ────────────────
    if _is_single_vaccine_cert(text):
        logger.info('Document classified as: single vaccine certificate')
        results = _parse_single_cert(text)

    elif _is_invoice_format(text):
        logger.info('Document classified as: invoice/receipt')
        results = _parse_invoice_format(text)

    elif _is_two_column_format(text):
        logger.info('Document classified as: two-column (given + due)')
        results = _parse_two_column(text)

    elif _is_reminder_only_format(text):
        logger.info('Document classified as: reminder/due-date-only')
        results = _parse_reminder_only(text)

    else:
        # Try explicit column parser first (Rice Hope / Port City style)
        logger.info('Document classified as: explicit column or unknown — trying column parser')
        results = _parse_explicit_columns(text)
        if not results:
            logger.info('Column parser found nothing — falling back to generic parser')
            results = _fallback_parse(text)

    # ── Post-process: deduplicate, filter empties ─────────────────────────────
    seen = {}
    for r in results:
        name = r['vaccine_name']
        if not name and not r['vaccination_date'] and not r['expiration_date']:
            continue
        if name not in seen:
            seen[name] = r
        else:
            # Prefer high confidence over low
            if r['confidence'] == 'high' and seen[name]['confidence'] == 'low':
                seen[name] = r

    # ── Vaccine name normalisation map ──────────────────────────────────────
    # Merge synonyms so we don't get duplicate entries for the same vaccine
    MERGE_MAP = {
        'Distemper/Parvo': 'DHPP',   # Parvovirus alone → fold into DHPP bucket
    }

    final_before_merge = list(seen.values())
    final = []
    for r in final_before_merge:
        canonical = MERGE_MAP.get(r['vaccine_name'])
        if canonical and any(x['vaccine_name'] == canonical for x in final):
            continue   # already have the preferred name
        if canonical:
            r = dict(r, vaccine_name=canonical)
        final.append(r)
    logger.info(f'OCR extraction complete: {len(final)} vaccine record(s) found')
    return final