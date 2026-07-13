"""
frame_types.py
==============
Single source of truth for classifying the `frame_type` input into one of the
four ACI 318-25 design regimes handled by the checker:

    SMF     — Special moment frame        (ACI 18.7 / 18.8)
    IMF     — Intermediate moment frame   (ACI 18.4)
    OMF     — Ordinary moment frame       (ACI 18.3)
    GRAVITY — Not part of the SFRS        (ACI 18.14, SDC D/E/F)

Any unrecognized or blank value defaults to SMF (the most demanding regime).
"""
from __future__ import annotations

from typing import Dict

SMF = 'SMF'
IMF = 'IMF'
OMF = 'OMF'
GRAVITY = 'GRAVITY'


def frame_class(row: Dict[str, object]) -> str:
    text = str(row.get('frame_type', '')).strip().upper()
    if text.startswith('G'):
        return GRAVITY
    if text.startswith('I'):
        return IMF
    if text.startswith('O'):
        return OMF
    return SMF


def is_smf(row: Dict[str, object]) -> bool:
    return frame_class(row) == SMF


def is_imf(row: Dict[str, object]) -> bool:
    return frame_class(row) == IMF


def is_omf(row: Dict[str, object]) -> bool:
    return frame_class(row) == OMF


def is_gravity(row: Dict[str, object]) -> bool:
    return frame_class(row) == GRAVITY
