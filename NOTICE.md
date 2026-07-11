# NOTICE

plotlet bundles or derives from the following third-party works.

## Matplotlib colormap data

`src/plotlet/draw/_cm_data.py` contains 256-point lookup tables sampled from
`matplotlib.colormaps`. Matplotlib is:

> Copyright (c) 2012- Matplotlib Development Team; All Rights Reserved.

Distributed under the Matplotlib License (PSF-style):
https://matplotlib.org/stable/users/project/license.html

## Example datasets

`src/plotlet/_datasets/` bundles small public example datasets:

- `penguins.csv` — Palmer Penguins (Gorman, Williams & Fraser 2014),
  distributed under CC0. https://allisonhorst.github.io/palmerpenguins/
- `flights.csv` — monthly airline passenger totals 1949–1960, the classic
  Box & Jenkins (1976) "AirPassengers" series (public data).
- `anscombe.csv` — Anscombe's quartet, the data table published in
  Anscombe, F. J. (1973), "Graphs in Statistical Analysis".
- `tips.csv` — restaurant tipping records from Bryant & Smith (1995),
  *Practical Data Analysis: Case Studies in Business Statistics*.

The `flights`, `anscombe`, and `tips` CSVs were obtained from the
seaborn example-data repository (https://github.com/mwaskom/seaborn-data).

## DejaVu Sans

`src/plotlet/draw/fonts/DejaVuSans*.ttf` (regular, bold, oblique,
bold-oblique) are the DejaVu Sans fonts, which are based on Bitstream
Vera Fonts (Copyright (c) 2003 by Bitstream, Inc.) with modifications
by the DejaVu changes committee. License (bundled as
`draw/fonts/LICENSE-DejaVuSans.txt`):
https://dejavu-fonts.github.io/License.html

## Arimo

`src/plotlet/draw/fonts/Arimo-*.ttf` (regular, bold, italic,
bold-italic) are the Arimo fonts, Copyright The Arimo Project Authors
(https://github.com/googlefonts/Arimo), distributed under the SIL Open
Font License 1.1, bundled as `draw/fonts/LICENSE-Arimo.txt`.
