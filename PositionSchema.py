from pydantic import BaseModel
from typing import Optional
import json

class Position(BaseModel):
    x1: Optional[float] = None
    y1: Optional[float] = None
    x2: Optional[float] = None
    y2: Optional[float] = None


class ParkPosition:
    def __init__(self, json_path):
        with open(json_path, 'r') as f:
            data = json.load(f)
            self.park1_position = Position(**data.get('carriage1').get('park_position', {}))
            self.park2_position = Position(**data.get('carriage2').get('park_position', {}))
        