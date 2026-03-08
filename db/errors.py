class DatabaseError(Exception):
    """Base error for storage-layer failures across backends."""


class DatabaseOperationalError(DatabaseError):
    """Raised for operational issues (missing relation/column, connectivity, etc.)."""


class DatabaseIntegrityError(DatabaseError):
    """Raised for constraint violations."""
