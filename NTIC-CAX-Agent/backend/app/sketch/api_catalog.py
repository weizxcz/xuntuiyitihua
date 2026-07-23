"""Frozen NCTI sketch API catalog.

Single source of truth for the kernel API surface, derived from the frozen
user manual + skill references (2026-07-21). Both the transpiler and the
verifier import from here so the mapping cannot drift.

This module is intentionally dependency-free (stdlib only).
"""

# Geometry primitive type -> NCTI API method name
GEOMETRY_API: dict[str, str] = {
    "point": "AddPoint",
    "line": "AddLine",
    "centerline": "AddCenterLine",
    "spline": "AddSpline",
    "rect": "AddRect",
    "circle": "AddCircle",
    "arc": "AddArc",
    "ellipse": "AddEllipse",
    "ellipse_arc": "AddEllipseArc",
    "fillet": "CurveRadius",
    "chamfer": "CurveChamfer",
    "trim": "CurveTrimming",
    "offset": "CurveOffset",
}

# Constraint type -> NCTI API method name
CONSTRAINT_API: dict[str, str] = {
    "length": "AddConsLength",
    "radius": "AddConsRadius",
    "angle": "AddConsAngle",
    "xpos": "AddConsXpos",
    "ypos": "AddConsYpos",
    "parallel": "AddConsParallel",
    "perpendicular": "AddConsVertical",   # API name is Vertical, semantics = Perpendicular (90deg)
    "tangent": "AddConsTangent",
    "equal": "AddConsEqual",
    "horizontal": "AddConsXAxis",          # API name is XAxis, semantics = horizontal alignment
    "vertical": "AddConsYAxis",            # API name is YAxis, semantics = vertical alignment
    "coincide": "AddConsCoincide",
}

DIMENSION_CONSTRAINTS = {"length", "radius", "angle", "xpos", "ypos"}
GEOMETRIC_CONSTRAINTS = {"parallel", "perpendicular", "tangent", "equal", "horizontal", "vertical", "coincide"}

# Which primitive types a constraint may target. None = any primitive type.
CONSTRAINT_TARGET_TYPES: dict[str, set[str] | None] = {
    "length": {"line"},
    "radius": {"circle", "arc"},
    "angle": {"line"},
    "xpos": None,
    "ypos": None,
    "parallel": {"line"},
    "perpendicular": {"line"},
    "tangent": None,
    "equal": None,
    "horizontal": {"line"},
    "vertical": {"line"},
    "coincide": None,
}

# Variable names the generated script reserves; user-provided ids must avoid these.
RESERVED_IDS = {"doc", "skt", "yh_doc", "YH", "NCTI"}

ALL_PRIMITIVE_TYPES = set(GEOMETRY_API.keys())
ALL_CONSTRAINT_TYPES = set(CONSTRAINT_API.keys())
