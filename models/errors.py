from __future__ import annotations


# errors

class QueueAError(Exception):
    """errors we can show the user"""


class ValidationError(QueueAError):
    """bad input"""


class AuthError(QueueAError):
    """login or sign up failed"""


class PermissionDenied(QueueAError):
    """not your stuff"""


class ConflictError(QueueAError):
    """something changed (like the slot got taken)"""


class DataStoreError(QueueAError):
    """database problem"""


class EarlyCompletionWarning(ValidationError):
    """completing before the meeting starts"""
