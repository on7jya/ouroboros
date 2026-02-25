"""Subagent architecture for Ouroboros — self-catalyzed evolution."""

from .planner import PlannerSubagent
from .coder import CoderSubagent
from .tester import TesterSubagent
from .reflector import ReflectorSubagent

__all__ = ["PlannerSubagent", "CoderSubagent", "TesterSubagent", "ReflectorSubagent"]
