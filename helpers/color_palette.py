"""Shared visual design tokens for Lemegeton Discord embeds and UI.

Core command embeds use one consistent violet/navy palette. Theme-specific
embeds may intentionally override these values when a user selects a custom theme.
"""
from __future__ import annotations

import discord


class Palette:
    PRIMARY = discord.Color.from_rgb(124, 92, 255)       # Lemegeton violet
    SECONDARY = discord.Color.from_rgb(72, 86, 125)      # Slate blue
    SUCCESS = discord.Color.from_rgb(46, 204, 113)       # Positive action
    WARNING = discord.Color.from_rgb(241, 196, 15)       # Attention required
    DANGER = discord.Color.from_rgb(231, 76, 60)         # Errors / destructive action
    INFO = discord.Color.from_rgb(52, 152, 219)          # Informational
    NEUTRAL = discord.Color.from_rgb(130, 145, 170)      # Neutral / unavailable
    PANEL = discord.Color.from_rgb(31, 39, 58)           # Dark slate panel


PALETTE = Palette()


def color_for_state(state: str) -> discord.Color:
    """Return a semantic color token, safely defaulting to the primary brand color."""
    normalized = (state or "").strip().casefold()
    return {
        "success": PALETTE.SUCCESS,
        "ok": PALETTE.SUCCESS,
        "warning": PALETTE.WARNING,
        "warn": PALETTE.WARNING,
        "error": PALETTE.DANGER,
        "danger": PALETTE.DANGER,
        "failure": PALETTE.DANGER,
        "info": PALETTE.INFO,
        "neutral": PALETTE.NEUTRAL,
        "secondary": PALETTE.SECONDARY,
        "panel": PALETTE.PANEL,
    }.get(normalized, PALETTE.PRIMARY)
