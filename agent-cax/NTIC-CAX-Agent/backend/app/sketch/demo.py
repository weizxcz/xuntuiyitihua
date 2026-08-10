"""Runnable demo of the structured-spec -> verify closed loop.

Run from backend/:  python -m app.sketch.demo
"""

from app.sketch import SketchPipeline, SketchSpec, transpile, verify_spec
from app.sketch.spec import CirclePrim, Constraint, LinePrim


def _header(t: str) -> None:
    print("\n" + "=" * 60 + f"\n{t}\n" + "=" * 60)


def demo_valid() -> None:
    _header("1) Valid spec -> transpile + verify (pass)")
    spec = SketchSpec(
        primitives=[
            LinePrim(id="l1", start=(0, 0, 0), end=(50, 0, 0)),
            CirclePrim(id="c1", center=(25, 25, 0), radius=10.0),
        ],
        constraints=[
            Constraint(type="length", target="l1", value=50.0),
            Constraint(type="radius", target="c1", value=10.0),
            Constraint(type="tangent", target="c1", target2="l1"),
        ],
    )
    res = SketchPipeline().run(spec)
    print(f"ok={res.ok} iterations={res.iterations}")
    print(res.script)


def demo_dangling_autofix() -> None:
    _header("2) Dangling constraint ref -> auto-fixed (dropped), passes")
    spec = SketchSpec(
        primitives=[LinePrim(id="l1", start=(0, 0, 0), end=(50, 0, 0))],
        constraints=[
            Constraint(type="length", target="l1", value=50.0),
            Constraint(type="parallel", target="l1", target2="ghost"),  # ghost missing
        ],
    )
    res = SketchPipeline().run(spec)
    print(f"ok={res.ok} iterations={res.iterations} unfixable={res.unfixable}")
    print("remaining constraints:", [c.type for c in res.spec.constraints])
    print(res.script)


def demo_degenerate_unfixable() -> None:
    _header("3) Zero-length line -> NOT auto-fixable, reported")
    spec = SketchSpec(
        primitives=[LinePrim(id="l1", start=(0, 0, 0), end=(0, 0, 0))],
        constraints=[Constraint(type="length", target="l1", value=50.0)],
    )
    res = SketchPipeline().run(spec)
    print(f"ok={res.ok} unfixable={res.unfixable}")
    for i in res.report.errors():
        print(f"  [{i.code}] {i.message} @ {i.spec_path}")


def demo_type_mismatch() -> None:
    _header("4) radius constraint on a line -> TYPE_MISMATCH")
    spec = SketchSpec(
        primitives=[LinePrim(id="l1", start=(0, 0, 0), end=(50, 0, 0))],
        constraints=[Constraint(type="radius", target="l1", value=5.0)],
    )
    report = verify_spec(spec)
    for i in report.errors():
        print(f"  [{i.code}] {i.message}")


if __name__ == "__main__":
    demo_valid()
    demo_dangling_autofix()
    demo_degenerate_unfixable()
    demo_type_mismatch()
