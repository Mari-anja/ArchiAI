"""Emit the self-contained WebGL viewer with the model parameters injected."""

import json, math, os
from . import params as P
from . import program as PG

HERE = os.path.dirname(os.path.abspath(__file__))
TEMPLATE = os.path.join(HERE, "assets", "viewer.html")


def _desks():
    out = []
    for level in (0, 1):
        polys, _ = PG.desks(level)
        for pts in polys:
            row = [level]
            for (x, y) in pts:
                row += [round(x, 3), round(y, 3)]
            out.append(row)
    return out


def params():
    void = next(r for r in PG.ROOMS_01 if r.cat == "void")
    return {
        "R": P.MAJOR_R, "r": P.TUBE_R, "zc": P.TUBE_Z, "shellT": P.ENV_T,
        "ffl1": P.FFL_01, "slabT": P.SLAB_T,
        "rIn": P.R_IN_00, "rOut": P.R_OUT_00, "rLoop": P.R_LOOP,
        "siteR": round(P.SITE_R * 0.6, 3),
        "nRadial": P.RADIAL_DIV, "colR": P.COL_RADII,
        "colD": P.COL_DIA, "ribD": P.RIB_DIA,
        "phi0": round(P.PHI_SPRING_OUT, 4), "phi1": round(P.PHI_SPRING_IN, 4),
        "cores": [[t, h] for (_, t, h) in P.CORES],
        "coreR0": P.CORE_R0, "coreR1": P.CORE_R1,
        "core3dR1": P.CORE_3D_R1, "core3dZ": P.CORE_3D_Z,
        "void0": void.t0, "void1": void.t1,
        "gia": int(round(PG.gia(0) + PG.gia(1))),
        "desks": _desks(),
    }


def write(path):
    with open(TEMPLATE) as fh:
        html = fh.read()
    html = html.replace("__PARAMS__", json.dumps(params(), separators=(",", ":")))
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(html)
    return path
