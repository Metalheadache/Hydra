"""
Design token system for Hydra document generation tools.

Provides style presets (color palettes, font stacks, number formats, spacing)
that write_docx, write_xlsx, and write_pptx can reference via a `style_preset`
parameter.

Core ships with 5 generic presets.  Add domain-specific presets via
register_preset() or by dropping JSON files in the presets directory.
"""

from __future__ import annotations

import copy
from typing import Any

# ── Document style presets ────────────────────────────────────────────────────

DOCUMENT_PRESETS: dict[str, dict[str, Any]] = {
    "corporate": {
        "primary": "#1B365D",
        "secondary": "#4A90D9",
        "accent": "#E8833A",
        "text": "#2C2C2C",
        "text_light": "#6B7280",
        "background": "#FFFFFF",
        "surface": "#F8F9FA",
        "font_heading": "Calibri",
        "font_body": "Calibri",
        "font_size_h1": 28,
        "font_size_h2": 22,
        "font_size_h3": 16,
        "font_size_body": 11,
        "line_spacing": 1.15,
    },
    "modern": {
        "primary": "#0F172A",
        "secondary": "#3B82F6",
        "accent": "#F59E0B",
        "text": "#1E293B",
        "text_light": "#94A3B8",
        "background": "#FFFFFF",
        "surface": "#F1F5F9",
        "font_heading": "Arial",
        "font_body": "Arial",
        "font_size_h1": 32,
        "font_size_h2": 24,
        "font_size_h3": 18,
        "font_size_body": 11,
        "line_spacing": 1.2,
    },
    "academic": {
        "primary": "#1A1A2E",
        "secondary": "#16213E",
        "accent": "#0F3460",
        "text": "#1A1A1A",
        "text_light": "#555555",
        "background": "#FFFFFF",
        "surface": "#FAFAFA",
        "font_heading": "Times New Roman",
        "font_body": "Times New Roman",
        "font_size_h1": 24,
        "font_size_h2": 18,
        "font_size_h3": 14,
        "font_size_body": 12,
        "line_spacing": 2.0,
    },
    "tech": {
        "primary": "#0D1117",
        "secondary": "#238636",
        "accent": "#58A6FF",
        "text": "#C9D1D9",
        "text_light": "#8B949E",
        "background": "#0D1117",
        "surface": "#161B22",
        "font_heading": "Consolas",
        "font_body": "Segoe UI",
        "font_size_h1": 28,
        "font_size_h2": 22,
        "font_size_h3": 16,
        "font_size_body": 11,
        "line_spacing": 1.15,
    },
    "financial": {
        "primary": "#003366",
        "secondary": "#336699",
        "accent": "#CC3333",
        "text": "#1A1A1A",
        "text_light": "#666666",
        "background": "#FFFFFF",
        "surface": "#F5F5F5",
        "font_heading": "Calibri",
        "font_body": "Calibri",
        "font_size_h1": 26,
        "font_size_h2": 20,
        "font_size_h3": 14,
        "font_size_body": 10,
        "line_spacing": 1.08,
    },
}


# ── Slide layout definitions (for write_pptx upgrades) ───────────────────────

SLIDE_LAYOUTS: dict[str, dict[str, Any]] = {
    "cover": {
        "elements": ["title", "subtitle", "date", "author"],
        "title_y_pct": 30,
        "subtitle_y_pct": 55,
        "use_primary_bg": True,
    },
    "toc": {
        "elements": ["title", "items"],
        "max_items": 8,
    },
    "section_divider": {
        "elements": ["section_number", "section_title"],
        "use_primary_bg": True,
        "text_color_override": "#FFFFFF",
    },
    "content": {
        "elements": ["title", "body"],
    },
    "content_with_image": {
        "elements": ["title", "body", "image"],
        "text_width_pct": 60,
        "image_width_pct": 35,
    },
    "two_column": {
        "elements": ["title", "left_body", "right_body"],
        "split_pct": 50,
    },
    "data_highlight": {
        "elements": ["title", "big_number", "description"],
        "big_number_font_size": 72,
    },
    "summary": {
        "elements": ["title", "key_points", "next_steps"],
    },
}


