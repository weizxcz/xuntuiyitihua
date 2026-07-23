"""SketchPipeline: the closed-loop orchestrator.

Implements the "结构化规格 -> 内核验证闭环" loop:

    transpile(spec) -> verify_spec(spec)
        if ok:            emit script, done
        else:            try deterministic auto-fix -> re-verify (bounded retries)
                          if unfixable: return structured errors for LLM/human

Only *safe* deterministic fixes are applied automatically (today: dropping
dangling-reference constraints). Geometry/value errors are reported back for
the LLM or human to patch, rather than guessed. This mirrors CADSmith's split
between "execution errors" (avoided by deterministic transpile) and "geometric
validity" (caught by verification) — see design doc §4.3.
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from app.sketch.spec import Constraint, SketchSpec
from app.sketch.transpiler import transpile
from app.sketch.verify import KernelStatus, VerificationReport, verify_kernel, verify_spec


@dataclass
class PipelineResult:
    ok: bool
    script: str | None = None
    spec: SketchSpec | None = None
    iterations: int = 0
    report: VerificationReport | None = None
    unfixable: bool = False
    kernel: KernelStatus | None = None  # populated when verify_kernel is wired; else skipped


class SketchPipeline:
    def __init__(self, max_iter: int = 3):
        self.max_iter = max_iter

    def run(self, spec: SketchSpec, run_solver=None) -> PipelineResult:
        current = spec
        for it in range(1, self.max_iter + 1):
            report = verify_spec(current)
            if report.ok:
                script = transpile(current)
                # Always call verify_kernel so the kernel field is populated:
                # real deep status when run_solver is wired, else skipped.
                kernel = verify_kernel(script, run_solver)
                return PipelineResult(
                    ok=True, script=script, spec=current, iterations=it, report=report, kernel=kernel
                )
            fixed = self._auto_fix(current, report)
            if fixed is None:
                return PipelineResult(
                    ok=False, script=None, spec=current, iterations=it,
                    report=report, unfixable=True, kernel=None,
                )
            current = fixed
        return PipelineResult(ok=False, script=None, spec=current, iterations=self.max_iter, report=report, kernel=None)

    def _auto_fix(self, spec: SketchSpec, report: VerificationReport):
        errs = report.errors()
        if not errs:
            return None
        # Only dangling-reference constraints are safe to auto-drop.
        if not all(i.code == "DANGLING_REF" for i in errs):
            return None
        dangling: set[str] = set()
        for i in errs:
            m = re.search(r"'([^']+)' not found", i.message)
            if m:
                dangling.add(m.group(1))
        new_cons: list[Constraint] = []
        dropped = 0
        for c in spec.constraints:
            if (c.target in dangling) or (c.target2 in dangling):
                dropped += 1
                continue
            new_cons.append(c)
        if dropped == 0:
            return None
        return spec.model_copy(update={"constraints": new_cons})
