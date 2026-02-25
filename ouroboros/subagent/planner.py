"""Planner subagent — detect stagnation, propose evolution."""

import asyncio
import json
import logging
from pathlib import Path
from typing import Dict, List, Optional

from .base import AgentRole, Propo
