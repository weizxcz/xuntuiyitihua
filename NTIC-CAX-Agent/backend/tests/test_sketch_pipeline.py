"""Tests for the sketch structured-spec -> verify closed loop."""

import pytest

from app.sketch import SketchPipeline, SketchSpec, transpile, verify_spec
from app.sketch.spec import ArcPrim, CirclePrim, Constraint, LinePrim


def _valid_spec() -> SketchSpec:
    return SketchSpec(
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


def test_valid_spec_verifies_ok():
    spec = _valid_spec()
    report = verify_spec(spec)
    assert report.ok
    assert report.errors() == []


def test_transpile_emits_frozen_api():
    script = transpile(_valid_spec())
    assert "yh_doc = YH.YHDocument(doc)" in script
    assert "skt = YH.SketchWorkPlane(doc)" in script
    assert "l1 = skt.AddLine(NCTI.Point(0.0, 0.0, 0.0), NCTI.Point(50.0, 0.0, 0.0))" in script
    assert "c1 = skt.AddCircle(NCTI.Point(25.0, 25.0, 0.0), 10.0)" in script
    assert "skt.AddConsLength(0, l1)" in script
    assert "skt.AddConsRadius(c1)" in script
    assert "skt.AddConsTangent(c1, l1)" in script
    assert script.strip().endswith("skt.Close()")


def test_pipeline_valid_passes():
    res = SketchPipeline().run(_valid_spec())
    assert res.ok
    assert res.iterations == 1
    assert res.script is not None


def test_zero_length_line_is_error_and_unfixable():
    spec = SketchSpec(
        primitives=[LinePrim(id="l1", start=(0, 0, 0), end=(0, 0, 0))],
        constraints=[Constraint(type="length", target="l1", value=50.0)],
    )
    res = SketchPipeline().run(spec)
    assert not res.ok
    assert res.unfixable
    assert "DEGENERATE" in res.report.error_codes()


def test_dangling_constraint_autofixed():
    spec = SketchSpec(
        primitives=[LinePrim(id="l1", start=(0, 0, 0), end=(50, 0, 0))],
        constraints=[
            Constraint(type="length", target="l1", value=50.0),
            Constraint(type="parallel", target="l1", target2="ghost"),
        ],
    )
    res = SketchPipeline().run(spec)
    assert res.ok
    assert res.iterations == 2  # 1st verify fails, auto-fix, 2nd passes
    assert [c.type for c in res.spec.constraints] == ["length"]


def test_type_mismatch_radius_on_line():
    spec = SketchSpec(
        primitives=[LinePrim(id="l1", start=(0, 0, 0), end=(50, 0, 0))],
        constraints=[Constraint(type="radius", target="l1", value=5.0)],
    )
    report = verify_spec(spec)
    assert not report.ok
    assert "TYPE_MISMATCH" in report.error_codes()


def test_schema_rejects_unknown_constraint():
    with pytest.raises(Exception):
        SketchSpec(
            primitives=[LinePrim(id="l1", start=(0, 0, 0), end=(50, 0, 0))],
            constraints=[Constraint(type="bogus", target="l1")],
        )


def test_arc_two_forms():
    a1 = ArcPrim(id="a1", start=(10, 0, 0), end=(0, 0, 0), point_on_arc=(5, 5, 0))
    assert "skt.AddArc(NCTI.Point(10.0, 0.0, 0.0)" in transpile(SketchSpec(primitives=[a1]))
    a2 = ArcPrim(id="a2", radius=5, start_angle=0, end_angle=60, center=(0, 0, 0))
    assert "skt.AddArc(5.0, 0.0, 60.0, NCTI.Point(0.0, 0.0, 0.0))" in transpile(SketchSpec(primitives=[a2]))


def test_arc_invalid_form_raises():
    with pytest.raises(Exception):
        ArcPrim(id="a1", start=(10, 0, 0))  # incomplete form A


def test_dimension_constraint_without_value_still_verifies():
    # NCTI dimension constraints (length/radius/angle/xpos/ypos) carry no `value`
    # parameter in their API surface, so the verifier must not require it.
    spec = SketchSpec(
        primitives=[
            LinePrim(id="l1", start=(0, 0, 0), end=(50, 0, 0)),
            CirclePrim(id="c1", center=(25, 25, 0), radius=10.0),
        ],
        constraints=[
            Constraint(type="length", target="l1"),   # no value
            Constraint(type="radius", target="c1"),   # no value
        ],
    )
    report = verify_spec(spec)
    assert report.ok, report.issues
    assert "MISSING_VALUE" not in report.error_codes()
