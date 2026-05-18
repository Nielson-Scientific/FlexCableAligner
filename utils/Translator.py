import numpy as np


class Translator:
    def __init__(self, c1, c2, s1, s2, invert_x=False, invert_y=False):
        self.invert_x = bool(invert_x)
        self.invert_y = bool(invert_y)
        c1n = self._normalize_cable_point(c1)
        c2n = self._normalize_cable_point(c2)
        self.R = self.get_rotation_matrix(c1n, c2n, s1, s2)
        self._tps_forward = None   # normalized cable -> stage
        self._tps_inverse = None   # stage -> normalized cable
        self.use_tps = False

    def _normalize_cable_point(self, cable_point):
        x, y = float(cable_point[0]), float(cable_point[1])
        if self.invert_x:
            x = -x
        if self.invert_y:
            y = -y
        return (x, y)

    def _denormalize_cable_point(self, cable_point):
        # For sign-flip inversion, normalization and denormalization are identical.
        # Applying the same transform twice returns the original value.
        return self._normalize_cable_point(cable_point)
    
    def get_stage_point_from_cable_point(self, cable_point):
        cx, cy = self._normalize_cable_point(cable_point)
        if self.use_tps and self._tps_forward is not None:
            sx, sy = self._tps_forward((cx, cy))
            return (sx, sy)
        c = np.array([cx, cy, 1], dtype = float)
        c = c.reshape(-1,1) # reshape to column
        s = self.R @ c
        s_x, s_y, _ = s.ravel()
        return (s_x, s_y)
    
    
    def get_cable_point_from_stage_point(self, stage_point):
        if self.use_tps and self._tps_inverse is not None:
            c_x, c_y = self._tps_inverse((stage_point[0], stage_point[1]))
            return self._denormalize_cable_point((c_x, c_y))
        s = np.array([stage_point[0], stage_point[1], 1], dtype = float)
        s = s.reshape(-1,1) # reshape to column
        c = np.linalg.solve(self.R, s)
        c_x, c_y, _ = c.ravel()
        return self._denormalize_cable_point((c_x, c_y))

    def get_rotation_matrix(self, c1, c2, s1, s2):
        A = np.array([
            [c1[0], -1*c1[1], 1, 0],
            [c1[1],    c1[0], 0, 1],
            [c2[0], -1*c2[1], 1, 0],
            [c2[1],    c2[0], 0, 1]
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

    @staticmethod
    def _tps_kernel(r2):
        eps = 1e-12
        return r2 * np.log(r2 + eps)

    @staticmethod
    def _fit_tps_model(src_points, dst_points, regularization=1e-8):
        src = np.asarray(src_points, dtype=float)
        dst = np.asarray(dst_points, dtype=float)
        n = src.shape[0]
        if n < 3:
            raise ValueError("TPS fitting requires at least 3 point pairs.")

        diff = src[:, None, :] - src[None, :, :]
        r2 = np.sum(diff * diff, axis=2)
        K = Translator._tps_kernel(r2) + regularization * np.eye(n)
        P = np.column_stack([np.ones(n), src[:, 0], src[:, 1]])

        L = np.zeros((n + 3, n + 3), dtype=float)
        L[:n, :n] = K
        L[:n, n:] = P
        L[n:, :n] = P.T

        Y = np.zeros((n + 3, 2), dtype=float)
        Y[:n, :] = dst

        params = np.linalg.solve(L, Y)
        w = params[:n, :]   # n x 2
        a = params[n:, :]   # 3 x 2

        def evaluate(point_xy):
            p = np.asarray(point_xy, dtype=float)
            d = src - p
            rr2 = np.sum(d * d, axis=1)
            U = Translator._tps_kernel(rr2)
            out = (U @ w) + np.array([1.0, p[0], p[1]]) @ a
            return float(out[0]), float(out[1])

        return evaluate

    def fit_tps(self, cable_points, stage_points):
        if len(cable_points) != len(stage_points):
            raise ValueError("cable_points and stage_points must have equal length.")
        if len(cable_points) < 3:
            raise ValueError("TPS fitting requires at least 3 point pairs.")

        cable_norm = [self._normalize_cable_point(c) for c in cable_points]
        stage = [tuple(map(float, s)) for s in stage_points]

        self._tps_forward = self._fit_tps_model(cable_norm, stage)
        self._tps_inverse = self._fit_tps_model(stage, cable_norm)


    def set_use_tps(self, enabled: bool):
        self.use_tps = bool(enabled)
