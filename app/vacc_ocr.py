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
    import tempfile, os as _os
    tmp_path = None
    try:
        import pytesseract
        from PIL import Image, ImageOps
        pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

        # HEIC/HEIF support — register opener if pillow-heif is installed
        suffix = str(image_path).lower()
        if suffix.endswith('.heic') or suffix.endswith('.heif'):
            try:
                from pillow_heif import register_heif_opener
                register_heif_opener()
            except ImportError:
                logger.warning('pillow-heif not installed; HEIC files may not open correctly')

        img = Image.open(image_path)
        # Apply EXIF rotation (phone photos are often stored sideways)
        img = ImageOps.exif_transpose(img)
        # Flatten any mode Tesseract can't handle — always target RGB
        if img.mode != 'RGB':
            img = img.convert('RGB')
        # Save to a temp PNG so Tesseract gets a clean, unambiguous file
        with tempfile.NamedTemporaryFile(suffix='.png', delete=False) as tmp:
            tmp_path = tmp.name
        img.save(tmp_path, 'PNG')
        text = pytesseract.image_to_string(tmp_path, config='--psm 6')
        return text
    except Exception as e:
        logger.error(f'OCR image error: {e}')
        return ''
    finally:
        if tmp_path:
            try:
                _os.unlink(tmp_path)
            except Exception:
                pass


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

    # DD-Mon-YYYY with hyphens (e.g. "14-Oct-2025", "25-Jul-2026")
    m = re.match(
        r'^(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d{4})$',
        s, re.IGNORECASE
    )
    if m:
        mo = MONTH_MAP.get(m.group(2).lower())
        if mo:
            try:
                return date(int(m.group(3)), mo, int(m.group(1)))
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

    # ISO dates: YYYY-MM-DD (must come BEFORE the MM/DD/YYYY pattern to avoid partial matches)
    for m in re.finditer(r'\b(20\d{2})[/\-](\d{1,2})[/\-](\d{1,2})\b', text):
        if m.start() in seen_positions:
            continue
        d = _parse_date(m.group(0))
        if d:
            results.append((m.start(), d))
            seen_positions.add(m.start())

    # Numeric dates: MM/DD/YYYY, M/D/YYYY, M/D/YY
    for m in re.finditer(r'\b(\d{1,2})[/\-](\d{1,2})[/\-](\d{2,4})\b', text):
        if m.start() in seen_positions:
            continue
        raw = m.group(0)
        d = _parse_date(raw)
        if d:
            results.append((m.start(), d))
            seen_positions.add(m.start())

    # DD-Mon-YYYY hyphenated (e.g. "14-Oct-2025")
    for m in re.finditer(
        r'\b(\d{1,2})-(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)-(\d{4})\b',
        text, re.IGNORECASE
    ):
        if m.start() in seen_positions:
            continue
        mo = MONTH_MAP.get(m.group(2).lower())
        if mo:
            try:
                d = date(int(m.group(3)), mo, int(m.group(1)))
                results.append((m.start(), d))
                seen_positions.add(m.start())
            except ValueError:
                pass

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


def _is_dual_table_cert(text):
    """
    Detect certificates that have TWO separate tables:
      1. Treatment table with 'Date Given' and 'Expiration Date' (vaccine lot expiry)
      2. A separate 'Due Date' section listing when the next vaccination is due.
    Example: Cobb County Animal Services Rabies Certificate.
    The 'Expiration Date' in table 1 is the lot/product expiry — NOT what we want.
    The 'Due Date' in table 2 is when the vaccination needs to be renewed — what we want.
    """
    tl = text.lower()
    has_expiration_col = bool(re.search(r'expir(?:ation|y)?\s*date', tl))
    has_due_date       = bool(re.search(r'due\s*date', tl))
    has_date_given     = bool(re.search(r'date\s*given', tl))
    return has_expiration_col and has_due_date and has_date_given


