# Chess Engine Testing Scenarios

This document describes the comprehensive testing approach for the Viper Chess Engine project. The goal is to ensure every actively used Python module has a corresponding, non-destructive unit test file, and that all tests can be run individually or as a suite.

---

## Testing Architecture Overview

- **Per-Module Testing:**  
  For every main `.py` file (excluding test scripts themselves), there is a corresponding `[module]_testing.py` file in the `testing` directory.  
  Example:  
  - `metrics_store.py` → `metrics_store_testing.py`
  - `chess_metrics.py` → `chess_metrics_testing.py`
  - `chess_game.py` → `chess_game_testing.py`
  - etc.

- **Test Suite Orchestration:**  
  - The `testing.yaml` file lists which test files to run in a test session.
  - The `launch_testing_suite.py` script reads `testing.yaml` and runs the selected tests in sequence.

- **Non-Destructive Testing:**  
  - All tests must avoid deleting or irreversibly modifying production data.
  - Tests should use temporary files, in-memory databases, or clearly marked test data.
  - If a test must write to disk, it should clean up after itself or use a dedicated test directory.

---

## How to Add or Run Tests

1. **To test a single module:**  
   Run its corresponding `[module]_testing.py` file directly.

2. **To run a suite of tests:**  
   - Edit `testing.yaml` to list the desired test files.
   - Run `python launch_testing_suite.py`.

3. **When adding a new `.py` file:**  
   - Create a blank `[module]_testing.py` in the `testing` directory.
   - Add basic import and smoke tests.
   - Expand with targeted unit tests as the module evolves.

---

## Checklist: Test File Coverage

- [x] `metrics_store.py` → `metrics_store_testing.py`
- [x] `chess_metrics.py` → `chess_metrics_testing.py`
- [x] `chess_game.py` → `chess_game_testing.py`
- [x] `viper_scoring_calculation.py` → `viper_scoring_calculation_testing.py`
- [x] `any_other_main_module.py` → `any_other_main_module_testing.py`
- [ ] _If you add a new main module, create its test file here._

---

## Example: metrics_store_testing.py

- Tests database initialization, data insertion, and query methods.
- Uses a temporary or test database file.
- Verifies that player_color normalization works as expected.
- Cleans up test data after running.

---

## Example: launch_testing_suite.py

- Reads `testing.yaml` for a list of test files.
- Imports and runs each test file in order.
- Reports pass/fail for each module.

---

## Example: testing.yaml

```yaml
# List of test files to run in the suite
test_files:
  - metrics_store_testing.py
  - chess_metrics_testing.py
  - chess_game_testing.py
  - viper_scoring_calculation_testing.py
```

---

## Best Practices

- **Tests should be idempotent:** Running them multiple times should not affect results or leave side effects.
- **Tests should be isolated:** Each test should set up and tear down its own data.
- **Tests should be fast:** Avoid long-running or resource-intensive operations unless specifically testing performance.
- **Tests should be clear:** Use descriptive names and comments.

---

## Next Steps

- Review the `testing` directory and ensure every main `.py` file has a corresponding `[module]_testing.py`.
- Expand each test file with meaningful unit and integration tests.
- Use `launch_testing_suite.py` and `testing.yaml` to automate multi-module testing before production releases.

---

If you find a `.py` file without a corresponding test file, create a blank `[module]_testing.py` and notify the team to add coverage.