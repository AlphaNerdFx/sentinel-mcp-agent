"""src/tools/__init__.py
Subsystem Facade for Relational Storage and Multi-Provider Search.
"""

from src.tools.database import DatabaseEngine, SecurityViolationError
from src.tools.search import ResilientSearchEngine, SearchResultItem, UnifiedSearchResponse

__all__ = [
    "DatabaseEngine",
    "SecurityViolationError",
    "ResilientSearchEngine",
    "UnifiedSearchResponse",
    "SearchResultItem",
]
