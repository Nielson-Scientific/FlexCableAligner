from utils.FileUtils import FileUtils as FU

 
def visit_tags(tag_csv):
    csv_points = FU.csv_to_array(tag_csv)[1:]
    coordinate_points = [(int(tag_id), float(x)/1000, float(y)/1000) for tag_id, _, _, x, y in csv_points]
    print(coordinate_points)


if __name__ == "__main__":
    visit_tags("test_data/tag16h5_10x3_500mm_15m_offset_framed_centers.csv")
