from pydantic import BaseModel
from typing import Optional
import json

class Position(BaseModel):
    x1: Optional[float] = None
    y1: Optional[float] = None
    z1: Optional[float] = None
    x2: Optional[float] = None
    y2: Optional[float] = None
    z2: Optional[float] = None

def dist_between_points(p: Position):
    if p.x1 is None or p.y1 is None or p.x2 is None or p.y2 is None:
        raise ValueError("All position values must be provided")
    return ((p.x2 - p.x1) ** 2 + (p.y2 - p.y1) ** 2) ** 0.5

class ParkPosition:
    def __init__(self, json_path):
        with open(json_path, 'r') as f:
            data = json.load(f)
            self.park1_position = Position(**data.get('carriage1').get('park_position', {}))
            self.park2_position = Position(**data.get('carriage2').get('park_position', {}))
        
