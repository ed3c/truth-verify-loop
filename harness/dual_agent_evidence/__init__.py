"""Independent Dual-Agent evidence verification extensions.

This package extends Truth Verify Loop evidence handling without creating a second
closure vocabulary or execution authority.
"""

from .contract import (
    BUNDLE_SCHEMA,
    REQUIRED_FAMILIES,
    DualAgentEvidenceError,
    compile_contract_closure,
    validate_bundle,
)

__all__ = [
    "BUNDLE_SCHEMA",
    "REQUIRED_FAMILIES",
    "DualAgentEvidenceError",
    "compile_contract_closure",
    "validate_bundle",
]
