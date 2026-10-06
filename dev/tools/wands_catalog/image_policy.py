"""Shared measurement-free image contract. Product specifications stay untouched."""
from __future__ import annotations

import re

VERSION = 'measurement-free-v1'
NO_MEASUREMENTS = (
    'No visible measurements, text, letters, numerals, units, size labels, dimension lines, '
    'arrows, tick marks, scales, rulers, tape measures, calipers, diagrams, charts, captions, '
    'logos, watermarks or annotated packaging. No markings on the product, background, '
    'props or image border. This is an unannotated product photograph.'
)
NUMBER = r'(?:\d+(?:\.\d+)?(?:\s+\d+/\d+)?|\d+/\d+)'
UNIT = r'(?:inches|inch|in\.?|feet|foot|ft\.?|yards|yard|yd|centimeters?|centimetres?|cm|millimeters?|millimetres?|mm|meters?|metres?|m|ounces?|oz|pounds?|lbs?|kg|grams?|g|liters?|litres?|ml|gallons?|gal|quarts?|qt|watts?|watt|volts?|volt|degrees?|°[CF]?|["\u2033\u201d\u2032\u2019\x27])'
MEASUREMENT = re.compile(rf'(?<![\w.])(?:[LWHDR]\s*)?{NUMBER}\s*(?:[-x×]\s*{NUMBER}\s*)*{UNIT}(?![a-z])(?:\s*\.?\s*[LWHD](?![a-z]))?', re.I)
HYPHENATED_MEASUREMENT = re.compile(rf'(?<![\w.]){NUMBER}\s*[-\u2010\u2011]\s*{UNIT}(?![a-z])',re.I)
UNITLESS_DIMENSIONS = re.compile(rf'(?<!\w){NUMBER}(?:\s*[x×]\s*{NUMBER}){{1,3}}(?!\w)', re.I)
DIAGRAM_REQUEST = re.compile(r'\b(?:prepare|create|draw|render|include|show)\b[^.!?\n]{0,90}\b(?:dimension diagram|dimension labels|visible label|measurement chart)\b', re.I)


def visual_text(value: object) -> str:
    """Remove measurement strings, not component counts or catalog attributes."""
    text = str(value)
    text = MEASUREMENT.sub('', text)
    text = UNITLESS_DIMENSIONS.sub('', text)
    # Component quantities use "8 x Fork"; retain that structural instruction.
    text = re.sub(r'\s+', ' ', text).strip(' ,;.')
    return text


def product_prompt(body: str) -> str:
    if DIAGRAM_REQUEST.search(body):
        raise ValueError('Measurement diagrams and visible labels are forbidden')
    # Prompt-only cleanup preserves normalization of frozen catalog briefs.
    clean = visual_text(HYPHENATED_MEASUREMENT.sub('',body.replace(NO_MEASUREMENTS, '')))
    return clean + '. ' + NO_MEASUREMENTS


def validate_prompt(prompt: str, view: str | None = None) -> None:
    if view in {'dimensions', 'dimension', 'diagram', 'measurement'}:
        raise ValueError('Measurement image views are retired')
    if not isinstance(prompt, str) or NO_MEASUREMENTS not in prompt:
        raise ValueError('Image prompt lacks the current measurement-free policy; rebuild its queue')
    body = prompt.replace(NO_MEASUREMENTS, '')
    if MEASUREMENT.search(body) or UNITLESS_DIMENSIONS.search(body) or DIAGRAM_REQUEST.search(body):
        raise ValueError('Image prompt contains measurement instructions; rebuild its queue')


class GuardedImageModel:
    """Enforce policy even when an old queue reaches a generation entry point."""
    def __init__(self, model):
        self.model = model

    def generate_image(self, *args, **kwargs):
        validate_prompt(kwargs.get('prompt'))
        return self.model.generate_image(*args, **kwargs)

    def __getattr__(self, name):
        return getattr(self.model, name)
