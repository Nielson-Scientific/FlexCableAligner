import numpy as np


class Translator:
    def __init__(self, c1, c2, s1, s2):
        self.R = self.get_rotation_matrix(c1, c2, s1, s2)
    
    def get_stage_point_from_cable_point(self, cable_point):
        c = np.array([cable_point[0], cable_point[1], 1], dtype = float)
        c = c.reshape(-1,1) # reshape to column
        s = self.R @ c
        s_x, s_y, _ = s.ravel()
        return (s_x, s_y)
    
    def get_cable_point_from_stage_point(self, stage_point):
        s = np.array([stage_point[0], stage_point[1], 1], dtype = float)
        s = s.reshape(-1,1) # reshape to column
        c = np.linalg.solve(self.R, s)
        c_x, c_y, _ = c.ravel()
        return (c_x, c_y)

    def get_rotation_matrix(self, c1, c2, s1, s2):
        A = np.array([
            [c1[0], -1*c1[1], 0, 1],
            [c1[1],    c1[0], 1, 0],
            [c2[0], -1*c2[1], 0, 1],
            [c2[1],    c2[0], 1, 0]
            ],
            dtype = float
        )
        s = np.array([s1[0], s1[1], s2[0], s2[1]])
        s = s.reshape(-1,1) # reshape to column
        x = np.linalg.solve(A,s)

        a,b,t_1,t_2   = x.ravel()
        rot_matrix = np.array([
            [a, -1*b, t_1],
            [b,    a, t_2],
            [0,    0,   1]
            ],
            dtype = float
        )
        return rot_matrix