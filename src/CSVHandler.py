import csv
import logging

class CSVHandler:
    def __init__(self):
        self.rows = []
        self.headers = []

    def load_file(self, filepath):
        """
        Loads a CSV file and validates its structure.
        Expected columns: x1, y1, x2, y2, manual
        """
        self.rows = []
        try:
            with open(filepath, mode='r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                self.headers = reader.fieldnames
                
                required_cols = {'x1', 'y1', 'x2', 'y2', 'manual'}
                if not required_cols.issubset(set(self.headers)):
                    raise ValueError(f"CSV missing required columns. Found: {self.headers}, Expected: {required_cols}")

                for i, row in enumerate(reader):
                    # Validate numeric values
                    try:
                        clean_row = {
                            'index': i,
                            'x1': float(row['x1']),
                            'y1': float(row['y1']),
                            'x2': float(row['x2']),
                            'y2': float(row['y2']),
                            'manual': row['manual'].strip().lower() == 'true'
                        }
                        self.rows.append(clean_row)
                    except ValueError as e:
                        logging.error(f"Row {i} has invalid data: {row}. Error: {e}")
                        continue
                        
            return self.rows
        except Exception as e:
            logging.error(f"Failed to load CSV: {e}")
            raise e
