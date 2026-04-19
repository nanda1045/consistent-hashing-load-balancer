# Contributing

Thanks for contributing.

## Quick Start

1. Clone the repository.
2. Start services:
   - `docker compose up -d --build`
3. Run tests:
   - `pytest -q`
4. Run benchmark:
   - `python scripts/benchmark.py`
5. Run API exercise:
   - `python scripts/exercise_api.py --with-failure-demo`

## Pull Requests

- Keep commits small and focused.
- Add or update tests when behavior changes.
- Update README when endpoints, scripts, or metrics change.
- Ensure CI passes before requesting review.
