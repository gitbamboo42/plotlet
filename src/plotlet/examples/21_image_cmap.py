"""Value matrix through a colormap

image_cmap renders a scalar matrix as pixels. extent places the matrix
on real axis coordinates, center=0 pins the diverging colormap's
midpoint to zero, and the colorbar comes from the same legend system
as everything else.
"""
import math

import plotlet as pt

data = [[math.sin(2 * (-3 + 6 * col / 159)) * math.cos(3 * (-2 + 4 * row / 119))
         + 0.3 * (-3 + 6 * col / 159)
         for col in range(160)] for row in range(120)]

c = pt.chart(title="image_cmap", xlabel="x", ylabel="y",
             data_width=360, data_height=240)
c.add_image_cmap(data, cmap="RdBu_r", center=0, extent=(-3, 3, -2, 2),
                 legend={"label": "amplitude"})