def _parse_dual_table_cert(text):
    """
    Parse dual-table certificates (e.g. Cobb County Rabies Certificate).
    - Reads vaccine names and Due Dates from the 'Due Date' section (bottom table).
    - Reads the vaccination date (Date Given) from the top treatment table.
    - Deliberately ignores the 'Expiration Date' column (that is the lot expiry, not the
      renewal due date).
    """
    results = []
    today   = date.today()
    lines   = text.split('\n')

    # ── Step 1: Pull vaccination_date (Date Given) from top table ─────────────
    # Find first past date on a line that also contains a vaccine name or "date given"
    given_date = None
    in_treatment_table = False
    for line in lines:
        if re.search(r'date\s*given|vet\s*treatment\s*type', line, re.IGNORECASE):
            in_treatment_table = True
        if re.search(r'due\s*date', line, re.IGNORECASE):
            in_treatment_table = False   # switched to bottom section
        if in_treatment_table:
            for _, d in _extract_all_dates(line):
                if d <= today:
                    given_date = d
                    break
        if given_date:
            break

    # ── Step 2: Locate the Due Date section and parse it ──────────────────────
    # Find the line that acts as the Due Date table header, then read rows below it
    due_header_idx = None
    for i, line in enumerate(lines):
        if re.search(r'due\s*date', line, re.IGNORECASE) and re.search(r'vet\s*treatment', line, re.IGNORECASE):
            due_header_idx = i
            break
    # Fallback: first line that contains only "Due Date"
    if due_header_idx is None:
        for i, line in enumerate(lines):
            if re.search(r'^\s*due\s*date\s*$', line, re.IGNORECASE):
                due_header_idx = i
                break

    if due_header_idx is None:
        return results

    # Parse rows after the Due Date header
    for line in lines[due_header_idx + 1:]:
        stripped = line.strip()
        if not stripped or len(stripped) < 4:
            continue
        # Stop at next blank section or signature block
        if re.search(r'vet\s*signature|date\s*:', stripped, re.IGNORECASE):
            break

        vaccine = _match_vaccine_name(stripped)
        if not vaccine:
            continue

        dates = _extract_all_dates(stripped)
        expiry = None
        for _, d in dates:
            if d > today:
                expiry = d
                break
        # Accept any date if all are past (shouldn't happen on a valid cert, but be safe)
        if not expiry and dates:
            expiry = dates[-1][1]

        results.append({
            'vaccine_name':     vaccine,
            'vaccination_date': given_date,
            'expiration_date':  expiry,
            'confidence':       'high' if expiry else 'low',
        })

    return results


def _is_two_column_format(text):
    """
    Detect records with explicit last-given + due-date columns (Banfield/bhere style).
    """
    tl = text.lower()
    return bool(re.search(r'last\s*date\s*given|date\s*vaccinated', tl))


def _is_vip_petcare_format(text):
    """
    Detect VIP Petcare / PetVet 'Official Summary of Visit' PDFs.
    These have labeled rows: 'Name <vaccine>', 'Due Date YYYY-MM-DD' on separate lines.
    """
    tl = text.lower()
    return bool(
        re.search(r'vip.?petcare|petvet|official summary of visit|tractor supply', tl) or
        (re.search(r'\bdue date\b', tl) and
         re.search(r'20\d\d-\d\d-\d\d', tl) and
         re.search(r'canine vaccines|vaccinations', tl, re.IGNORECASE))
    )


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


