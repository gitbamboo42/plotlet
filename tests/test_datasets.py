"""Unit tests for the bundled example datasets."""
import math

import pytest

import plotlet as pt


def test_list_datasets():
    assert pt.list_datasets() == ["anscombe", "flights", "penguins", "tips"]


def test_unknown_dataset():
    with pytest.raises(ValueError, match="Unknown dataset"):
        pt.load("nope")


def test_penguins():
    df = pt.load("penguins")
    assert list(df) == ["species", "island", "bill_length_mm", "bill_depth_mm",
                        "flipper_length_mm", "body_mass_g", "sex", "year"]
    assert len(df["species"]) == 344
    assert df["species"][0] == "Adelie"
    assert df["bill_length_mm"][0] == 39.1
    assert any(isinstance(v, float) and math.isnan(v)
               for v in df["bill_length_mm"])


def test_flights():
    df = pt.load("flights")
    assert list(df) == ["year", "month", "passengers"]
    assert len(df["year"]) == 144                      # 12 years x 12 months
    assert df["year"][0] == 1949 and df["year"][-1] == 1960
    assert df["month"][0] == "January"
    assert all(isinstance(v, int) for v in df["passengers"])


def test_anscombe():
    df = pt.load("anscombe")
    assert list(df) == ["dataset", "x", "y"]
    assert len(df["x"]) == 44
    assert sorted(set(df["dataset"])) == ["I", "II", "III", "IV"]
    assert df["x"][0] == 10.0 and df["y"][0] == 8.04


def test_tips():
    df = pt.load("tips")
    assert list(df) == ["total_bill", "tip", "sex", "smoker",
                        "day", "time", "size"]
    assert len(df["tip"]) == 244
    assert df["total_bill"][0] == 16.99
    assert all(isinstance(v, int) for v in df["size"])
    assert set(df["time"]) == {"Lunch", "Dinner"}
