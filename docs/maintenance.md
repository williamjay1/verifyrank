# Proposed maintenance policy

This policy accompanies VerifyRank 0.2.0, prepared for public release by its sole software author, junjiezhang. It describes intended maintenance practices, not an established service, funded support commitment or record of external adoption. No independent adopters or usability participants have been established. A public issue tracker and release history are not asserted before publication of the repository.

## Versioning and compatibility

The CSV/JSON contract documented for software 0.2.x is schema series 0.2. The current JSON schemas and synthetic fixtures are the reference contract. Input column names, state meanings, reference identity rules, conditional-score denominators and completion semantics form part of compatibility; matching field names alone is insufficient.

Patch releases in 0.2.x should preserve valid documented inputs and output meanings. Numerical bug fixes must include a reproducing fixture and explicitly identify affected earlier results. A change to evidence states, identity, budgets, estimands, existing field meanings or acceptance of previously valid inputs requires a minor-version change during the pre-1.0 series, migration notes and updated fixtures. Future additive fields must not be silently introduced into the current strict input schema. At version 1.0, incompatible public API or schema changes would require a major-version change.

Old input examples and expected completion values should remain in regression tests. An adapter migration should preserve its original data and produce a new versioned input, accompanied by an explicit old/new result comparison. The evaluator must not repair input inconsistencies by dropping rows, inventing negatives or changing weights.

## Change review and release checks

Each behavioral fix or feature should add or revise a test that would fail under the previous implementation. Relevant checks include malformed input rejection, shared-reference identity, exact completion extrema, denominator handling, truth-free planning and executable CLI behavior. New planning rules must state their objective, cost assumptions and whether optimality is established; synthetic success alone is insufficient to claim operational gains.

A proposed release should build the wheel, install it in a clean environment, run source and installed-package tests, run the synthetic CSV and JSON examples, and inspect the distribution file list. Domain parity checks require separately authorized inputs and should be run when evaluation semantics change. Their restricted records and local reports must not be included in the software archive. The changelog records changes and remaining limitations. Release manifests identify the exact source and wheel contents.

The GitHub Actions configuration in `.github/workflows/tests.yml` defines Python 3.12 source tests, wheel installation and synthetic CLI checks. It has been prepared, but no remote workflow execution is claimed in this release. The Dockerfile is likewise a provided configuration; the current machine has no Docker command, so no successful container build or run is claimed. Local installed-package validation is a separate executed check.

## Reporting bugs

Before a public tracker exists, send the project owner a minimal reproducible example. Once a repository is published, ordinary non-sensitive defects can be submitted through its Issues interface. Include the VerifyRank version, Python/OS versions, the smallest synthetic input demonstrating the problem, the command or API call, expected behavior, actual output and an error traceback if present.

Do not attach access tokens, passwords, signed URLs, private records, provider-restricted observations or identifying participant data. Replace them with synthetic cases that preserve the failure. Reports should distinguish an arithmetic or contract bug from an invalid domain adapter or uncertain measurement label. Neither an issue nor a test passing constitutes independent scientific validation.

No response-time guarantee or named maintenance team is established. Any future appointment of maintainers, deprecation schedule or user-validation study should be recorded explicitly rather than inferred from this proposed policy.
