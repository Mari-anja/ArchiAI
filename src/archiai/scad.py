"""Parametric OpenSCAD source, generated from the same parameters as the drawings."""

import os
from . import params as P

TEMPLATE = '''// =====================================================================
//  TORUS  --  two-storey office pavilion
//  %(number)s   rev %(rev)s   %(date)s
//  %(architect)s
//
//  A circle of radius r is swept around a vertical axis at distance R and
//  truncated by the ground plane.  Every other element is derived from that.
//
//  Render:   openscad -o torus-office.stl torus-office.scad
//  Preview:  F5      Full render: F6   (full render takes a few minutes)
// =====================================================================

/* [Primary geometry] */
R          = %(R).3f;    // major radius, building centre to tube centreline
r          = %(r).3f;     // tube radius
zc         = %(zc).3f;     // height of the tube axis above FFL 00
shell_t    = %(shell_t).3f;    // envelope thickness

/* [Levels] */
ffl_00     = %(ffl0).3f;
ffl_01     = %(ffl1).3f;
slab_t     = %(slab_t).3f;

/* [Grid] */
n_radial   = %(nrad)d;      // radial gridlines / hoop ribs
col_r1     = %(col0).3f;   // ring grid C2
col_r2     = %(col1).3f;   // ring grid C4
col_d      = %(cold).3f;    // column diameter
rib_d      = %(ribd).3f;    // hoop rib diameter

/* [Resolution] */
fn_ring    = 240;       // segments around the building axis
fn_tube    = 96;        // segments around the tube section

/* [Display] */
show_shell   = true;
show_floors  = true;
show_frame   = true;
show_cores   = true;
show_site    = true;
cutaway      = false;   // remove a quarter to reveal the interior
cut_from     = 266;     // degrees
cut_to       = 360;

// ---- derived --------------------------------------------------------
half_chord   = sqrt(r*r - (ffl_00 - zc)*(ffl_00 - zc));
r_in         = R - half_chord;   // %(rin).3f
r_out        = R + half_chord;   // %(rout).3f
z_apex       = zc + r;           // %(apex).3f

// =====================================================================
module tube_profile(inner = true) {
    difference() {
        circle(r = r, $fn = fn_tube);
        if (inner) circle(r = r - shell_t, $fn = fn_tube);
    }
}

module above_ground() {
    translate([0, 0, ffl_00])
        cylinder(h = z_apex + 1, r = R + r + 1, $fn = fn_ring);
}

module wedge(a0, a1, h = 60) {
    // a solid pie slice, used for cutaways and for the cores
    rotate([0, 0, a0])
        rotate_extrude(angle = a1 - a0, $fn = fn_ring)
            translate([0.001, -h/2]) square([R + r + 2, h]);
}

module shell() {
    intersection() {
        rotate_extrude($fn = fn_ring) translate([R, zc]) tube_profile(true);
        above_ground();
    }
}

module ring_slab(z, t, ri, ro) {
    translate([0, 0, z - t])
        difference() {
            cylinder(h = t, r = ro, $fn = fn_ring);
            translate([0, 0, -1]) cylinder(h = t + 2, r = ri, $fn = fn_ring);
        }
}

module floors() {
    ring_slab(ffl_00, 0.35, r_in, r_out);
    difference() {
        ring_slab(ffl_01, slab_t, r_in, r_out);
        // double-height void over the entrance hall
        rotate([0, 0, %(void0).1f])
            rotate_extrude(angle = %(voidspan).1f, $fn = fn_ring)
                translate([%(loop).3f, ffl_01 - slab_t - 0.5]) square([r_out, slab_t + 1]);
    }
}

module hoop_rib(a) {
    rotate([0, 0, a])
        rotate_extrude(angle = 0.9, $fn = fn_ring)
            translate([R, zc])
                difference() {
                    circle(r = r - shell_t, $fn = fn_tube);
                    circle(r = r - shell_t - rib_d, $fn = fn_tube);
                }
}

module frame() {
    for (i = [0 : n_radial - 1]) {
        a = i * 360 / n_radial;
        for (cr = [col_r1, col_r2])
            translate([cr * cos(a), cr * sin(a), ffl_00])
                cylinder(h = ffl_01 + 3.6, d = col_d, $fn = 16);
        intersection() { hoop_rib(a); above_ground(); }
    }
}

module cores() {
    %(cores)s
}

module site() {
    color([0.78, 0.79, 0.74]) translate([0, 0, -0.12])
        cylinder(h = 0.10, r = %(siter).1f, $fn = fn_ring);
    color([0.62, 0.71, 0.55]) translate([0, 0, -0.02])
        cylinder(h = 0.02, r = r_in, $fn = fn_ring);
    color([0.55, 0.70, 0.80]) translate([0, 0, 0.0])
        cylinder(h = 0.03, r = 7.2, $fn = fn_ring);
}

// =====================================================================
module building() {
    if (show_site)   site();
    if (show_floors) color([0.80, 0.78, 0.74]) floors();
    if (show_frame)  color([0.55, 0.58, 0.62]) frame();
    if (show_cores)  color([0.66, 0.66, 0.64]) cores();
    if (show_shell)  color([0.62, 0.72, 0.80, 0.75]) shell();
}

if (cutaway) {
    difference() { building(); wedge(cut_from, cut_to); }
} else {
    building();
}
'''


def _cores_scad():
    out = []
    for (cid, tc, half) in P.CORES:
        out.append(
            "// core %s\n    rotate([0, 0, %.1f])\n"
            "        rotate_extrude(angle = %.1f, $fn = fn_ring)\n"
            "            translate([%.3f, ffl_00])\n"
            "                square([%.3f, %.3f]);" % (
                cid, tc - half, 2 * half, P.CORE_R0,
                P.CORE_3D_R1 - P.CORE_R0, P.CORE_3D_Z))
    return "\n    ".join(out)


def write(path):
    void = next(r for r in __import__("archiai.program", fromlist=["x"]).ROOMS_01
                if r.cat == "void")
    src = TEMPLATE % {
        "number": P.PROJECT["number"], "rev": P.PROJECT["rev"],
        "date": P.PROJECT["date"], "architect": P.PROJECT["architect"],
        "R": P.MAJOR_R, "r": P.TUBE_R, "zc": P.TUBE_Z, "shell_t": P.ENV_T,
        "ffl0": P.FFL_00, "ffl1": P.FFL_01, "slab_t": P.SLAB_T,
        "nrad": P.RADIAL_DIV, "col0": P.COL_RADII[0], "col1": P.COL_RADII[1],
        "cold": P.COL_DIA, "ribd": P.RIB_DIA,
        "rin": P.R_IN_00, "rout": P.R_OUT_00, "apex": P.Z_APEX,
        "void0": void.t0, "voidspan": void.t1 - void.t0, "loop": P.R_LOOP,
        "cores": _cores_scad(), "siter": P.SITE_R * 0.6,
    }
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        fh.write(src)
    return path
