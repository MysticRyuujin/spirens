"""Phase modules — imported for their @phase() side-effects.

Keep this list in phase-order: run.py uses it for --all and --from/--to.
"""

from __future__ import annotations

from tests.e2e.phases import (  # noqa: F401
    p00_prereqs,
    p01_sync_repo,
    p03_bootstrap,
    p04_dry_runs,
    p05_up_single,
    p07_health_doctor,
    p08_endpoints,
    p99_cleanup,
)
