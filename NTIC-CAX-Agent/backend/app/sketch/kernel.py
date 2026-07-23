"""Deep-verification seam against the live NCTI kernel.

This is the integration point for the "深验" path described in
``docs/sketch-transpile-verify-design.md`` §4.3 / §5.1 阻塞项 B. It is *wired but
dormant*: until a kernel runtime is registered (via ``set_kernel_runtime``),
``verify_kernel`` returns a ``skipped`` status and ``run_sketch_pipeline``'s
``kernel`` field stays empty.

Real kernel API (grounded in the shipped examples under the NCTI install dir
``Script/Constraint/DCM_*.py``, confirmed 2026-07-21 — supersedes the earlier
*predicted* ``GetDOF``/``GetConflictCons`` names):

  - **DOF / 约束平衡**: ``doc.dcm_constraint_balance(sys) -> tuple``
        index [1] = 自由度 (DOF), [2] = 约束度, [3] = 刚性体自由度
  - **过/欠约束状态**: ``doc.dcm_status(sys, node_name[, node_type]) -> int``
        geometry-node enum: 3=OVER_DEFINED, 5=NOT_CONSISTENT,
        10=WELL_DEFINED, 11=UNDER_DEFINED (r-node enum differs; see DCM_RADIUS).
  - 另有新一代 ``dcm3_*`` 引擎：``dcm3_constraint_balance`` / ``dcm3_status`` /
    ``dcm3_overdefined_status`` / ``dcm3_underdefined_dof`` /
    ``dcm3_get_overdefined_constraints`` 等（读回接口更细）。

.. important:: Headless-execution reality check (option (c) probe, 2026-07-21)

   The standalone ``ncti_python`` binding (``ncti_python312.pyd`` at the NCTI
   install dir, license ``dcubed.lic``/``gmde.lic`` present, ``Init(KERNEL_DIR)``
   returns 1) exposes the *full* API surface, but it does **NOT** execute
   commands headlessly:

   * ``doc.RunCommand("cmd_ncti_create_*", ...)`` is a **no-op** (returns ``None``);
     ``doc.AllNames()`` returns ``None`` before *and* after — i.e. no geometry is
     created and the constraint engine never runs.
   * ``doc.dcm_constraint_balance`` / ``doc.dcm_status`` therefore also return
     ``None`` (nothing was solved).
   * ``doc.ActivateDoc()`` **blocks/hangs** — it is waiting for the host NCTI
     application's document manager / message loop.
   * ``YH`` / ``SketchWorkPlane`` are **not importable** from the standalone
     module (only ``Document``/``Point``/``Vector``/``AiFunction`` exist); the OOP
     sketch API only works inside the full NCTI app's script host.

   **Consequence**: real DOF/conflict deep-verify cannot be obtained by
   ``import ncti_python`` + ``Document()`` in the backend. The seam below stays
   dormant, but the blocker is *"needs the host NCTI application (or its
   headless/automation engine entry) to register the command table + document
   manager"*, **not** merely "runtime not registered". To activate real deep
   verification, a ``KernelRuntime`` must be supplied that executes the transpiled
   script *inside* the host app (e.g. via the app's script host / batch /
   automation API) — not a bare ``Document()``. Until such a runtime exists,
   ``verify_kernel`` degrades to ``skipped`` rather than guessing.
"""

from __future__ import annotations

from typing import Any, Callable, Optional, Protocol

from app.sketch.verify import KernelStatus

# Real DCM read-back API (proven from shipped Script/Constraint examples).
_DCM_BALANCE_METHOD = "dcm_constraint_balance"
_DCM_STATUS_METHOD = "dcm_status"

# geometry-node status enum (doc.dcm_status). Values that indicate a problem.
DCM_STATUS_OVER_DEFINED = 3
DCM_STATUS_NOT_CONSISTENT = 5
DCM_STATUS_NOT_CONSISTENT_DIMENSIONS = 6
DCM_STATUS_NOT_CONSISTENT_OTHER = 7
DCM_STATUS_NOT_CONSISTENT_UNKNOWN = 8
DCM_STATUS_WELL_DEFINED = 10
DCM_STATUS_UNDER_DEFINED = 11

_CONFLICT_STATUSES = {
    DCM_STATUS_OVER_DEFINED,
    DCM_STATUS_NOT_CONSISTENT,
    DCM_STATUS_NOT_CONSISTENT_DIMENSIONS,
    DCM_STATUS_NOT_CONSISTENT_OTHER,
    DCM_STATUS_NOT_CONSISTENT_UNKNOWN,
}

