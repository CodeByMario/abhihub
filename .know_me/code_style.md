# Code Style Guidelines

## General Conventions
- Use **PEP 8** as the base style guide for Python code.
- Indentation: **4 spaces** (no tabs).
- Maximum line length: **100 characters**.
- Use **snake_case** for variables and functions, **PascalCase** for classes.
- Constants should be in **UPPER_SNAKE_CASE**.

## Imports
- Order imports: standard library, third‑party packages, local modules.
- Separate each group with a blank line.
- Use absolute imports for project modules.

## Documentation
- All public functions/classes must have a **docstring** describing purpose, args, returns, and raised exceptions.
- Use **Google style** docstrings.
- Module‑level docstrings at the top of each file.

## Linting & Formatting
- Run `flake8` for linting and `black` for auto‑formatting.
- Enforce **type hints** where practical; run `mypy` in CI.

## Testing
- Keep tests in a `tests/` directory mirroring the source layout.
- Use **pytest** with descriptive test names.
- Aim for **>80% coverage**; run `pytest --cov`.

## Scripts
- Provide a short usage comment at the top of each script.
- Scripts should be **executable** via `python -m <module>` when possible.

## Version Control
- Follow conventional commits for clear history.
- Do not commit generated files (e.g., `__pycache__`, compiled assets).

---
These guidelines apply across the entire repository to ensure consistency and maintainability.
