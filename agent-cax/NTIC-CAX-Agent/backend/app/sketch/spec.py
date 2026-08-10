"""SketchSpec: the structured intermediate representation (JSON Schema).

Frozen, kernel-independent. LLM/perception layer emits this; the transpiler
consumes it. Pydantic enforces the schema so malformed specs fail fast.
"""

from __future__ import annotations

from typing import Annotated, Literal, Optional, Union

from pydantic import BaseModel, ConfigDict, Field, model_validator

# A 3D point / vector as [x, y, z]; pydantic coerces [x, y, z] lists to tuples.
Point3 = tuple[float, float, float]
Vec3 = tuple[float, float, float]

_ID_PATTERN = r"^[A-Za-z_][A-Za-z0-9_]*$"


class _BasePrimitive(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(..., pattern=_ID_PATTERN, description="stable object reference, used as variable name")


class PointPrim(_BasePrimitive):
    type: Literal["point"] = "point"
    at: Point3


class LinePrim(_BasePrimitive):
    type: Literal["line"] = "line"
    start: Point3
    end: Point3


class CenterLinePrim(_BasePrimitive):
    type: Literal["centerline"] = "centerline"
    start: Point3
    end: Point3


class SplinePrim(_BasePrimitive):
    type: Literal["spline"] = "spline"
    points: list[Point3]


class RectPrim(_BasePrimitive):
    type: Literal["rect"] = "rect"
    start: Point3
    end: Point3


class CirclePrim(_BasePrimitive):
    type: Literal["circle"] = "circle"
    center: Point3
    radius: float = Field(..., gt=0)


class ArcPrim(_BasePrimitive):
    type: Literal["arc"] = "arc"
    # Form A: three points. Form B: radius + angles + center. Exactly one.
    start: Optional[Point3] = None
    end: Optional[Point3] = None
    point_on_arc: Optional[Point3] = None
    radius: Optional[float] = None
    start_angle: Optional[float] = None
    end_angle: Optional[float] = None
    center: Optional[Point3] = None

    @model_validator(mode="after")
    def _check_form(self) -> "ArcPrim":
        form_a = all(x is not None for x in (self.start, self.end, self.point_on_arc))
        form_b = all(
            x is not None for x in (self.radius, self.start_angle, self.end_angle, self.center)
        )
        if form_a == form_b:  # both True or both False
            raise ValueError("arc must provide exactly one of (start,end,point_on_arc) or (radius,start_angle,end_angle,center)")
        if self.radius is not None and self.radius <= 0:
            raise ValueError("arc radius must be > 0")
        return self


class EllipsePrim(_BasePrimitive):
    type: Literal["ellipse"] = "ellipse"
    center: Point3
    major: Vec3
    minor: Vec3


class EllipseArcPrim(_BasePrimitive):
    type: Literal["ellipse_arc"] = "ellipse_arc"
    center: Point3
    major: Vec3
    minor: Vec3
    start_angle: float
    end_angle: float


class FilletPrim(_BasePrimitive):
    type: Literal["fillet"] = "fillet"
    radius: float = Field(..., gt=0)
    line_a: str
    line_b: str


class ChamferPrim(_BasePrimitive):
    type: Literal["chamfer"] = "chamfer"
    dist_a: float = Field(..., gt=0)
    line_a: str
    dist_b: float = Field(..., gt=0)
    line_b: str


class TrimPrim(_BasePrimitive):
    type: Literal["trim"] = "trim"
    at: Point3
    objects: Optional[list[str]] = None


class OffsetPrim(_BasePrimitive):
    type: Literal["offset"] = "offset"
    objects: list[str]
    distance: float


Primitive = Annotated[
    Union[
        PointPrim,
        LinePrim,
        CenterLinePrim,
        SplinePrim,
        RectPrim,
        CirclePrim,
        ArcPrim,
        EllipsePrim,
        EllipseArcPrim,
        FilletPrim,
        ChamferPrim,
        TrimPrim,
        OffsetPrim,
    ],
    Field(discriminator="type"),
]


class Constraint(BaseModel):
    """A constraint referencing one or two primitive ids by `id`."""

    model_config = ConfigDict(extra="forbid")
    id: Optional[str] = Field(None, pattern=_ID_PATTERN)
    type: Literal[
        "length", "radius", "angle", "xpos", "ypos",
        "parallel", "perpendicular", "tangent", "equal", "horizontal", "vertical", "coincide",
    ]
    target: Optional[str] = None
    target2: Optional[str] = None
    value: Optional[float] = None
    index: Optional[int] = None
    index2: Optional[int] = None


class SketchSpec(BaseModel):
    """Top-level structured sketch specification."""

    model_config = ConfigDict(extra="forbid")
    plane: Literal["XY", "XZ", "YZ"] = "XY"
    auto_solve: bool = True
    primitives: list[Primitive]
    constraints: list[Constraint] = Field(default_factory=list)
