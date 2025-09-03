pos_line = "X:1.5 Y:2.5 Z:5 A:4.00 B:3.5 C:30 Count X:0 Y:0 Z:0"
pos_line = pos_line.split('Count')[0]  # Ignore anything after 'Count'
vals: dict[str, float] = {}
for token in pos_line.replace(',', ' ').split():
    if ':' not in token:
        continue
    k, v = token.split(':', 1)
    k = k.strip().lower()
    # Clean numeric value (strip trailing non-number chars)
    vnum = ''
    for ch in v:
        if ch in '+-0123456789.eE':
            vnum += ch
        else:
            break
    try:
        vals[k] = float(vnum)
    except Exception:
        pass
return_dict =  {
    'x': float(vals.get('x', 0.0)),
    'y': float(vals.get('y', 0.0)),
    'z': float(vals.get('z', 0.0)),
    'a': float(vals.get('a', 0.0)),
    'b': float(vals.get('b', 0.0)),
    'c': float(vals.get('c', 0.0)),
}
print(return_dict)