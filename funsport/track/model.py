"""数据结构（可选，供扩展使用）。"""
from dataclasses import dataclass, field


@dataclass
class GenPoint:
    id: int = 0
    flag: int = 0
    gLat: float = 0.0
    gLng: float = 0.0
    speed: float = 0.0
    avgSpeed: float = 0.0
    radius: float = 0.0
    ptype: int = 0
    locType: int = 0
    totalTime: int = 0
    totalDis: float = 0.0
    steps: int = 0
    bdA: float = 0.0
    state: int = 0


@dataclass
class Track:
    totalTime: int = 0
    totalDistance: float = 0.0
    validDistance: float = 0.0
    validTime: int = 0
    startTime: int = 0
    startLatitude: float = 0.0
    startLongitude: float = 0.0
    totalSteps: int = 0
    locations: list = field(default_factory=list)
    speedPerTenSec: list = field(default_factory=list)
    stepsPerTenSec: list = field(default_factory=list)
