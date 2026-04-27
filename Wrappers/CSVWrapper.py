import pandas as pd
import numpy as np
from pydantic import BaseModel
from PositionSchema import Position

# Expected Schema: index, x1, y1, x2, y2, manual
class TestPair(BaseModel):
    index: int
    x1: float
    y1: float
    x2: float
    y2: float
    manual: bool

class Point(BaseModel):
    x: float
    y: float

class CSVWrapper:
    def __init__(self, file_path):
        self.file_path = file_path
        data = pd.read_csv(file_path)
        self.landmark1: tuple[float, float] = None
        self.landmark2: tuple[float, float] = None
        self.current_row = 0
        self.test_pairs: list[TestPair] = []


        for _, row in data.iterrows():
            if row['index'] == 'landmark1':
                self.landmark1 = (row['x1'], row['y1'])
            elif row['index'] == 'landmark2':
                self.landmark2 = (row['x2'], row['y2'])
            else:
                x1 = row['x1']
                y1 = row['y1']
                x2 = row['x2']
                y2 = row['y2']

                # Normalize point ordering: (x1, y1) is always the point with the smaller X.
                # This makes left-to-right ordering consistent across all rows.
                try:
                    if pd.notna(x1) and pd.notna(x2) and float(x1) > float(x2):
                        x1, x2 = x2, x1
                        y1, y2 = y2, y1
                except (TypeError, ValueError):
                    pass

                self.test_pairs.append(
                    TestPair(
                        index=int(row['index']),
                        x1=x1,
                        y1=y1,
                        x2=x2,
                        y2=y2,
                        manual=bool(row['manual']),
                    )
                )

    def _normalize_test_pair_ordering(self) -> None:
        for pair in self.test_pairs:
            try:
                if float(pair.x1) > float(pair.x2):
                    pair.x1, pair.x2 = pair.x2, pair.x1
                    pair.y1, pair.y2 = pair.y2, pair.y1
            except (TypeError, ValueError):
                continue

    def get_number_of_test_pairs(self):
        return len(self.test_pairs)
    
    def get_landmarks(self):
        return self.landmark1, self.landmark2
    
    def get_rotation(self, p1: Point, p2: Point):
        # Calculate the angle between the two points (in radians)
        angle1 = np.arctan2(p1.y, p1.x)
        angle2 = np.arctan2(p2.y, p2.x)
        rotation = angle2 - angle1
        return rotation
    
    def apply_rotation(self, angle: float):
        # Rotate all test pairs by the given angle (in radians)
        cos_angle = np.cos(angle)
        sin_angle = np.sin(angle)

        for pair in self.test_pairs:
            # Rotate point 1
            x1_new = pair.x1 * cos_angle - pair.y1 * sin_angle
            y1_new = pair.x1 * sin_angle + pair.y1 * cos_angle
            pair.x1, pair.y1 = x1_new, y1_new

            # Rotate point 2
            x2_new = pair.x2 * cos_angle - pair.y2 * sin_angle
            y2_new = pair.x2 * sin_angle + pair.y2 * cos_angle
            pair.x2, pair.y2 = x2_new, y2_new

        # Keep the min-X point in (x1, y1) after transformation.
        self._normalize_test_pair_ordering()

    def get_nth_test_pair(self, n: int):
        if n < len(self.test_pairs):
            p = self.test_pairs[n]
            return Position(x1=p.x1, y1=p.y1, x2=p.x2, y2=p.y2)
        else:
            return None


    def get_next_test_pair(self):
        if self.current_row < len(self.test_pairs):
            self.current_row += 1
            return self.test_pairs[self.current_row - 1]
        else:
            return None