"""Wavefront OBJ export of the whole building, from the same parameters."""

import math, os
from . import params as P
from . import program as PG

T_STEP = 2.5      # degrees around the building axis  (matches the mullion grid)
P_STEP = 4.0      # degrees around the tube section


class Mesh:
    def __init__(self):
        self.v, self.vn = [], []
        self._vi, self._ni = {}, {}      # dedup tables
        self.groups = []          # (name, material, [ (vidx, nidx) faces ])
        self._cur = None

    def group(self, name, material):
        self._cur = (name, material, [])
        self.groups.append(self._cur)

    def vert(self, p):
        k = (round(p[0], 4), round(p[1], 4), round(p[2], 4))
        i = self._vi.get(k)
        if i is None:
            self.v.append(k)
            i = self._vi[k] = len(self.v)
        return i

    def norm(self, n):
        k = (round(n[0], 4), round(n[1], 4), round(n[2], 4))
        i = self._ni.get(k)
        if i is None:
            self.vn.append(k)
            i = self._ni[k] = len(self.vn)
        return i

    def face(self, idx):
        self._cur[2].append(idx)

    def quad(self, a, b, c, d):
        self.face([a, b, c, d])

    def write(self, path, mtl_name):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w") as fh:
            fh.write("# TORUS -- two-storey office pavilion\n")
            fh.write("# %s  %s  rev %s\n" % (P.PROJECT["number"], P.PROJECT["name"],
                                             P.PROJECT["rev"]))
            fh.write("# Units: metres.  Origin at the centre of the torus, FFL 00.\n")
            fh.write("# Major radius %.3f, tube radius %.3f, tube axis at +%.3f\n" % (
                P.MAJOR_R, P.TUBE_R, P.TUBE_Z))
            fh.write("mtllib %s\n" % mtl_name)
            for x, y, z in self.v:
                fh.write("v %.4f %.4f %.4f\n" % (x, y, z))
            for x, y, z in self.vn:
                fh.write("vn %.4f %.4f %.4f\n" % (x, y, z))
            for name, mat, faces in self.groups:
                if not faces:
                    continue
                fh.write("g %s\no %s\nusemtl %s\n" % (name, name, mat))
                for fidx in faces:
                    fh.write("f " + " ".join("%d//%d" % (a, b) for (a, b) in fidx) + "\n")
        return path

    @property
    def face_count(self):
        return sum(len(f) for _, _, f in self.groups)


MATERIALS = [
    ("glazing",  (0.62, 0.72, 0.80), 0.30, 0.55),
    ("crown",    (0.72, 0.74, 0.72), 0.10, 0.35),
    ("pv",       (0.13, 0.16, 0.20), 0.55, 0.70),
    ("concrete", (0.80, 0.78, 0.74), 0.04, 0.10),
    ("steel",    (0.55, 0.58, 0.62), 0.42, 0.55),
    ("core",     (0.66, 0.66, 0.64), 0.06, 0.15),
    ("grass",    (0.62, 0.71, 0.55), 0.02, 0.05),
    ("ground",   (0.78, 0.79, 0.74), 0.02, 0.05),
    ("water",    (0.55, 0.70, 0.80), 0.60, 0.85),
    ("timber",   (0.68, 0.60, 0.48), 0.06, 0.15),
]


def write_mtl(path):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write("# TORUS materials\n")
        for name, (r, g, b), ks, ns in MATERIALS:
            fh.write("\nnewmtl %s\n" % name)
            fh.write("Ka %.3f %.3f %.3f\n" % (r * 0.35, g * 0.35, b * 0.35))
            fh.write("Kd %.3f %.3f %.3f\n" % (r, g, b))
            fh.write("Ks %.3f %.3f %.3f\n" % (ks, ks, ks))
            fh.write("Ns %.1f\n" % (ns * 200))
            if name == "glazing":
                fh.write("d 0.72\n")
            else:
                fh.write("d 1.0\n")
    return path


