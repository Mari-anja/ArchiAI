# TORUS — Design Report

**AAI-2601 · Stage 3 spatial coordination · Rev P03 · 2026-08-19**
ArchiAI Design Studio

---

## 1. The brief, and the one decision that answers it

The brief was a two-storey office shaped as a torus. A torus is not a
metaphor here and not a plan shape: it is a solid of revolution, a circle of
radius **7 500** swept around a vertical axis at radius **30 000**. Everything
else in this project follows from choosing that circle and then deciding where
the ground plane cuts it.

The whole geometry is:

```
P(θ, φ) = ( (30 000 + 7 500·cos φ)·cos θ,
            (30 000 + 7 500·cos φ)·sin θ,
             2 100  + 7 500·sin φ )
```

with `θ` the plan angle measured anticlockwise from east and `φ` the section
angle within the tube, zero at the outermost point of the tube and 90° at the
crown.

The tube axis sits at **+2.100**. That single number does the most work in the
project, because it fixes where the ground plane truncates the torus:

| | |
|---|---|
| Half-chord at ground level | 7 200 |
| Springing radii | 22 800 and 37 200 |
| Widest point of the shell | 37 500 at +2.100 |
| Tightest point | 22 500 at +2.100 |
| Crown | +9.600 at radius 30 000 |
| Overall diameter | 75 000 |
| Courtyard diameter | 45 000 |

The shell therefore springs directly from the paving on two concentric
circles, leans outwards to its widest at chest height, and returns to a crown
9.6 m up. There is no plinth, no base course and no ramp anywhere on the
approach: the external ground plane and FFL 00 are the same datum all the way
round the building.

## 2. Two plates, and why they came out identical

Both floors are horizontal chords of the same generating circle, placed
symmetrically about its axis at −2.100 and +2.100. Because the chords are
symmetric, they are the same length. Both plates are annuli from radius
**22 800 to 37 200** — **14 400** deep, **2 714 m²** each.

That depth is the argument for the whole building type. A 14.4 m plate glazed
on both faces puts no desk more than 7.2 m from a window, and opens the floor
to cross ventilation across its full depth. A conventional deep-plan floor of
the same area would be lit from one side and mechanically ventilated
throughout.

The cost of the geometry is paid on Level 01, where the shell curves down to
meet the slab. Head height falls below 2 100 outside radius 36 214 and inside
radius 23 786 — about 1 m at each edge, 373 m² over the floor. That strip is
not lost: it takes the perimeter services, low storage and window seating, and
it is where the curved soffit meets the glass, which is the best thing about
being on that floor. The usable Level 01 plate is 2 342 m².

Level 00 has the opposite condition. Its ceiling is the flat Level 01 slab at
**3 550** clear, and the shell bulges outwards past the slab edge by 300 mm,
so the ground floor is a straight-sided, generously lit room with a slight
outward lean to the glass. Level 01 is the shaped one, rising to **5 400**
clear at the tube centreline.

## 3. Plan

The ring is organised in three concentric bands:

- **22 800 – 26 000** — the loop. A continuous 3 200 wide circulation ring on
  the courtyard side, glazed to the court for its whole 188 m length. Every
  enclosed room opens off it. It is the social spine and the escape route at
  once.
- **26 000 – 37 200** — the occupied band, 11 200 deep.
- Four cores at 45°, 135°, 225° and 315° plug the occupied band completely,
  each 14° wide, taking a protected stair, two lifts, WCs and risers out to
  the outer face.

Placing the cores against the *outer* facade and the circulation against the
*courtyard* is the reverse of the usual arrangement, and it is deliberate. The
courtyard face is the shorter, calmer, more social elevation; giving it to
movement rather than to desks is what makes the loop worth walking.

Radial gridlines **R01–R36** at 10.00°; ring gridlines **C1–C5** at 3 600
centres. Columns on C2 and C4 give spans of 3 600 / 7 200 / 3 600 across the
plate.

The ring is broken twice at ground level:

- **South, 263°–277°** — the main entrance. A portal through the outer shell
  into a double-height hall that runs the full 14.4 m depth and continues as a
  public route out into the courtyard.
- **North, 84°–96°** — a service gateway, an undercroft 3 550 clear for
  service vehicles into the courtyard, with loading and waste either side.

Level 01 is otherwise a continuous ring, with a void over the entrance hall
from 262° to 278°; the loop crosses it as a bridge, so you can still walk the
whole circuit.

## 4. Structure

Thirty-six **CHS 457 × 16** hoop ribs at 10° centres. Each rib is a 212.52°
arc of a 7 500 radius circle — 27.82 m long — standing on two feet 14 400
apart. They are tied at their base by the ground slab and a continuous
**1 100 × 900** RC ring beam under each springing line, on 600 CFA piles.
Circumferential **CHS 219 × 10** members at close centres complete a shell
that is stiff in both directions.