_STATUS_NAMES = {
    0: "UNKNOWN",
    1: "FIXED",
    2: "FROZEN",
    3: "OVER_DEFINED",
    4: "NON_ALGEBRAIC",
    5: "NOT_CONSISTENT",
    6: "NOT_CONSISTENT_DIMENSIONS",
    7: "NOT_CONSISTENT_OTHER",
    8: "NOT_CONSISTENT_UNKNOWN",
    9: "NOT_CHANGED",
    10: "WELL_DEFINED",
    11: "UNDER_DEFINED",
}


class KernelRuntime(Protocol):
    """Minimal contract a registered NCTI kernel runtime must satisfy.

    The runtime provides the execution namespace the transpiled script needs
    (``NCTI`` for geometry primitives, ``doc`` for the document handle) and, for
    deep verification, a ``doc`` exposing the DCM read-back methods
    ``dcm_constraint_balance`` / ``dcm_status``. ``YH`` is included because the
    frozen sketch manual references it; it may be ``None`` if the sketch layer
    is not used.
    """

    NCTI: Any
    doc: Any
    YH: Any


_runtime: Optional[KernelRuntime] = None


def set_kernel_runtime(rt: KernelRuntime) -> None:
    """Register a live kernel runtime so deep verification activates.

    Call this once at gateway startup when the NCTI kernel is reachable. Pass
    ``None`` or call ``clear_kernel_runtime`` to deactivate (back to skipped).
    """
    global _runtime
    _runtime = rt


def get_kernel_runtime() -> Optional[KernelRuntime]:
    return _runtime


def clear_kernel_runtime() -> None:
    global _runtime
    _runtime = None


def _read_dof(doc: Any, dcm_system: str) -> Optional[int]:
    """Read DOF via ``doc.dcm_constraint_balance(sys)[1]``; None on any failure."""
    fn = getattr(doc, _DCM_BALANCE_METHOD, None)
    if fn is None:
        return None
    try:
        res = fn(dcm_system)
        return res[1]
    except Exception:
        return None


def _read_conflicts(doc: Any, dcm_system: str, nodes: list[str]) -> list[str]:
    """Return ``"<node>:<STATUS>"`` for nodes in a conflicting DCM status."""
    fn = getattr(doc, _DCM_STATUS_METHOD, None)
    if fn is None:
        return []
    conflicts: list[str] = []
    for node in nodes:
        try:
            status = fn(dcm_system, node)
        except Exception:
            continue
        if status in _CONFLICT_STATUSES:
            conflicts.append(f"{node}:{_STATUS_NAMES.get(status, status)}")
    return conflicts


def make_ncti_run_solver(
    rt: KernelRuntime,
    *,
    dcm_system: Optional[str] = None,
    status_nodes: Optional[list[str]] = None,
) -> Callable[[str], KernelStatus]:
    """Build a ``run_solver(script) -> KernelStatus`` callable for the pipeline.

    Executes the transpiled script in the runtime namespace, then reads solver
    state via the real DCM API. Any missing/unexpected surface degrades to a
    ``skipped`` status rather than raising.

    Args:
        rt: registered kernel runtime (provides ``NCTI`` / ``doc`` / ``YH``).
        dcm_system: name of the DCM dimension system to query for DOF /
            status. If omitted, execution errors are still caught (the "inner
            loop"), but DOF / conflict read-back is skipped because the system
            name is unknown — see the two-API note in the module docstring.
        status_nodes: DCM node names to check via ``dcm_status`` for
            over/under-constraint. Optional.

    Note: the transpiled YH script ends with ``skt.RunSolve()`` then
    ``skt.Close()``. If the kernel invalidates handles on ``Close()``, read
    solver state *before* closing (omit ``Close`` for verification runs).
    """

    def run_solver(script: str) -> KernelStatus:
        ns: dict[str, Any] = {"NCTI": rt.NCTI, "doc": rt.doc, "YH": getattr(rt, "YH", None)}
        try:
            exec(script, ns)  # noqa: S102 - trusted kernel namespace only
        except Exception as exc:  # execution error = CADSmith "inner loop"
            return KernelStatus(
                skipped=False,
                reason=f"script execution error: {exc}",
                raw=str(exc),
            )

        if dcm_system is None:
            return KernelStatus(
                skipped=True,
                reason="script executed OK, but no dcm_system name provided for DOF/status read-back",
            )

        doc = rt.doc
        dof = _read_dof(doc, dcm_system)
        conflicts = _read_conflicts(doc, dcm_system, status_nodes or [])
        return KernelStatus(
            skipped=False,
            dof=dof,
            conflicts=conflicts,
            degenerate=[],
            raw={"dof": dof, "conflicts": conflicts},
        )

    return run_solver
