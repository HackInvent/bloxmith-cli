# -----------------------------------------------------------------------------
# Role: Exports the CLI block package API.
# File Name: __init__.py
# Author: Alexandre EL
# Email: alex@hackinvent.com
# Created Date: 2024-03-15
# -----------------------------------------------------------------------------

from .block import CliBlock, CliBlockError

__all__ = ["CliBlock", "CliBlockError"]
