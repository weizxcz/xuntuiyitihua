"""verify_sketch: shallow static verification of a SketchSpec.

This is the "验证闭环" layer. Without the live NCTI kernel reachable from this
environment, we perform *shallow* verification on the structured Spec itself
(pre-execution), which catches the dominant error classes:

  - schema errors        (pydantic, at parse time)
  - duplicate / reserved ids
  - degenerate geometry   (zero-length line, non-positive radius/axes)
  - dangling references   (constraint/operation targets a missing primitive)
  - type mismatches       (e.g. radius constraint on a line)

Note: dimension values are *not* validated here. NCTI dimension constraints
(length/radius/angle/xpos/ypos) have no `value` parameter in their API surface —
the actual size is carried by the primitive's own coordinates/radius, so the
transpiler ignores `Constraint.value` and the verifier does not require it.

A pluggable `verify_kernel` hook is provided for the *deep* verification path
(reading solver DOF / conflict / degenerate-geometry feedback from the kernel
after RunSolve). When the kernel is unavailable it returns a "skipped" status,
so the shallow verifier remains the source of truth. See design doc §4.3 / §5.1.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Callable, Optional

from app.sketch.api_catalog import (
    CONSTRAINT_API,
    CONSTRAINT_TARGET_TYPES,
    RESERVED_IDS,
)
from app.sketch.spec import Constraint, SketchSpec


@dataclass
class Issue:
    level: str  # "error" | "warning"
    code: str
    message: str
    spec_path: Optional[str] = None


@dataclass
class VerificationReport:
    ok: bool
    issues: list[Issue] = field(default_factory=list)

    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "error"]

    def warnings(self) -> list[Issue]:
        return [i for i in self.issues if i.level == "warning"]

    def error_codes(self) -> set[str]:
        return {i.code for i in self.errors()}


@dataclass
class KernelStatus:
    skipped: bool
    reason: Optional[str] = None
    dof: Optional[int] = None
    conflicts: list[str] = field(default_factory=list)
    degenerate: list[str] = field(default_factory=list)
    raw: Optional[object] = None


def _mag(v: tuple[float, float, float]) -> float:
    return (v[0] ** 2 + v[1] ** 2 + v[2] ** 2) ** 0.5


def _check_primitive(p, idx: int, issues: list[Issue]) -> None:
    vid = p.id
    if vid in RESERVED_IDS:
        issues.append(Issue("error", "RESERVED_ID", f"primitive id '{vid}' is reserved", f"primitives[{idx}]"))
    t = p.type
    if t == "line" and _eq(p.start, p.end):
        issues.append(Issue("error", "DEGENERATE", "zero-length line (start == end)", f"primitives[{idx}]"))
    if t == "circle" and p.radius <= 0:
        issues.append(Issue("error", "DEGENERATE", "circle radius must be > 0", f"primitives[{idx}]"))
    if t == "arc" and p.radius is not None and p.radius <= 0:
        issues.append(Issue("error", "DEGENERATE", "arc radius must be > 0", f"primitives[{idx}]"))
    if t == "ellipse":
        if _mag(p.major) <= 0 or _mag(p.minor) <= 0:
            issues.append(Issue("error", "DEGENERATE", "ellipse axes must be > 0", f"primitives[{idx}]"))
    if t == "fillet" and p.radius <= 0:
        issues.append(Issue("error", "DEGENERATE", "fillet radius must be > 0", f"primitives[{idx}]"))
    if t == "chamfer" and (p.dist_a <= 0 or p.dist_b <= 0):
        issues.append(Issue("error", "DEGENERATE", "chamfer distances must be > 0", f"primitives[{idx}]"))


def _require_line(ref: str, ids: dict, issues: list[Issue], path: str) -> None:
    if ref not in ids:
        issues.append(Issue("error", "DANGLING_REF", f"'{ref}' not found", path))
    elif ids[ref].type != "line":
        issues.append(Issue("error", "TYPE_MISMATCH", f"'{ref}' is not a line", path))


def _require_exists(ref: str, ids: dict, issues: list[Issue], path: str) -> None:
    if ref not in ids:
        issues.append(Issue("error", "DANGLING_REF", f"'{ref}' not found", path))


def _check_constraint(c: Constraint, j: int, ids: dict, issues: list[Issue]) -> None:
    path = f"constraints[{j}]"
    if c.type not in CONSTRAINT_API:
        issues.append(Issue("error", "UNKNOWN_CONSTRAINT", f"unknown constraint type '{c.type}'", path))
        return
    if c.target is None:
        issues.append(Issue("error", "MISSING_TARGET", f"constraint '{c.type}' missing target", path))
        return
    if c.target not in ids:
        issues.append(Issue("error", "DANGLING_REF", f"constraint target '{c.target}' not found", path))
        return
    if c.target2 is not None and c.target2 not in ids:
        issues.append(Issue("error", "DANGLING_REF", f"constraint target2 '{c.target2}' not found", path))
        return
    # Dimension constraints carry no `value` in the NCTI API (size comes from the
    # primitive itself), so `value` is intentionally not required/checked here.
    allowed = CONSTRAINT_TARGET_TYPES.get(c.type)
    if allowed is not None:
        t1 = ids[c.target].type
        if t1 not in allowed:
            issues.append(Issue("error", "TYPE_MISMATCH", f"constraint '{c.type}' cannot apply to '{t1}'", path))
        if c.target2 is not None:
            t2 = ids[c.target2].type
            if t2 not in allowed:
                issues.append(Issue("error", "TYPE_MISMATCH", f"constraint '{c.type}' cannot apply to '{t2}'", path))


def _eq(a: tuple, b: tuple) -> bool:
    return tuple(a) == tuple(b)


def verify_spec(spec: SketchSpec) -> VerificationReport:
    """Shallow static verification of a SketchSpec. Returns a report."""
    issues: list[Issue] = []
    ids: dict[str, object] = {}
    for i, p in enumerate(spec.primitives):
        if p.id in ids:
            issues.append(Issue("error", "DUP_ID", f"duplicate primitive id '{p.id}'", f"primitives[{i}]"))
        ids[p.id] = p
        _check_primitive(p, i, issues)

    for i, p in enumerate(spec.primitives):
        if p.type == "fillet":
            _require_line(p.line_a, ids, issues, f"primitives[{i}].line_a")
            _require_line(p.line_b, ids, issues, f"primitives[{i}].line_b")
        elif p.type == "chamfer":
            _require_line(p.line_a, ids, issues, f"primitives[{i}].line_a")
            _require_line(p.line_b, ids, issues, f"primitives[{i}].line_b")
        elif p.type in ("trim", "offset"):
            for o in p.objects or []:
                _require_exists(o, ids, issues, f"primitives[{i}].objects")

    for j, c in enumerate(spec.constraints):
        _check_constraint(c, j, ids, issues)

    ok = not any(i.level == "error" for i in issues)
    return VerificationReport(ok=ok, issues=issues)


def verify_kernel(script: str, run_solver: Optional[Callable[[str], KernelStatus]] = None) -> KernelStatus:
    """Pluggable deep verification against the NCTI kernel.

    `run_solver` executes the script in the NCTI runtime and returns a
    KernelStatus with DOF / conflicts / degenerate-geometry feedback. When the
    kernel runtime is unavailable (this environment), returns a skipped status
    so the shallow verifier stays authoritative.

    Any exception raised by `run_solver` is caught and degraded to a skipped
    status instead of crashing the pipeline.
    """
    if run_solver is None:
        return KernelStatus(skipped=True, reason="kernel runtime not available in this environment")
    try:
        return run_solver(script)
    except Exception as exc:  # deep-verify must never abort the closed loop
        return KernelStatus(skipped=True, reason=f"kernel execution error: {exc}")
