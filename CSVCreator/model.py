from scipy.spatial import KDTree
import csv

class Model:
    def __init__(self):
        self.origin = None
        self.current_pairs = []
        self.dxf_points = None
        self.dxf_kdtree = None
        self.dxf_lines = []
        self.landmark_1 = None
        self.landmark_2 = None

    def set_origin(self, point):
        self.origin = point

    def set_dxf_data(self, lines, points, kdtree):
        self.dxf_lines = lines
        self.dxf_points = points
        self.dxf_kdtree = kdtree

    def set_landmark_1(self, p1):
        self.landmark_1 = p1

    def set_landmark_2(self, p1):
        self.landmark_2 = p1

    def add_pair(self, p1, p2):
        self.current_pairs.append((p1, p2))

    def undo(self):
        if self.current_pairs:
            self.current_pairs.pop()

    def clear(self):
        self.current_pairs = []
        self.landmark_1 = None
        self.landmark_2 = None

    def export_csv(self, filepath):
        if not self.origin:
            raise ValueError("Origin not set")
        
        with open(filepath, 'w', newline='') as csvfile:
            # Header with 'Index' and 'manual' column
            fieldnames = ['Index', 'x1', 'y1', 'x2', 'y2', 'manual']
            writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
            writer.writeheader()
            
            # Helper function to write a row
            def write_pair(index_val, p1, p2):
                x1 = (p1[0] - self.origin[0]) / 1000.0
                y1 = (p1[1] - self.origin[1]) / 1000.0
                # If p2 is None (landmark case), set x2/y2 to 0
                if p2 is None:
                    x2 = 0.0
                    y2 = 0.0
                else:
                    x2 = (p2[0] - self.origin[0]) / 1000.0
                    y2 = (p2[1] - self.origin[1]) / 1000.0
                
                writer.writerow({
                    'Index': index_val,
                    'x1': x1, 
                    'y1': y1, 
                    'x2': x2, 
                    'y2': y2, 
                    'manual': True
                })

            if self.landmark_1:
                write_pair("Landmark1", self.landmark_1, None)
            if self.landmark_2:
                write_pair("Landmark2", self.landmark_2, None)

            for i, (p1, p2) in enumerate(self.current_pairs):
                write_pair(i, p1, p2)
