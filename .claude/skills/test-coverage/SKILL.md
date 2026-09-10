---
name: test-coverage
description: Use when adding or modifying a function or component in the codebase (new util, new endpoint, changed public function). Do NOT use for read-only work — reading code, debugging, or refactors that introduce no new function.
---

# Test coverage

When you add or change a **public function**, your FIRST action — before moving on —
is to create or update its matching test file. The test tree mirrors the source
tree: a file's path under `generator_test/tests/` matches its path under
`generator_test/`, with the basename prefixed `test_`.

- `fonctions_python/scoring.py` → `tests/test_scoring.py`
- `fonctions_python/type_questions/foo.py` → `tests/type_questions/test_foo.py`

## Done when (verifiable)

- Every new or changed public function in `generator_test/fonctions_python/` and
  `lacune_evaluation/` has a corresponding test in a file at the **same relative
  path** under `generator_test/tests/`.
- `cd generator_test && python -m pytest` passes.
