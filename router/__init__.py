"""Cost-aware inference router — prototype (plan item #7).

See router-prototype-spec.md for the design. Public entry points:

    from router.models import load_scenario
    from router.router import CostAwareRouter
    from router.report import build_report
"""

__all__ = ["models", "latency", "router", "baselines", "report"]
