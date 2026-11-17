"""Repository-local Minecraft regression kit; future Minecraft MCP adapter boundary.

Importing this package does not attach to a client, run archived code, or start a
server. Source-pinned runtime tools remain at their original paths in tools/.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = Path(__file__).resolve().parent / "data"
