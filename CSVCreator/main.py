import tkinter as tk
from model import Model
from gui import GUI
from dxf_loader import load_dxf
import sys
import os

# Add current directory to path just in case, though usually handled by python
sys.path.append(os.path.dirname(os.path.abspath(__file__)))


def main():
    root = tk.Tk()
    # Optional: set icon, geometry, etc.
    root.geometry("1000x800")
    
    model = Model()
    
    # Define callback to be used by GUI
    def load_dxf_callback(filepath):
        # Could add extra logic here if needed
        return load_dxf(filepath)

    app = GUI(root, model, load_dxf_callback)
    
    root.mainloop()

if __name__ == "__main__":
    main()
