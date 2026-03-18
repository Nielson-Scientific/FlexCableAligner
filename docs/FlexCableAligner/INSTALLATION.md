# Installation

## Prerequisites
- Python **3.9+**
- `pip` (recommended to use a virtual environment)
- Git (optional, for cloning the repository)

## Setup steps
1. Clone the repository (if you haven't already):
   ```bash
   git clone https://github.com/yourusername/FlexCableAligner.git
   cd FlexCableAligner
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Linux/macOS
   .\\venv\\Scripts\\activate  # Windows
   ```
3. Install the required Python packages:
   ```bash
   pip install -r requirements.txt
   ```
4. Verify the installation by running a quick sanity check (no hardware needed):
   ```bash
   python -c "import src.App; print('FlexCableAligner modules loaded')"
   ```

## Optional dependencies
- `matplotlib` is required only for optional visualisation utilities.
- If you plan to develop or run the older version scripts, install additional packages listed in `older_versions/requirements.txt` (if present).

---
For more detailed environment configuration (e.g., Klipper firmware settings), see the project's main [`README.md`](../README.md).