# ── Excel formatting presets (for write_xlsx upgrades) ────────────────────────

XLSX_PRESETS: dict[str, dict[str, Any]] = {
    "financial": {
        "number_format": "#,##0.00",
        "negative_format": '#,##0.00;[Red]-#,##0.00',
        "percentage_format": "0.00%",
        "date_format": "YYYY-MM-DD",
        "currency_symbol": "$",
        "currency_format": "$#,##0.00",
        "header_fill": "003366",
        "header_font_color": "FFFFFF",
        "header_bold": True,
        "alternating_rows": True,
        "alternating_fill": "F2F2F2",
        "border_style": "thin",
        "freeze_panes": "B2",
        "auto_filter": True,
        "auto_width": True,
    },
    "scientific": {
        "number_format": "0.000E+00",
        "date_format": "YYYY-MM-DD",
        "currency_symbol": "",
        "header_fill": "2C3E50",
        "header_font_color": "FFFFFF",
        "header_bold": True,
        "alternating_rows": False,
        "border_style": "thin",
        "freeze_panes": "A2",
        "auto_filter": True,
        "auto_width": True,
    },
    "dashboard": {
        "number_format": "#,##0",
        "date_format": "YYYY-MM-DD",
        "currency_symbol": "",
        "header_fill": "0D1117",
        "header_font_color": "58A6FF",
        "header_bold": True,
        "alternating_rows": True,
        "alternating_fill": "161B22",
        "border_style": "none",
        "auto_filter": False,
        "auto_width": True,
    },
    "plain": {
        "number_format": "General",
        "date_format": "YYYY-MM-DD",
        "currency_symbol": "",
        "header_fill": "D9E1F2",
        "header_font_color": "000000",
        "header_bold": True,
        "alternating_rows": False,
        "border_style": "thin",
        "freeze_panes": "A2",
        "auto_filter": True,
        "auto_width": True,
    },
}


# ── Preset registry ──────────────────────────────────────────────────────────


def get_document_preset(name: str) -> dict[str, Any]:
    """Get a document style preset by name. Returns a deep copy."""
    if name not in DOCUMENT_PRESETS:
        raise ValueError(
            f"Unknown document preset: {name!r}. "
            f"Available: {list(DOCUMENT_PRESETS.keys())}"
        )
    return copy.deepcopy(DOCUMENT_PRESETS[name])


def get_xlsx_preset(name: str) -> dict[str, Any]:
    """Get an Excel formatting preset by name. Returns a deep copy."""
    if name not in XLSX_PRESETS:
        raise ValueError(
            f"Unknown xlsx preset: {name!r}. "
            f"Available: {list(XLSX_PRESETS.keys())}"
        )
    return copy.deepcopy(XLSX_PRESETS[name])


def get_slide_layout(name: str) -> dict[str, Any]:
    """Get a slide layout definition by name. Returns a deep copy."""
    if name not in SLIDE_LAYOUTS:
        raise ValueError(
            f"Unknown slide layout: {name!r}. "
            f"Available: {list(SLIDE_LAYOUTS.keys())}"
        )
    return copy.deepcopy(SLIDE_LAYOUTS[name])


def register_preset(
    category: str,
    name: str,
    preset: dict[str, Any],
) -> None:
    """Register a custom preset at runtime.

    Args:
        category: 'document', 'xlsx', or 'slide_layout'
        name:     unique preset name
        preset:   preset dict matching the category's schema
    """
    registries = {
        "document": DOCUMENT_PRESETS,
        "xlsx": XLSX_PRESETS,
        "slide_layout": SLIDE_LAYOUTS,
    }
    if category not in registries:
        raise ValueError(f"Unknown category: {category!r}. Available: {list(registries.keys())}")
    registries[category][name] = copy.deepcopy(preset)


def list_presets() -> dict[str, list[str]]:
    """List all available presets by category."""
    return {
        "document": list(DOCUMENT_PRESETS.keys()),
        "xlsx": list(XLSX_PRESETS.keys()),
        "slide_layout": list(SLIDE_LAYOUTS.keys()),
    }
