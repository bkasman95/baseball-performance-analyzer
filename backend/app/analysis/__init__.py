"""DiamondScope analysis engine.

Three stages, run in order:

    Stage A  — anomalies.py     — what changed, when, how much
    Stage B  — attribution.py   — why (probable drivers, ranked)
    Stage C  — report.py        — assembled JSON report with NL summaries

The metric catalog (§6 of the spec) lives in metrics.py and is the domain
source of truth. Everything else reads from it.

Honesty contract: findings are PROBABLE causes. Never "proven". This is
correlational driver attribution guided by domain rules — not causal
inference. The UI must label things accordingly; reports here use
"likely drivers" / "probable cause" wording.
"""

from app.analysis.report import build_report, AnalysisReport

__all__ = ["build_report", "AnalysisReport"]
