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
    p10_public_dns_preflight,
    p11_public_endpoints,
    p12_ddns_module,
    p13_dns_sync_module,
    p17_swarm_bootstrap,
    p18_up_swarm,
    p19_swarm_health,
    p20_down_swarm,
    p99_cleanup,
)
