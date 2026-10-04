"""`orientation=` across the categorical artists: which axis holds the
categories, and what the unset/guess default resolves to.

One helper (`utils.resolve_orientation`) backs all of them, so the
behaviour is tested once per artist rather than once per artist per case.
"""
import plotlet as pt
from plotlet import aes
import pytest


# every artist that takes a long-form (category, value) pair
CATEGORICAL = ("violin", "boxplot", "strip", "swarm", "pointplot", "bar")

# artists whose value axis must be real numbers (quantiles, KDE, bar
# heights); strip and swarm can place a value on a category scale too
NUMERIC_ONLY = ("violin", "boxplot", "pointplot", "bar")


def _df():
    return {"cat": ["a", "a", "a", "b", "b", "b"],
            "value": [1.0, 2.0, 3.0, 2.0, 3.0, 4.0]}


def _scales(c):
    """The first panel's resolved x/y scale dicts."""
    panel = pt.to_ir(c).resolve().to_dict()["root"]["children"][0]
    return panel["scales"]


def _axes(c):
    """(x_kind, y_kind) as the resolved IR sees them."""
    s = _scales(c)
    return s["x"]["kind"], s["y"]["kind"]


def _artist(c):
    """The first panel's first recorded artist."""
    panel = pt.to_ir(c).resolve().to_dict()["root"]["children"][0]
    return panel["state"]["artists"][0]


@pytest.mark.parametrize("artist", CATEGORICAL)
def test_discrete_x_guesses_upright(artist):
    c = pt.chart(_df(), aes(x="cat", y="value"))
    getattr(c, "add_" + artist)()
    assert _axes(c) == ("category", "linear")


@pytest.mark.parametrize("artist", CATEGORICAL)
def test_discrete_y_guesses_horizontal(artist):
    # the call that used to crash (violin/boxplot/bar) or silently render
    # flipped (strip/swarm) — the mapping alone now says horizontal
    c = pt.chart(_df(), aes(x="value", y="cat"))
    getattr(c, "add_" + artist)()
    assert _axes(c) == ("linear", "category")


@pytest.mark.parametrize("artist", CATEGORICAL)
def test_explicit_orientation_matches_the_guess(artist):
    guessed = pt.chart(_df(), aes(x="value", y="cat"))
    getattr(guessed, "add_" + artist)()

    stated = pt.chart(_df(), aes(x="value", y="cat"))
    getattr(stated, "add_" + artist)(orientation="y")

    assert guessed.to_svg() == stated.to_svg()


@pytest.mark.parametrize("artist", CATEGORICAL)
def test_both_numeric_keeps_categories_on_x(artist):
    # A numeric category column (doses, years) still reads as the category
    # axis — guessing never transposes a two-numeric mapping. The *scale*
    # stays linear either way (a numeric column always gets a linear axis),
    # so the guess shows up in the artist, not in the scale kind.
    df = {"dose": [5, 5, 5, 10, 10, 10], "resp": [1.0, 2.0, 3.0, 2.0, 3.0, 4.0]}
    c = pt.chart(df, aes(x="dose", y="resp"))
    getattr(c, "add_" + artist)()
    a = _artist(c)
    assert a["opts"]["orientation"] == "x"
    assert a["cats"] == [5, 10]


@pytest.mark.parametrize("artist", NUMERIC_ONLY)
def test_non_numeric_value_axis_raises_at_the_call_site(artist):
    df = {"cat": ["a", "a", "b", "b"], "other": ["p", "q", "p", "q"]}
    c = pt.chart(df, aes(x="cat", y="other"))
    getattr(c, "add_" + artist)()
    with pytest.raises(TypeError, match="must be numeric"):
        c.to_svg()


@pytest.mark.parametrize("artist", CATEGORICAL)
def test_explicit_orientation_against_the_dtypes_raises(artist):
    # orientation="y" says "categories on y", but y is the numeric column
    # and x the discrete one — a swapped mapping. strip/swarm would
    # otherwise draw it silently (each float a category, strings as
    # values), so every artist rejects it, with the swap hint.
    c = pt.chart(_df(), aes(x="cat", y="value"))
    getattr(c, "add_" + artist)(orientation="y")
    with pytest.raises(TypeError, match="must be numeric"):
        c.to_svg()


def test_numeric_error_does_not_blame_an_unset_orientation():
    # guessed layout: the message names the columns and the fix, and
    # never quotes an orientation= the user did not pass
    df = {"cat": ["a", "a", "b", "b"], "other": ["p", "q", "p", "q"]}
    c = pt.chart(df, aes(x="cat", y="other"))
    c.add_boxplot()
    with pytest.raises(TypeError, match="y= must be numeric") as info:
        c.to_svg()
    assert "orientation='x'" not in str(info.value)


@pytest.mark.parametrize("artist", ("strip", "swarm"))
def test_two_discrete_columns_draw_a_dot_plot(artist):
    # strip/swarm place points on a category scale happily — a
    # categorical-vs-categorical dot plot is a real plot, not an error
    df = {"a": ["p", "p", "q", "q"], "b": ["x", "y", "x", "y"]}
    c = pt.chart(df, aes(x="a", y="b"))
    getattr(c, "add_" + artist)()
    assert _axes(c) == ("category", "category")


@pytest.mark.parametrize("artist", CATEGORICAL + ("hist",))
def test_old_vh_vocabulary_is_rejected(artist):
    df = _df()
    mapping = aes(x="value") if artist == "hist" else aes(x="cat", y="value")
    c = pt.chart(df, mapping)
    getattr(c, "add_" + artist)(orientation="h")
    with pytest.raises(ValueError, match="must be 'x' or 'y'"):
        c.to_svg()


def test_hist_bins_along_the_named_axis():
    # Both axes are linear here, so the swap shows up as the two scale
    # dicts trading places: bin edges on the named axis, counts opposite.
    df = {"v": [1.0, 2.0, 2.0, 3.0, 3.0, 3.0, 4.0]}

    upright = pt.chart(df, aes(x="v"))
    upright.add_hist(orientation="x", bins=4)
    sideways = pt.chart(df, aes(x="v"))
    sideways.add_hist(orientation="y", bins=4)

    assert _scales(upright)["x"] == _scales(sideways)["y"]
    assert _scales(upright)["y"] == _scales(sideways)["x"]


def test_bar_count_stays_upright_without_a_second_column():
    # stat="count" maps x only, so there is nothing to guess from
    df = {"cat": ["a", "a", "b", "b", "b", "c"]}
    c = pt.chart(df, aes(x="cat"))
    c.add_bar(stat="count")
    assert _axes(c) == ("category", "linear")

    c = pt.chart(df, aes(x="cat"))
    c.add_bar(stat="count", orientation="y")
    assert _axes(c) == ("linear", "category")


def test_bar_error_bars_follow_the_guessed_orientation():
    df = {"cat": ["a", "b"], "v": [1.0, 2.0], "sd": [0.1, 0.2]}

    # guessed horizontal → the value axis is x, so yerr is the wrong kwarg
    c = pt.chart(df, aes(x="v", y="cat", yerr="sd"))
    c.add_bar()
    with pytest.raises(TypeError, match="xerr"):
        c.to_svg()

    # guessed upright → the mirror case
    c = pt.chart(df, aes(x="cat", y="v", xerr="sd"))
    c.add_bar()
    with pytest.raises(TypeError, match="yerr"):
        c.to_svg()