def _parse_vip_petcare(text):
    """
    Parse VIP Petcare / PetVet 'Official Summary of Visit' PDFs.
    Each vaccine block has labeled rows:
        Name Bordetella Oral - NOBIVAC INTRA-TRAC Oral
        Quantity 1
        Due Date 2027-07-05
        Category Vaccinations
    Strategy: find 'Name <vaccine text>' lines, then look ahead up to 6 lines
    for 'Due Date YYYY-MM-DD'. Visit date pulled from 'Date: YYYY-MM-DD' field.
    Skip non-vaccine Name lines (Pet Name, Vitals Check, Rabies Tag, packages).
    """
    results = []

    # Extract visit date from "Date: YYYY-MM-DD" near the top of the doc
    visit_date = None
    vm = re.search(r'\bDate:\s*(20\d{2}-\d{2}-\d{2})\b', text)
    if vm:
        visit_date = _parse_date(vm.group(1))

    _SKIP_NAMES = re.compile(
        r'pet\s*name|vitals\s*check|rabies\s*tag|total\s*health\s*package|'
        r'generic\s*rabies|package\s*only|for\s*package',
        re.IGNORECASE,
    )

    lines = text.split('\n')
    seen_vaccines = set()

    for i, line in enumerate(lines):
        line = line.strip()
        # Match lines like "Name Bordetella Oral - ..."
        name_m = re.match(r'^Name\s+(.+)$', line, re.IGNORECASE)
        if not name_m:
            continue
        vaccine_text = name_m.group(1).strip()
        if _SKIP_NAMES.search(vaccine_text):
            continue
        vaccine = _match_vaccine_name(vaccine_text)
        if not vaccine:
            continue
        if vaccine in seen_vaccines:
            continue

        # Look ahead up to 6 lines for "Due Date YYYY-MM-DD"
        due_date = None
        for j in range(i + 1, min(i + 7, len(lines))):
            due_m = re.match(r'^Due\s*Date\s+(20\d{2}-\d{2}-\d{2})', lines[j].strip(), re.IGNORECASE)
            if due_m:
                due_date = _parse_date(due_m.group(1))
                break
            # Stop at next "Name" line
            if re.match(r'^Name\s+', lines[j].strip(), re.IGNORECASE):
                break

        seen_vaccines.add(vaccine)
        results.append({
            'vaccine_name':     vaccine,
            'vaccination_date': visit_date,
            'expiration_date':  due_date,
            'confidence':       'high' if due_date else 'low',
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
    # Matches headers like:
    #   "Reminders\n"                   (simple)
    #   "Reminders for: Charlie ...\n"  (Guyton Animal Hospital / invoice style)
    reminder_section = re.search(
        r'reminder[s]?(?:\s+for\s*:[^\n]*)?\s*\n(.*?)(?:\n\s*\n|\Z)',
        text, re.IGNORECASE | re.DOTALL
    )
    if reminder_section:
        reminder_text = reminder_section.group(1)
        lines = reminder_text.split('\n')
        last_reminder_date = None
        for line in lines:
            if len(line.strip()) < 4:
                continue
            # Skip the "Last done" column header line
            if re.search(r'last\s*done', line, re.IGNORECASE):
                continue

            dates_on_line = _extract_all_dates(line)
            vaccine = _match_vaccine_name(line)

            if not vaccine:
                # Update carry-forward date even on non-vaccine lines
                if dates_on_line:
                    last_reminder_date = dates_on_line[0][1]
                continue

            if len(dates_on_line) >= 2:
                # Two-date format: "DUE_DATE  Vaccine Name  LAST_DONE_DATE"
                # Determine which date is future (due/expiry) and which is past (given)
                d0, d1 = dates_on_line[0][1], dates_on_line[1][1]
                today = date.today()
                if d0 >= today and d1 <= today:
                    expiry, given = d0, d1
                elif d1 >= today and d0 <= today:
                    expiry, given = d1, d0
                else:
                    # Both future or both past — first is due, second is last done
                    expiry, given = (d0, d1) if d0 > d1 else (d1, d0)
                last_reminder_date = expiry
            elif len(dates_on_line) == 1:
                d = dates_on_line[0][1]
                today = date.today()
                expiry = d if d > today else last_reminder_date
                given  = d if d <= today else visit_date
                last_reminder_date = expiry or last_reminder_date
            else:
                expiry = last_reminder_date
                given  = visit_date

            results.append({
                'vaccine_name':     vaccine,
                'vaccination_date': given,
                'expiration_date':  expiry,
                'confidence':       'high' if expiry else 'low',
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
    elif suffix in ('.jpg', '.jpeg', '.png', '.bmp', '.tiff', '.tif', '.webp', '.heic', '.heif'):
        text = _ocr_image(path)
    else:
        logger.warning(f'Unsupported file type: {suffix}')
        return []

    if not text.strip():
        logger.warning('OCR returned no text')
        return []

    logger.debug(f'OCR extracted text ({len(text)} chars):\n{text[:500]}')

    # ── Classify document type and route to appropriate parser ────────────────
    if _is_vip_petcare_format(text):
        logger.info('Document classified as: VIP Petcare / PetVet summary')
        results = _parse_vip_petcare(text)

    elif _is_single_vaccine_cert(text):
        logger.info('Document classified as: single vaccine certificate')
        results = _parse_single_cert(text)

    elif _is_invoice_format(text):
        logger.info('Document classified as: invoice/receipt')
        results = _parse_invoice_format(text)

    elif _is_dual_table_cert(text):
        logger.info('Document classified as: dual-table cert (Date Given + separate Due Date section)')
        results = _parse_dual_table_cert(text)

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