# ---------------------------------------------------------------------------
def surf(theta, phi, rad):
    t, p = math.radians(theta), math.radians(phi)
    rho = P.MAJOR_R + rad * math.cos(p)
    return (rho * math.cos(t), rho * math.sin(t), P.TUBE_Z + rad * math.sin(p))


def shell_normal(theta, phi, outward=True):
    t, p = math.radians(theta), math.radians(phi)
    n = (math.cos(p) * math.cos(t), math.cos(p) * math.sin(t), math.sin(p))
    return n if outward else (-n[0], -n[1], -n[2])


BANDS = [
    ("shell_glazing_L00_outer", "glazing", P.PHI_SPRING_OUT, P.PHI_L01_OUT),
    ("shell_glazing_L01_outer", "glazing", P.PHI_L01_OUT, 62.0),
    ("shell_crown_pv",          "pv",      62.0, 88.0),
    ("shell_crown",             "crown",   88.0, 118.0),
    ("shell_glazing_L01_inner", "glazing", 118.0, P.PHI_L01_IN),
    ("shell_glazing_L00_inner", "glazing", P.PHI_L01_IN, P.PHI_SPRING_IN),
]


def _phi_range(p0, p1):
    out, p = [], p0
    while p < p1 - 1e-9:
        out.append((p, min(p + P_STEP, p1)))
        p += P_STEP
    return out


def build_shell(m):
    nt = int(round(360.0 / T_STEP))
    r_out, r_in = P.TUBE_R, P.TUBE_R - P.ENV_T
    for (name, mat, a0, a1) in BANDS:
        m.group(name, mat)
        for (pa, pb) in _phi_range(a0, a1):
            for i in range(nt):
                ta, tb = i * T_STEP, (i + 1) * T_STEP
                q = []
                for (t, p) in ((ta, pa), (tb, pa), (tb, pb), (ta, pb)):
                    vi = m.vert(surf(t, p, r_out))
                    ni = m.norm(shell_normal(t, p, True))
                    q.append((vi, ni))
                m.quad(*q)
    # inner face of the shell, so the model is a solid with thickness
    m.group("shell_lining", "crown")
    for (pa, pb) in _phi_range(P.PHI_SPRING_OUT, P.PHI_SPRING_IN):
        for i in range(nt):
            ta, tb = i * T_STEP, (i + 1) * T_STEP
            q = []
            for (t, p) in ((ta, pa), (ta, pb), (tb, pb), (tb, pa)):
                vi = m.vert(surf(t, p, r_in))
                ni = m.norm(shell_normal(t, p, False))
                q.append((vi, ni))
            m.quad(*q)
    # springing edges, closing the shell onto the ground
    m.group("shell_springing", "steel")
    for phi, up in ((P.PHI_SPRING_OUT, False), (P.PHI_SPRING_IN, True)):
        n = (0.0, 0.0, -1.0)
        for i in range(nt):
            ta, tb = i * T_STEP, (i + 1) * T_STEP
            pts = [surf(ta, phi, r_out), surf(tb, phi, r_out),
                   surf(tb, phi, r_in), surf(ta, phi, r_in)]
            if up:
                pts.reverse()
            q = [(m.vert(p), m.norm(n)) for p in pts]
            m.quad(*q)


