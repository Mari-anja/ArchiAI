"""Request and response shapes."""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, field_validator


class FootprintInput(BaseModel):
    """A drawn or imported outline, in metres."""
    outer: List[List[float]] = Field(..., min_length=3,
                                     description="Closed outer ring, [[x, y], ...]")
    holes: List[List[List[float]]] = Field(default_factory=list,
                                           description="Courtyards or light wells")
    storeys: int = Field(3, ge=1, le=60)
    floor_to_floor: float = Field(3.9, gt=2.0, le=12.0)
    use: str = "office"
    entrance_azimuth: float = 270.0
    name: Optional[str] = None

    @field_validator("outer")
    @classmethod
    def _finite(cls, v):
        for p in v:
            if len(p) != 2 or not all(abs(c) < 1e6 for c in p):
                raise ValueError("each point must be [x, y] in metres")
        return v


class SpecInput(BaseModel):
    use: str = "office"
    shape: str = "bar"
    storeys: int = Field(3, ge=1, le=60)
    area_m2: Optional[float] = Field(None, gt=0)
    entrance_azimuth: float = 270.0
    floor_to_floor: Optional[float] = Field(None, gt=2.0, le=12.0)
    name: Optional[str] = None


class GenerateRequest(BaseModel):
    brief: Optional[str] = Field(None, description="Plain-language brief")
    footprint: Optional[FootprintInput] = None
    spec: Optional[SpecInput] = None

    project_id: Optional[str] = Field(None, description="Your projects.id, echoed back")
    number: Optional[str] = Field(None, description="Drawing number prefix")
    client: Optional[str] = None
    idempotency_key: Optional[str] = None
    include_model: bool = True
    elevations: List[float] = Field(default_factory=lambda: [270.0, 0.0, 90.0, 180.0])

    def mode(self):
        given = [n for n in ("brief", "footprint", "spec") if getattr(self, n)]
        if len(given) != 1:
            raise ValueError("supply exactly one of brief, footprint or spec")
        return given[0]


class ParseRequest(BaseModel):
    brief: str


class ParseResponse(BaseModel):
    spec: Dict[str, Any]
    assumptions: List[str]
    estimated_cost_units: int
    estimated_sheets: int


class Asset(BaseModel):
    kind: str
    number: Optional[str] = None
    title: Optional[str] = None
    scale: Optional[str] = None
    key: str
    url: str
    bytes: int
    content_type: str
    width: int = 0
    height: int = 0
    meta: Dict[str, Any] = Field(default_factory=dict)


class GenerateResponse(BaseModel):
    status: str = "complete"
    generation_id: str
    project_id: Optional[str] = None
    duration_ms: int
    cost_units: int
    manifest: Dict[str, Any]
    assets: List[Asset]
