from scipy.spatial import KDTree
import csv

class Model:
    def __init__(self):
        self.origin = None
        self.current_pairs = []
        self.dxf_points = None
        self.dxf_kdtree = None
        self.dxf_lines = []

    def set_origin(self, point):
        self.origin = point

    def set_dxf_data(self, lines, points, kdtree):
        self.dxf_lines = lines
        self.dxf_points = points
        self.dxf_kdtree = kdtree

    def add_pair(self, p1, p2):
        self.current_pairs.append((p1, p2))

    def undo(self):
        if self.current_pairs:
            self.current_pairs.pop()

    def clear(self):
        self.current_pairs = []

    def export_csv(self, filepath):
        if not self.origin:
            raise ValueError("Origin not set")
        
        with open(filepath, 'w', newline='') as csvfile:
            # Header with 'manual' column
            fieldnames = ['x1', 'y1', 'x2', 'y2', 'manual']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            for p1, p2 in self.current_pairs:
                # Transform: (point - origin) / 1000.0 (microns to mm)
                x1 = (p1[0] - self.origin[0]) / 1000.0
                y1 = (p1[1] - self.origin[1]) / 1000.0
                x2 = (p2[0] - self.origin[0]) / 1000.0
                y2 = (p2[1] - self.origin[1]) / 1000.0
                
                writer.writerow({
                    'x1': x1, 
                    'y1': y1, 
                    'x2': x2, 
                    'y2': y2, 
                    'manual': True
                })
