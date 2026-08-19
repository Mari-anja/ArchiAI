"""
TORUS OFFICE  --  single source of truth for the building's geometry.

Everything downstream (plans, sections, elevations, schedules, the 3D mesh,
the OpenSCAD source and the web viewer) is derived from the constants in this
module.  Change a number here and the whole document set regenerates
consistently.

GEOMETRIC PARTI
---------------
The building is a true torus: a circle of radius `TUBE_R` swept around a
vertical axis at distance `MAJOR_R`.  The torus is truncated by the ground
plane, which cuts it exactly at the level of the ground-floor slab, so the
curved shell springs directly from the paving on two concentric circles.

    P(theta, phi) = ( (MAJOR_R + TUBE_R*cos(phi)) * cos(theta),
                      (MAJOR_R + TUBE_R*cos(phi)) * sin(theta),
                      TUBE_Z  + TUBE_R*sin(phi) )

    theta : plan angle, measured CCW from East (+X).  North = +Y = 90 deg.
    phi   : section angle within the tube.  phi=0 is the outermost point of
            the tube, phi=90 the crown, phi=180 the courtyard-most point.

The two floor plates are horizontal chords of that circular section, placed
symmetrically about the tube axis, which is why they come out as identical
annuli -- a happy consequence of the geometry rather than a drafting choice.
"""

import math

# ---------------------------------------------------------------------------
# PRIMARY GEOMETRY  (metres)
# ---------------------------------------------------------------------------
MAJOR_R = 30.000   # radius from building centre to the tube centreline
TUBE_R  = 7.500    # radius of the swept circular section
TUBE_Z  = 2.100    # height of the tube axis above ground-floor FFL

FFL_00 = 0.000     # Level 00 finished floor level (site datum +0.00 = 42.60 AOD)
FFL_01 = 4.200     # Level 01 finished floor level
SITE_DATUM_AOD = 42.600

# ---------------------------------------------------------------------------
# DERIVED SECTION GEOMETRY
# ---------------------------------------------------------------------------
def phi_at_z(z, upper=True):
    """Section angle phi at which the tube surface crosses height `z`.

    Returns the outer-side solution when `upper` is True (phi in -90..90),
    the courtyard-side solution otherwise.
    """
    s = (z - TUBE_Z) / TUBE_R
    s = max(-1.0, min(1.0, s))
    a = math.degrees(math.asin(s))
    return a if upper else 180.0 - a

def half_chord(z):
    """Horizontal half-width of the tube section at height `z`."""
    dz = z - TUBE_Z
    return math.sqrt(max(0.0, TUBE_R * TUBE_R - dz * dz))

# Ground plane cuts the tube here:
HALF_CHORD_00 = half_chord(FFL_00)          # 7.200
HALF_CHORD_01 = half_chord(FFL_01)          # 7.200  (symmetric about TUBE_Z)

R_IN_00  = MAJOR_R - HALF_CHORD_00          # 22.800  courtyard edge, Level 00
R_OUT_00 = MAJOR_R + HALF_CHORD_00          # 37.200  outer edge,     Level 00
R_IN_01  = MAJOR_R - HALF_CHORD_01          # 22.800  courtyard edge, Level 01
R_OUT_01 = MAJOR_R + HALF_CHORD_01          # 37.200  outer edge,     Level 01

R_MAX = MAJOR_R + TUBE_R                    # 37.500  widest point of the shell
R_MIN = MAJOR_R - TUBE_R                    # 22.500  tightest point of the shell
Z_APEX = TUBE_Z + TUBE_R                    #  9.600  top of the shell

PHI_SPRING_OUT = phi_at_z(FFL_00, True)     # -16.26  outer springing at ground
PHI_SPRING_IN  = phi_at_z(FFL_00, False)    # 196.26  courtyard springing at ground
PHI_L01_OUT    = phi_at_z(FFL_01, True)     #  16.26  L01 slab meets outer shell
PHI_L01_IN     = phi_at_z(FFL_01, False)    # 163.74  L01 slab meets inner shell

OVERALL_DIA   = 2 * R_MAX                   # 75.000
COURTYARD_DIA = 2 * R_MIN                   # 45.000
FOOTPRINT_DIA = 2 * R_OUT_00                # 74.400

# ---------------------------------------------------------------------------
# HEADROOM  --  on Level 01 the shell curves down to meet the slab, so the
# outermost / innermost strips of the plate are below habitable head height.
# ---------------------------------------------------------------------------
CLEAR_HEIGHT_MIN = 2.100                    # habitable-height threshold
_dz = (FFL_01 + CLEAR_HEIGHT_MIN) - TUBE_Z
_u  = math.sqrt(TUBE_R * TUBE_R - _dz * _dz)
R_OUT_01_USABLE = MAJOR_R + _u              # 36.214
R_IN_01_USABLE  = MAJOR_R - _u              # 23.786
HEAD_L01_CROWN  = Z_APEX - FFL_01           #  5.400  at the tube centreline

SLAB_T      = 0.300    # composite slab + deck structural depth
CEIL_ZONE   = 0.350    # services + ceiling zone below L01 slab
CLEAR_L00   = FFL_01 - SLAB_T - CEIL_ZONE   # 3.550 clear on the ground floor

# ---------------------------------------------------------------------------
# STRUCTURAL GRID
# ---------------------------------------------------------------------------
RADIAL_DIV     = 36                 # primary radial gridlines / arch ribs
RADIAL_STEP    = 360.0 / RADIAL_DIV # 10.0 deg
SECONDARY_STEP = RADIAL_STEP / 2.0  # 5.0 deg  secondary floor beams

