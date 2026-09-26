"""Failures the execution engine may classify without knowing a transport."""


class ToolUnavailableError(RuntimeError):
    pass


class ToolTimeoutError(TimeoutError):
    pass
