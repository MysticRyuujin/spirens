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
    p06_public_dns_preflight,
    p07_health_doctor,
    p08_endpoints,
    p09_public_endpoints,
    p14_ddns_module,
    p15_dns_sync_module,
    p16_down_single_for_swarm,
    p17_swarm_bootstrap,
    p17b_swarm_worker_join,
    p18_up_swarm,
    p19_swarm_health,
    p19a_swarm_placement,
    p19b_swarm_drain,
    p20_down_swarm,
    p21_failure_modes,
    p99_cleanup,
)
