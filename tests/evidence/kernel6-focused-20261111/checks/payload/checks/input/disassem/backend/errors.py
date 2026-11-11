"""Construction outcomes before a source instruction is emitted."""


class LoweringUnsupported(ValueError):
    """The current representation cannot faithfully lower this instruction."""


class RegisterPressure(ValueError):
    """The selected physical scratch mapping cannot hold this instruction."""


class LoweringInvariant(ValueError):
    """Retained compiler/source identity changed before emission."""
