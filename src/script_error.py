class ScriptError(Exception):
    """Raised by scripts instead of exit(1) when called in-process."""
    pass
