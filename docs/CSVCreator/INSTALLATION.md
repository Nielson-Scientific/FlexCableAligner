# Installation

## Prerequisites
- Python **3.9+**
- `pip` (use a virtual environment)
- Git (optional, for cloning the repository)

## Setup steps
1. Clone the repository (if not already done):
   ```bash
   git clone https://github.com/yourusername/FlexCableAligner.git
   cd FlexCableAligner/CSVCreator
   ```
2. Create and activate a virtual environment:
   ```bash
   python -m venv .venv
   source .venv/bin/activate   # Linux/macOS
   .\\venv\\Scripts\\activate  # Windows
   ```
3. Install required packages:
   ```bash
   pip install ezdxf scipy matplotlib
   ```
4. Verify the installation by running the GUI:
   ```bash
   python main.py
   ```
   The application window should appear without errors.
