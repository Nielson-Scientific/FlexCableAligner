import ezdxf
from scipy.spatial import KDTree

def load_dxf(filepath):
    try:
        doc = ezdxf.readfile(filepath)
    except IOError:
        raise Exception(f"Not a DXF file or a generic I/O error: {filepath}")
    except ezdxf.DXFStructureError:
        raise Exception(f"Invalid or corrupted DXF file: {filepath}")

    msp = doc.modelspace()
    
    lines = []
    points = []
    
    for entity in msp:
        if entity.dxftype() == 'LINE':
            start = entity.dxf.start
            end = entity.dxf.end
            lines.append(((start.x, start.y), (end.x, end.y)))
            points.append((start.x, start.y))
            points.append((end.x, end.y))
        
        elif entity.dxftype() == 'LWPOLYLINE':
            # get_points returns list of (x, y, start_width, end_width, bulge)
            polyline_points = entity.get_points()
            pts = [(p[0], p[1]) for p in polyline_points]
            
            for i in range(len(pts) - 1):
                lines.append((pts[i], pts[i+1]))
                points.append(pts[i])
            points.append(pts[-1])
            
            if entity.is_closed:
                lines.append((pts[-1], pts[0]))

        elif entity.dxftype() == 'POLYLINE':
            # 2D POLYLINE
            if entity.is_2d_polyline or entity.is_3d_polyline:
                pts = [(v.dxf.location.x, v.dxf.location.y) for v in entity.vertices]
                if len(pts) > 1:
                    for i in range(len(pts) - 1):
                        lines.append((pts[i], pts[i+1]))
                        points.append(pts[i])
                    points.append(pts[-1])
                    
                    if entity.is_closed:
                        lines.append((pts[-1], pts[0]))

    unique_points = list(set(points))
    
    kdtree = None
    if unique_points:
        kdtree = KDTree(unique_points)
        
    return lines, unique_points, kdtree
