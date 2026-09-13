# pages

Static pages served by GitHub Pages from `docs/`, one directory per project.

    docs/<project>/        the page and its generated data
    docs/slides/<deck>/    a slide deck
    docs/_layouts/         shared layouts
    docs/assets/           shared brand tokens
    scripts/<project>/     the generators for that project
    data/<project>/        raw snapshots, the durable source the generators read

Adding a project means adding those three directories; nothing else has to change.

## tool-tests

Longitudinal tool test results for tools-iuc, cross-checked against the AnVIL
deployment's dashboard.

    python3 scripts/tool-tests/ingest_run.py <ci_run_id>...    # CI artifact -> data/
    python3 scripts/tool-tests/generate_raster_data.py         # data/ -> docs/
    python3 scripts/tool-tests/compare_dashboards.py --runs 5 \
        --overlay docs/tool-tests/data/anvil-overlay.json \
        --panel   docs/tool-tests/data/anvil-panel.json

## slides

Decks use the `deck` layout: arrow keys move, Cmd-P prints one landscape page per
slide. Styling comes from `docs/assets/tokens.css`, vendored from
[galaxy-brand-tokens](https://github.com/galaxyproject/galaxy-brand-tokens); the file
header records the commit and how to refresh it.
