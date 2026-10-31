# Research and scope

Sources checked on 2026-10-31. Implementation and tests are original; no upstream
implementation or documentation was copied into this repository.

## Source facts

- [OpenAPI 3.1.1, Paths Object and matching](https://spec.openapis.org/oas/v3.1.1.html#paths-object)
  distinguishes concrete precedence, invalid equivalent templates with different
  names, and potentially ambiguous crossing patterns. Ambiguous resolution is
  left to tooling. It does not classify every overlap as invalid.
- [OpenAPI 3.2.1](https://spec.openapis.org/oas/v3.2.1.html) is published, dated
  10 September 2026. This project deliberately supports the 3.0/3.1 feature sets
  only; it does not advertise support for the latest specification.
- [Vacuum's no-ambiguous-paths rule](https://quobix.com/vacuum/rules/operations/no-ambiguous-paths/)
  already targets ambiguous paths and documents equivalent and crossing examples.
  Ambiguity detection is an existing feature area, not a new invention here.

## Project choices and inference

The narrow opportunity is a dependency-free Python script whose bounded route
model produces a concrete shared path, neutral indexed diagnostics, and explicit
exit codes. Potential usefulness is an inference; no user demand or adoption has
been measured. No speed, accuracy, or superiority benchmark was performed.

Equivalent templates are checked globally. The same-method crossing check and
partially templated dominance policy are explicit analysis choices. The tool
does not establish how any runtime resolves a request. Parameter constraints may
exclude a structural witness; this checker intentionally ignores those constraints.

## Fair alternatives

Use [Vacuum](https://quobix.com/vacuum/) for a broader OpenAPI lint workflow,
including its existing ambiguity rule. [Redocly CLI](https://redocly.com/docs/cli/)
is another established broader validation/linting alternative. Their wider
workflows may fit an API project better. This research does not claim either tool
lacks witness output, and it does not attempt an exhaustive feature comparison.

Choose this script when the exact documented segment profile and a standalone
stdlib Python artifact are useful. Pair it with a broader validator; unsupported
syntax is a rejected input, never evidence that the API has no conflicts.
