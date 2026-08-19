// =====================================================================
//  TORUS  --  two-storey office pavilion
//  AAI-2601   rev P03   2026-08-19
//  ArchiAI Design Studio
//
//  A circle of radius r is swept around a vertical axis at distance R and
//  truncated by the ground plane.  Every other element is derived from that.
//
//  Render:   openscad -o torus-office.stl torus-office.scad
//  Preview:  F5      Full render: F6   (full render takes a few minutes)
// =====================================================================

/* [Primary geometry] */
R          = 30.000;    // major radius, building centre to tube centreline
r          = 7.500;     // tube radius
zc         = 2.100;     // height of the tube axis above FFL 00
shell_t    = 0.350;    // envelope thickness

/* [Levels] */
ffl_00     = 0.000;
ffl_01     = 4.200;
slab_t     = 0.300;

/* [Grid] */
n_radial   = 36;      // radial gridlines / hoop ribs
col_r1     = 26.400;   // ring grid C2
col_r2     = 33.600;   // ring grid C4
col_d      = 0.324;    // column diameter
rib_d      = 0.457;    // hoop rib diameter

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
r_in         = R - half_chord;   // 22.800
r_out        = R + half_chord;   // 37.200
z_apex       = zc + r;           // 9.600

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
        rotate([0, 0, 262.0])
            rotate_extrude(angle = 16.0, $fn = fn_ring)
                translate([26.000, ffl_01 - slab_t - 0.5]) square([r_out, slab_t + 1]);
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
    // core A
    rotate([0, 0, 38.0])
        rotate_extrude(angle = 14.0, $fn = fn_ring)
            translate([26.000, ffl_00])
                square([9.600, 5.000]);
    // core B
    rotate([0, 0, 128.0])
        rotate_extrude(angle = 14.0, $fn = fn_ring)
            translate([26.000, ffl_00])
                square([9.600, 5.000]);
    // core C
    rotate([0, 0, 218.0])
        rotate_extrude(angle = 14.0, $fn = fn_ring)
            translate([26.000, ffl_00])
                square([9.600, 5.000]);
    // core D
    rotate([0, 0, 308.0])
        rotate_extrude(angle = 14.0, $fn = fn_ring)
            translate([26.000, ffl_00])
                square([9.600, 5.000]);
}

module site() {
    color([0.78, 0.79, 0.74]) translate([0, 0, -0.12])
        cylinder(h = 0.10, r = 70.8, $fn = fn_ring);
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
