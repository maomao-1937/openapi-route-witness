# Testing

Validated on 2026-10-31 with Python 3.11 on Windows. No third-party dependencies.

```console
python -m unittest discover -s tests -v
python -m compileall -q openapi_route_witness.py tests
```

Observed results: **44 tests passed** in 0.754 seconds; compilation passed.
All **13 fixture examples** listed in `checks.json` were executed with Python,
the project as cwd, managed stdout/stderr pipes, and a 20-second timeout per
subprocess. All expected exit codes matched, stdout parsed as JSON, and stderr
was empty. These are local results, not remote CI or deployment evidence.

## RED / GREEN record

The initial 40 contracts were written before implementation. The recorded RED
run had 40 assertion failures because the implementation and CLI were absent.
These existence-gated failures do not establish 40 independent algorithm
regressions. An earlier harness run had missing-CLI JSON parsing errors; the
harness was corrected before the saved RED run.

The first implementation run passed 38 tests and failed two contracts: the clean
fixture was missing, and missing-version input had the wrong error classification.
After adding the fixture and correcting classification, all 40 passed. Four
additional verification tests then passed without feature changes.

A separate controlled regression probe temporarily disabled crossing-overlap
classification in the real script. The dedicated crossing test failed with
`AssertionError: 1 != 0`. The original script was restored in a `finally` block,
then the complete 44-test suite passed. This probe is identified as regression
verification, not the original test-first run. Raw builder logs are retained
outside the distributable project in the batch's builder evidence directory.

## Coverage and limits

Tests cover concrete witnesses against an independent matcher, an exhaustive
small-domain oracle over 91 route pairs, specificity and crossing behavior,
equivalent templates across methods, known HTTP methods, root/trailing slashes,
unsupported syntax and references, malformed core containers, version scope,
JSON/UTF-8 rejection, bounds, metadata privacy, and CLI error/help/output handling.

The CLI reads one UTF-8 JSON file, or stdin with a single `-` argument. It emits
one JSON report and returns 0, 1, or 2 as documented in README.md. Tests invoke
the script by basename from the project directory to avoid path-related Windows
startup overhead observed in the surrounding builder workflow.

Fixtures are synthetic. No full OpenAPI validation, YAML handling, reference
resolution, parameter constraint analysis, runtime HTTP routing, benchmark,
remote CI, publishing, or deployment was performed by this builder. A structural
witness may violate parameter constraints. Witnesses intentionally expose path
literal segments; tests check that metadata sentinels and parameter names stay
out of output. See README.md for the complete supported profile and limits.