def _annulus(m, z, thickness, r0, r1, t0=0.0, t1=360.0, step=T_STEP):
    n = max(1, int(round((t1 - t0) / step)))
    zb = z - thickness
    for i in range(n):
        ta = t0 + (t1 - t0) * i / n
        tb = t0 + (t1 - t0) * (i + 1) / n
        ca, sa = math.cos(math.radians(ta)), math.sin(math.radians(ta))
        cb, sb = math.cos(math.radians(tb)), math.sin(math.radians(tb))
        A = (r0 * ca, r0 * sa, z); B = (r1 * ca, r1 * sa, z)
        C = (r1 * cb, r1 * sb, z); D = (r0 * cb, r0 * sb, z)
        up = m.norm((0, 0, 1)); dn = m.norm((0, 0, -1))
        m.quad((m.vert(A), up), (m.vert(B), up), (m.vert(C), up), (m.vert(D), up))
        A2 = (A[0], A[1], zb); B2 = (B[0], B[1], zb)
        C2 = (C[0], C[1], zb); D2 = (D[0], D[1], zb)
        m.quad((m.vert(D2), dn), (m.vert(C2), dn), (m.vert(B2), dn), (m.vert(A2), dn))
        for (p, q, r, ss, nx) in ((B, C, C2, B2, (cb, sb, 0)), (D, A, A2, D2, (-ca, -sa, 0))):
            nn = m.norm(nx)
            m.quad((m.vert(p), nn), (m.vert(q), nn), (m.vert(r), nn), (m.vert(ss), nn))


def build_floors(m):
    m.group("slab_L00", "concrete")
    _annulus(m, P.FFL_00, 0.35, P.R_IN_00, P.R_OUT_00)
    m.group("slab_L01", "concrete")
    for (a0, a1) in ((0.0, PG.ROOMS_01[0].t0 + 0.0),):
        pass
    voids = [(r.t0, r.t1) for r in PG.ROOMS_01 if r.cat == "void"]
    spans, cur = [], 0.0
    for (a, b) in sorted(voids):
        if a > cur:
            spans.append((cur, a))
        cur = b
    spans.append((cur, 360.0))
    for (a, b) in spans:
        _annulus(m, P.FFL_01, P.SLAB_T, P.R_IN_00, P.R_OUT_00, a, b)
    for (a, b) in voids:                 # the loop continues as a bridge
        _annulus(m, P.FFL_01, P.SLAB_T, P.R_IN_00, P.R_LOOP, a, b)


def _cylinder(m, cx, cy, z0, z1, r, sides=14, mat_normal_up=True):
    for i in range(sides):
        a = 2 * math.pi * i / sides
        b = 2 * math.pi * (i + 1) / sides
        pa = (cx + r * math.cos(a), cy + r * math.sin(a))
        pb = (cx + r * math.cos(b), cy + r * math.sin(b))
        na = m.norm((math.cos(a), math.sin(a), 0))
        nb = m.norm((math.cos(b), math.sin(b), 0))
        m.quad((m.vert((pa[0], pa[1], z0)), na), (m.vert((pb[0], pb[1], z0)), nb),
               (m.vert((pb[0], pb[1], z1)), nb), (m.vert((pa[0], pa[1], z1)), na))


def build_frame(m):
    m.group("columns", "steel")
    for i in range(P.RADIAL_DIV):
        t = math.radians(i * P.RADIAL_STEP)
        for r in P.COL_RADII:
            x, y = r * math.cos(t), r * math.sin(t)
            _cylinder(m, x, y, P.FFL_00, P.FFL_01 - P.SLAB_T, P.COL_DIA / 2.0)
            _cylinder(m, x, y, P.FFL_01, P.FFL_01 + 3.6, P.COL_DIA / 2.0)
    m.group("hoop_ribs", "steel")
    rad = P.TUBE_R - P.ENV_T - P.RIB_DIA / 2.0
    for i in range(P.RADIAL_DIV):
        th = i * P.RADIAL_STEP
        pts = []
        n = 72
        for k in range(n + 1):
            phi = P.PHI_SPRING_OUT + (P.PHI_SPRING_IN - P.PHI_SPRING_OUT) * k / n
            pts.append((phi, surf(th, phi, rad)))
        hw = math.radians(P.RIB_DIA / 2.0 / P.MAJOR_R) * 180.0 / math.pi
        for k in range(n):
            p0, c0 = pts[k]
            p1, c1 = pts[k + 1]
            for off in (-P.RIB_DIA / 2.0, P.RIB_DIA / 2.0):
                d0 = _tangential_offset(th, c0, off)
                d1 = _tangential_offset(th, c1, off)
                a0 = surf(th, p0, rad + P.RIB_DIA / 2.0)
                a1 = surf(th, p1, rad + P.RIB_DIA / 2.0)
                nn = m.norm(shell_normal(th, (p0 + p1) / 2.0, False))
                m.quad((m.vert(d0), nn), (m.vert(d1), nn), (m.vert(a1), nn), (m.vert(a0), nn))