The floors are composite: 130 mm lightweight concrete on 60 mm deck, on radial
**UB 457 × 191** primaries at 10° and **UB 305 × 165** secondaries at 5°,
carried on two rings of **CHS 324 × 12.5** columns with 3 600 cantilevers to
each edge. Stability comes from braced bays inside each of the four cores.

Movement joints are cut in the ground slab only, at R09, R18, R27 and R36. The
shell has no movement joints: it is continuous, and accommodates movement
through its own curvature.

## 5. Envelope

| Zone | φ from | φ to | Build-up |
|---|---|---|---|
| GL-00-EXT | −16.26° | 16.26° | Curved IGU, floor to soffit, outer face |
| GL-01-EXT | 16.26° | 62° | Curved IGU, inclined |
| CR-PV | 62° | 90° | Standing seam with integrated photovoltaic |
| CR-STD | 90° | 118° | Standing seam with rooflight slots |
| GL-01-INT | 118° | 163.74° | Curved IGU, courtyard side |
| GL-00-INT | 163.74° | 196.26° | Curved IGU, floor to soffit, courtyard |

The point worth making about fabricating a torus: **every glazing unit is
curved to the same single radius of 7 500, about the tube axis.** The surface
is developable in that direction, so no panel is doubly curved and no panel is
unique. There are 144 mullion positions around the ring and about 36 courses up
the section: 5 184 panels in total, but only ~36 *types*, because rotational
symmetry makes every panel in a given course identical. That is the
difference between this being buildable and not.

U-values: glazing 1.10, crown 0.13, ground slab 0.15 W/m²K; air permeability
3.0 m³/h·m² at 50 Pa. Developed envelope area 5 244 m², of which 628 m² carries
photovoltaic laminate.

## 6. Environment

- The outward lean of the shell below +2.100 self-shades the Level 00 glazing
  through the middle of the day. No brise-soleil is needed anywhere.
- Mixed mode. Actuated vents at both springing lines drive cross ventilation
  and night purge across the full 14.4 m plate.
- Ground-source heat pumps on a 48-borehole field under the courtyard,
  140 m deep, seasonal COP 4.1.
- The shell drains to two continuous ring gutters at the springing lines, 72
  outlets, into attenuation under the courtyard; harvested for irrigation and
  WC flushing.
- Target 55 kWh/m²/yr including small power.

## 7. Fire and access

Purpose group 3. Two storeys with the top storey at +4.200, so no firefighting
shaft is required. Four protected stairs, each 1 400 wide, discharge directly
to open air at the perimeter. Because the plan is a ring, escape is available
in two directions from everywhere; maximum travel to a protected stair is
**23.6 m** against a 45 m limit. Occupancy 657 at 1:8; stair capacity is
4 × 220 = 880, so the building clears with one stair discounted.

Fire appliance access runs around the whole perimeter road, with every dry
riser inlet within 45 m of hardstanding. The courtyard is served by hydrant
and by the northern undercroft.

## 8. Areas

| | Level 00 | Level 01 | Total |
|---|---|---|---|
| Gross internal | 2 640 m² | 2 616 m² | **5 256 m²** |
| Workstations drawn | 138 | 168 | **306** |

Footprint 2 714 m² on a 43 744 m² site — 6.2 % coverage. Courtyard 1 633 m².

## 9. Open questions for the next stage

Stated plainly, because they are real:

1. **Undercroft headroom.** The northern gateway gives 3 550 clear, which
   suits service vehicles but is below the 3 700 usually wanted for a fire
   appliance. The strategy currently relies on perimeter access and a
   courtyard hydrant instead. If the authority requires appliance access into
   the court, the Level 01 slab has to be locally raised over the gateway, or
   the gateway widened and the slab trimmed out.
2. **Cold-bending tolerance.** The 7 500 radius is a comfortable cold bend for
   the outer units but tight for the laminated inner leaf at full panel size.
   This needs a specialist review before the panel module is fixed.
3. **Level 01 perimeter.** 373 m² sits below 2 100 head height. It is
   programmed as services and seating, but it should be tested against the
   client's own space standards rather than assumed away.
4. **Cleaning and maintenance of the shell.** A crown walkway is shown; the
   flanks below +6.000 need either a mast climber running on the perimeter
   road or a rope access strategy. Not yet resolved.
5. **Acoustics of a circular courtyard.** A 45 m concave court will focus
   sound. The inner facade should carry diffusing relief or the planting
   should be denser than shown.

---

*Every drawing in this set is generated from one parametric model. Change
`MAJOR_R` or `TUBE_Z` in `src/archiai/params.py` and the plans, sections,
elevations, schedules, mesh and viewer all regenerate consistently.*
