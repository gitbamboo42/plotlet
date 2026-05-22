"""Hierarchical-clustering tree. Standalone artist — doesn't auto-couple to
imshow; the caller reorders heatmap data with the leaf permutation.
Compute / draw logic lives in plotlet.dendrogram.
"""
from ..registry import ArtistSpec, add_artist
from .._spec import _D
from ..dendrogram import (
    _dendrogram_record,
    _dendrogram_xdomain,
    _dendrogram_ydomain,
    _dendrogram_draw,
    _dendrogram_data_attrs,
    _dendrogram_axis_order,
    _dendrogram_frame_defaults,
)


add_artist(ArtistSpec(
    name="dendrogram",
    record=_dendrogram_record,
    xdomain=_dendrogram_xdomain,
    ydomain=_dendrogram_ydomain,
    draw=_dendrogram_draw,
    uses_color_cycle=False,
    default_color=_D["dendrogram_color"],
    data_attrs=_dendrogram_data_attrs,
    axis_order=_dendrogram_axis_order,
    frame_defaults=_dendrogram_frame_defaults,
    tight_domain=True,
))
