"""
Majestic core package.

Contains the central coordination components: Gateway (input normalisation),
and future additions such as the Planner, Executor, and Reflector.
"""

from .gateway import Gateway

__all__ = ["Gateway"]
