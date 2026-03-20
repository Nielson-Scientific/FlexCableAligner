# Contributing

We welcome contributions to **CSVCreator**. Follow these steps to submit improvements:

## Development workflow
1. Fork the repository and create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Install development dependencies (if any) using the same environment as the installation guide.
3. Make your changes, ensuring existing functionality is not broken.
4. Run the test suite (if present) with:
   ```bash
   pytest
   ```
5. Commit with clear messages and push to your fork.
6. Open a Pull Request targeting the `main` branch.

## Code style
- Follow **PEP 8** guidelines; you can use `black` or `flake8` for formatting checks.
- Keep line length ≤ 100 characters.
- Add type hints where appropriate.

## Documentation updates
- When adding new features, update the relevant markdown files in `docs/CSVCreator/`.
- Ensure any new code references are linked using the clickable format, e.g., [`gui.py`](CSVCreator/gui.py:1).
