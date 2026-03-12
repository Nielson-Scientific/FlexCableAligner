import csv
import logging

class CSVHandler:
    def __init__(self):
        self.rows = []
        self.landmarks = {}
        self.headers = []

    def load_file(self, filepath):
        """
        Loads a CSV file and validates its structure.
        Expected columns: Index, x1, y1, x2, y2, manual
        Returns a tuple: (list of point rows, dict of landmarks)
        """
        self.rows = []
        self.landmarks = {}
        
        try:
            with open(filepath, mode='r', newline='', encoding='utf-8') as f:
                reader = csv.DictReader(f)
                self.headers = reader.fieldnames
                
                # Check for required columns
                required_cols = {'Index', 'x1', 'y1', 'x2', 'y2', 'manual'}
                # Note: We check if required cols are present. keys() gives us what's in the file.
                # If 'Index' is missing, maybe we should support legacy format? 
                # The prompt implies a strict new format.
                
                if not required_cols.issubset(set(self.headers)):
                     raise ValueError(f"CSV missing required columns. Found: {self.headers}, Expected: {required_cols}")

                for i, row in enumerate(reader):
                    try:
                        idx_val = row['Index'].strip()
                        
                        # Parse coordinates
                        clean_row = {
                            'index_id': idx_val, # Keep original string ID
                            'x1': float(row['x1']),
                            'y1': float(row['y1']),
                            'x2': float(row['x2']),
                            'y2': float(row['y2']),
                            'manual': row['manual'].strip().lower() == 'true'
                        }
                        
                        if idx_val == "Landmark1":
                            self.landmarks['Landmark1'] = clean_row
                        elif idx_val == "Landmark2":
                            self.landmarks['Landmark2'] = clean_row
                        else:
                            # It's a point
                            # Check if index is numeric just for sanity, but store it as is or int
                            # The prompt says: "Index should start at 0 and increment by 1"
                            # We can just store it.
                            self.rows.append(clean_row)
                            
                    except ValueError as e:
                        logging.error(f"Row {i} has invalid data: {row}. Error: {e}")
                        continue
            
            # Validation: Ensure we found both landmarks
            if 'Landmark1' not in self.landmarks or 'Landmark2' not in self.landmarks:
                raise ValueError("CSV must contain both 'Landmark1' and 'Landmark2' rows.")
                
            return self.rows, self.landmarks
            
        except Exception as e:
            logging.error(f"Failed to load CSV: {e}")
            raise e
