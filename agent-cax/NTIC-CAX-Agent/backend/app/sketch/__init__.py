"""NCTI Sketch pipeline: structured spec -> transpile -> verify closed loop."""

from app.sketch.api_catalog import CONSTRAINT_API, GEOMETRY_API
from app.sketch.kernel import (
    clear_kernel_runtime,
    get_kernel_runtime,
    make_ncti_run_solver,
    set_kernel_runtime,
)
from app.sketch.pipeline import PipelineResult, SketchPipeline
from app.sketch.spec import CirclePrim, Constraint, LinePrim, SketchSpec
from app.sketch.transpiler import transpile
from app.sketch.verify import Issue, KernelStatus, VerificationReport, verify_kernel, verify_spec

__all__ = [
    "SketchSpec",
    "Constraint",
    "LinePrim",
    "CirclePrim",
    "transpile",
    "verify_spec",
    "verify_kernel",
    "VerificationReport",
    "Issue",
    "KernelStatus",
    "SketchPipeline",
    "PipelineResult",
    "GEOMETRY_API",
    "CONSTRAINT_API",
    "set_kernel_runtime",
    "get_kernel_runtime",
    "clear_kernel_runtime",
    "make_ncti_run_solver",
]
