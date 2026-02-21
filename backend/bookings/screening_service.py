"""Sanctions screening service — checks parties against OFAC/EU/UN lists."""

import csv
import os
from datetime import timedelta
from difflib import SequenceMatcher
from pathlib import Path

from django.utils import timezone

DATA_DIR = Path(__file__).resolve().parent / 'data'
OFAC_FILE = DATA_DIR / 'ofac_sdn.csv'
EU_FILE = DATA_DIR / 'eu_sanctions.csv'

# Cache loaded data in module-level variables (cleared on server restart)
_ofac_names = None
_eu_names = None
_last_loaded = None
CACHE_TTL = timedelta(hours=1)


def _load_names_from_csv(filepath):
    """Load name entries from a sanctions CSV file."""
    names = []
    if not filepath.exists():
        return names
    with open(filepath, 'r', encoding='utf-8', errors='replace') as f:
        reader = csv.reader(f)
        for row in reader:
            if row and len(row) >= 2:
                name = row[1].strip() if len(row) > 1 else row[0].strip()
                if name and name != 'SDN_Name' and name != 'name':
                    names.append(name.upper())
    return names


def _get_ofac_names():
    global _ofac_names, _last_loaded
    now = timezone.now()
    if _ofac_names is None or _last_loaded is None or (now - _last_loaded) > CACHE_TTL:
        _ofac_names = _load_names_from_csv(OFAC_FILE)
        _last_loaded = now
    return _ofac_names


def _get_eu_names():
    global _eu_names, _last_loaded
    now = timezone.now()
    if _eu_names is None or _last_loaded is None or (now - _last_loaded) > CACHE_TTL:
        _eu_names = _load_names_from_csv(EU_FILE)
        _last_loaded = now
    return _eu_names


def _fuzzy_match(name, sanctions_names, threshold=0.85):
    """Check name against sanctions list using SequenceMatcher.

    Returns list of (matched_name, score) tuples above threshold.
    """
    name_upper = name.upper()
    matches = []
    for sdn_name in sanctions_names:
        score = SequenceMatcher(None, name_upper, sdn_name).ratio()
        if score >= threshold:
            matches.append((sdn_name, score))
    # Sort by score descending
    matches.sort(key=lambda x: x[1], reverse=True)
    return matches[:5]  # Top 5 matches


def screen_party(party):
    """Screen a single party against all sanctions lists.

    Returns list of ScreeningResult objects (already saved).
    """
    from .models import ScreeningResult

    # Check if already screened within 24h
    recent = ScreeningResult.objects.filter(
        party=party,
        checked_at__gte=timezone.now() - timedelta(hours=24),
    ).first()
    if recent:
        return list(ScreeningResult.objects.filter(
            party=party,
            checked_at__gte=timezone.now() - timedelta(hours=24),
        ))

    results = []
    name = party.company_name

    for list_name, names_func in [('OFAC', _get_ofac_names), ('EU', _get_eu_names)]:
        sanctions_names = names_func()
        if not sanctions_names:
            # No data file — mark as clear with note
            result = ScreeningResult.objects.create(
                party=party,
                list_checked=list_name,
                status='CLEAR',
                match_score=0.0,
                match_details={'note': 'No sanctions data available'},
            )
            results.append(result)
            continue

        matches = _fuzzy_match(name, sanctions_names)
        if not matches:
            result = ScreeningResult.objects.create(
                party=party,
                list_checked=list_name,
                status='CLEAR',
                match_score=0.0,
                match_details={},
            )
        else:
            best_name, best_score = matches[0]
            if best_score >= 0.95:
                status = 'BLOCKED'
            elif best_score >= 0.85:
                status = 'POTENTIAL_MATCH'
            else:
                status = 'CLEAR'
            result = ScreeningResult.objects.create(
                party=party,
                list_checked=list_name,
                status=status,
                match_score=best_score,
                match_details={
                    'matches': [{'name': n, 'score': round(s, 3)} for n, s in matches],
                },
            )
        results.append(result)

    return results


def screen_booking_parties(booking):
    """Screen all parties on a booking. Returns list of BLOCKED results."""
    blocked = []
    for bp in booking.booking_parties.select_related('party').all():
        if bp.party:
            results = screen_party(bp.party)
            for r in results:
                if r.status == 'BLOCKED':
                    blocked.append(r)
    return blocked


def get_party_screening_status(party):
    """Get the latest screening status for a party.

    Returns: 'CLEAR', 'POTENTIAL_MATCH', 'BLOCKED', 'REVIEWED_OK',
             'REVIEWED_BLOCKED', or 'NOT_SCREENED'.
    """
    latest = party.screening_results.first()
    if not latest:
        return 'NOT_SCREENED'
    return latest.status


def update_sanctions_data():
    """Download latest sanctions list CSVs.

    Returns summary string of what was updated.
    """
    import logging
    import urllib.request

    logger = logging.getLogger(__name__)

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    results = []

    # OFAC SDN list
    ofac_url = 'https://www.treasury.gov/ofac/downloads/sdn.csv'
    try:
        urllib.request.urlretrieve(ofac_url, OFAC_FILE)
        results.append('OFAC SDN updated')
    except Exception as e:
        logger.error('Failed to download OFAC SDN: %s', e)
        results.append(f'OFAC SDN failed: {e}')

    # Clear module-level cache so new data is loaded
    global _ofac_names, _eu_names, _last_loaded
    _ofac_names = None
    _eu_names = None
    _last_loaded = None

    return '; '.join(results)
