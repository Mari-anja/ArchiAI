# TORUS — Drawing Register

**AAI-2601 · Stage 3 spatial coordination · Rev P03 · 2026-08-19**

All sheets ISO A1 (841 × 594 mm), issued as SVG. Line weights follow
ISO 128 (0.13 / 0.18 / 0.25 / 0.35 / 0.50 / 0.70 mm).

| Number | Title | Scale @ A1 | Contents |
|---|---|---|---|
| AAI-2601-A-000 | Cover Sheet and Drawing Register | — | Key metrics, hero cutaway, register |
| AAI-2601-A-010 | Site Plan | 1:500 | Approach, ring road, parking, landscape, levels |
| AAI-2601-A-100 | Level 00 — Ground Floor Plan | 1:150 | Full plan, grid, cores, furniture, dimensions |
| AAI-2601-A-101 | Level 01 — First Floor Plan | 1:150 | Neighbourhoods, focus cells, void, headroom zone |
| AAI-2601-A-102 | Roof Plan | 1:150 | Crown, PV array, rooflights, gutters, walkway |
| AAI-2601-A-200 | Elevations — South and East | 1:150 | With envelope-zone table |
| AAI-2601-A-201 | Elevations — North and West | 1:150 | With envelope-zone table |
| AAI-2601-A-202 | Developed Elevations | 1:200 | Outer and courtyard facades unrolled, in halves |
| AAI-2601-A-300 | Sections A-A and B-B | 1:150 | Diametric cuts; the tube reads as two true circles |
| AAI-2601-A-301 | Typical Bay — Radial Section | 1:50 | One 10° bay, fully annotated, with detail callouts |
| AAI-2601-A-500 | Envelope Details | 1:10 | 4 details, keyed, with performance table |
| AAI-2601-A-600 | Level 01 Framing Plan | 1:150 | Radial and ring steel, braced bays, member schedule |
| AAI-2601-A-700 | Area Schedule and Accommodation | — | Room schedules, metrics, fire, access, energy |
| AAI-2601-A-800 | Axonometric and Assembly | 1:300 / 1:620 | Shaded cutaway and exploded assembly |

## Section and elevation references

Section planes are set midway between radial gridlines so the flags never
collide with the grid bubbles:

- **A-A** — cut on 85° / 265°, through the northern service gateway and the
  double-height entrance hall.
- **B-B** — cut on 355° / 175°, through Town Square East and the auditorium.
- **C** — typical bay detail section at 25°, drawn on A-301.
- **Details 1, 2, 3, 4** — located on A-301, drawn on A-500.

## Model and source files

| File | Description |
|---|---|
| `output/model/torus-office.obj` | Wavefront mesh, 17 named groups, 25 182 faces, metres |
| `output/model/torus-office.mtl` | Material library |
| `output/model/torus-office.scad` | Parametric OpenSCAD source with customiser parameters |
| `output/model/viewer.html` | Self-contained WebGL viewer, no external assets |

## Revision history

| Rev | Date | Description |
|---|---|---|
| P03 | 2026-08-19 | Stage 3 spatial coordination issue. First issue of the full set. |
