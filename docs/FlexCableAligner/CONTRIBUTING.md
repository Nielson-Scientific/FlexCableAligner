# Contributing

We welcome contributions! Please follow these guidelines:

## Code style
- Use **PEP 8** formatting. Run `flake8` or `black` before submitting a PR.
- Keep line length ≤ 100 characters.
- Add type hints where appropriate.

## Development workflow
1. Fork the repository and create a feature branch:
   ```bash
   git checkout -b feature/your-feature-name
   ```
2. Make your changes, ensuring existing tests still pass.
3. Run the test suite (if any) with `pytest`.
4. Commit with clear messages and push to your fork.
5. Open a Pull Request targeting the `main` branch.

## Testing
- Unit tests are located in the `tests/` directory (add new tests for new features).
- Run tests using:
  ```bash
  pytest
  ```

## Documentation updates
- When adding or modifying functionality, update the relevant markdown files under `docs/`.
- Keep diagrams and code references up‑to‑date.

Thank you for helping improve FlexCableAligner!