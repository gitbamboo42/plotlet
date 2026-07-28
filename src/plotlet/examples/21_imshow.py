"""Image grid

imshow renders dense matrices as an embedded raster; the colorbar
comes from the same legend system as everything else.
"""
import math

import plotlet as pt

data = [[math.sin(r * 0.07) + math.cos(c * 0.05) for c in range(160)]
        for r in range(120)]

c = pt.chart(title="imshow", xlabel="col", ylabel="row",
             data_width=320, data_height=240)
c.add_imshow(data, cmap="magma")

