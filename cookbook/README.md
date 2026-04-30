# plotlet cookbook

Reference implementations of plot types **not** included in the core library.

These exist to be **read, copied, and adapted**, not imported. Each file is a
working example of how to use plotlet's deferred-render pattern to build a
custom plot type for your own project.

The point of the cookbook is the opposite of a feature catalog. **plotlet
deliberately does not grow a long list of built-in plot types.** Instead:

- The core ships ~5 standard plots (line, scatter, bar, hist, fill_between).
- The cookbook shows how to write your own.
- For your custom needs, copy a cookbook example, modify it for your data, and
  use it in your project. AI assistance makes this fast.

## How to use a recipe

1. Copy the file into your own project.
2. Either patch the `Figure` class directly, or wrap it in a thin helper.
3. Adjust styling, data shape, and details for your specific use case.
4. Don't PR your version back here — your version is for your project.

## Why no upstream contributions?

plotlet's value is the **scaffold**, not the catalog. Adding plot types to
the core would grow it, complicate maintenance, and erode the "small enough to
read end-to-end" property. The cookbook is intentionally a **reference set**,
not a catalog. We accept fixes to existing examples and improvements to the
core; we don't accept new plot types.

If you wrote something useful, **publish it in your project.** With AI search,
the next person who needs it will find your version anyway.