def _tangential_offset(theta, pt, off):
    t = math.radians(theta)
    return (pt[0] - math.sin(t) * off, pt[1] + math.cos(t) * off, pt[2])


def build_cores(m):
    m.group("cores", "core")
    for (cid, tc, half) in P.CORES:
        for a in (tc - half, tc + half):
            t = math.radians(a)
            p0 = (P.CORE_R0 * math.cos(t), P.CORE_R0 * math.sin(t))
            p1 = (P.CORE_3D_R1 * math.cos(t), P.CORE_3D_R1 * math.sin(t))
            nx = m.norm((-math.sin(t), math.cos(t), 0))
            m.quad((m.vert((p0[0], p0[1], P.FFL_00)), nx),
                   (m.vert((p1[0], p1[1], P.FFL_00)), nx),
                   (m.vert((p1[0], p1[1], P.CORE_3D_Z)), nx),
                   (m.vert((p0[0], p0[1], P.CORE_3D_Z)), nx))
        n = 8
        for k in range(n):
            ta = tc - half + 2 * half * k / n
            tb = tc - half + 2 * half * (k + 1) / n
            for r, sgn in ((P.CORE_R0, -1), (P.CORE_3D_R1, 1)):
                ca, sa = math.cos(math.radians(ta)), math.sin(math.radians(ta))
                cb, sb = math.cos(math.radians(tb)), math.sin(math.radians(tb))
                nn = m.norm((sgn * math.cos(math.radians((ta + tb) / 2)),
                             sgn * math.sin(math.radians((ta + tb) / 2)), 0))
                m.quad((m.vert((r * ca, r * sa, P.FFL_00)), nn),
                       (m.vert((r * cb, r * sb, P.FFL_00)), nn),
                       (m.vert((r * cb, r * sb, P.CORE_3D_Z)), nn),
                       (m.vert((r * ca, r * sa, P.CORE_3D_Z)), nn))


def build_ground(m):
    m.group("site", "ground")
    _disc(m, -0.05, 0.0, P.SITE_R * 0.6, step=6.0)
    m.group("courtyard", "grass")
    _disc(m, 0.0, 7.6, P.R_IN_00, step=6.0)
    m.group("pool", "water")
    _disc(m, 0.05, 0.0, 7.2, step=6.0)


def _disc(m, z, r0, r1, step=6.0):
    n = int(round(360.0 / step))
    up = m.norm((0, 0, 1))
    for i in range(n):
        ta, tb = math.radians(i * step), math.radians((i + 1) * step)
        A = (r0 * math.cos(ta), r0 * math.sin(ta), z)
        B = (r1 * math.cos(ta), r1 * math.sin(ta), z)
        C = (r1 * math.cos(tb), r1 * math.sin(tb), z)
        D = (r0 * math.cos(tb), r0 * math.sin(tb), z)
        m.quad((m.vert(A), up), (m.vert(B), up), (m.vert(C), up), (m.vert(D), up))


def build_furniture(m):
    m.group("desks", "timber")
    for level, z in ((0, P.FFL_00), (1, P.FFL_01)):
        polys, _ = PG.desks(level)
        up = m.norm((0, 0, 1))
        for pts in polys:
            q = [(m.vert((x, y, z + 0.74)), up) for (x, y) in pts]
            m.quad(*q)


def export(obj_path, mtl_path):
    m = Mesh()
    build_ground(m)
    build_floors(m)
    build_frame(m)
    build_cores(m)
    build_furniture(m)
    build_shell(m)
    write_mtl(mtl_path)
    m.write(obj_path, os.path.basename(mtl_path))
    return m
