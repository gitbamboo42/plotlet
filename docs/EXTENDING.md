# Extending plotlet

Adding a custom plot type is a 3-step recipe. The recipe will be
documented here in detail after the scaffold refactor (which promotes
the helper functions to public API).

For now, see [`cookbook/karyotype.py`](../cookbook/karyotype.py) for a worked
example, and [`PHILOSOPHY.md`](PHILOSOPHY.md) for why we don't accept new plot
types into the core.

## The three steps (preview)

1. **Record method calls** — append to `Figure._calls`. Either monkey-patch
   `_RECORDABLE` and the replay loop, or use the upcoming `add_artist` API.
2. **Domain logic** — extend `_render`'s domain computation if your artist
   affects axis limits.
3. **Draw branch** — emit SVG strings using the public helpers
   (`text_path`, `measure_text`, `resolve_color`, scale classes).

Detailed examples coming with the scaffold refactor.
