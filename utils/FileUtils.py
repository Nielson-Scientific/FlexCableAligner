
class FileUtils:
    @staticmethod
    def csv_to_array(csv_file_path):
        with open(csv_file_path, "r", encoding="utf-8", newline="") as csv_file:
            return [line.rstrip("\r\n").split(",") for line in csv_file]