RING_GRID = [22.800, 26.400, 30.000, 33.600, 37.200]   # C1..C5, 3.6 m centres
COL_RADII = [26.400, 33.600]                           # C2 and C4 carry columns
COL_DIA   = 0.324                                      # CHS 324 x 12.5

RIB_DIA    = 0.457    # CHS 457 x 16  primary hoop rib
PURLIN_DIA = 0.219    # CHS 219 x 10  circumferential shell member

def grid_label(i):
    """Radial gridline label for index i (0-based, i=0 at theta=0 / East)."""
    return "R%02d" % (i + 1)

RING_LABELS = ["C1", "C2", "C3", "C4", "C5"]

# ---------------------------------------------------------------------------
# ENVELOPE ZONES  (section angle phi, degrees)
# ---------------------------------------------------------------------------
ENVELOPE = [
    ("GL-00-EXT", PHI_SPRING_OUT, PHI_L01_OUT,  "glazing", "L00 outer facade - curved IGU, floor to soffit"),
    ("GL-01-EXT", PHI_L01_OUT,    62.0,         "glazing", "L01 outer facade - inclined curved IGU"),
    ("CR-PV",     62.0,           90.0,         "crown",   "Crown - insulated standing-seam + integrated PV"),
    ("CR-STD",    90.0,           118.0,        "crown",   "Crown - insulated standing-seam + rooflight slots"),
    ("GL-01-INT", 118.0,          PHI_L01_IN,   "glazing", "L01 courtyard facade - inclined curved IGU"),
    ("GL-00-INT", PHI_L01_IN,     PHI_SPRING_IN,"glazing", "L00 courtyard facade - curved IGU, floor to soffit"),
]
MULLION_STEP_OUT = 2.5    # deg, outer half of the shell  -> 1.64 m at R_MAX
MULLION_STEP_IN  = 5.0    # deg, courtyard half           -> 1.96 m at R_MIN

# ---------------------------------------------------------------------------
# PLAN ORGANISATION
# ---------------------------------------------------------------------------
CORES = [                       # (id, centre theta, half-width in degrees)
    ("A", 45.0,  7.0),
    ("B", 135.0, 7.0),
    ("C", 225.0, 7.0),
    ("D", 315.0, 7.0),
]
CORE_R0, CORE_R1 = 26.000, 37.200     # cores plug the occupied band, loop passes inboard
# The core enclosure is shown in the 3D model as a simplified volume kept
# clear of the curving shell, so it does not poke through the envelope.
CORE_3D_R1, CORE_3D_Z = 35.600, 5.000

ENTRANCE_THETA   = 270.0    # main entrance, due south
GATEWAY_THETA    =  90.0    # service / fire-tender undercroft, due north
GATEWAY_HALF     =   6.0    # deg  -> 6.28 m clear at the tube centreline
PASSAGE_HALF     =   8.0    # deg  public route through the ring at the entrance

LOOP_W = 3.200              # width of the courtyard-side circulation loop
R_LOOP = R_IN_00 + LOOP_W   # 26.000  inner edge of the occupied band

VOID_T0, VOID_T1 = 262.0, 278.0     # double-height void over the entrance hall
BRIDGE_T0, BRIDGE_T1 = 268.0, 272.0 # link bridge across the void, courtyard side

# ---------------------------------------------------------------------------
# SITE
# ---------------------------------------------------------------------------
SITE_R      = 118.0   # radius of the landscaped site shown on the site plan
APPROACH_W  = 12.0    # width of the southern approach
RING_ROAD_R = 52.0    # perimeter service road centreline radius

PROJECT = {
    "name":     "TORUS",
    "subtitle": "Two-storey office pavilion",
    "number":   "AAI-2601",
    "client":   "ArchiAI",
    "architect":"ArchiAI Design Studio",
    "status":   "STAGE 3  /  SPATIAL COORDINATION",
    "rev":      "P03",
    "date":     "2026-08-19",
}


# ---------------------------------------------------------------------------
# PLAN CUT
# ---------------------------------------------------------------------------
CUT_ABOVE_FFL = 1.500       # conventional plan cut height
ENV_T = 0.350               # envelope build-up thickness (mullion + cavity + lining)

def cut_z(level):
    return (FFL_00 if level == 0 else FFL_01) + CUT_ABOVE_FFL

def cut_radii(level):
    """Inner and outer radius at which the plan cut passes through the shell.

    On Level 00 the cut is *outside* the slab edge (the tube still bulging
    outwards); on Level 01 it is *inside* it (the tube already curving back).
    That difference is why the two plans read so differently.
    """
    h = half_chord(cut_z(level))
    return (MAJOR_R - h, MAJOR_R + h)

def slab_edges(level):
    return (R_IN_00, R_OUT_00) if level == 0 else (R_IN_01, R_OUT_01)


# ---------------------------------------------------------------------------
# SECTION / ELEVATION SET-OUT
# Cutting planes are placed midway between radial gridlines so that the
# section flags never collide with the grid bubbles.
# ---------------------------------------------------------------------------
SEC_AA = (85.0, 265.0)      # through the service gateway and the entrance hall
SEC_BB = (355.0, 175.0)     # through Studio South-East and the auditorium
DET_THETA = 25.0            # angle of the typical-bay detail section
