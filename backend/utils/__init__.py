from pathlib import Path
import os

root_dir = Path(os.path.abspath(__file__)).parent.parent.parent

data_dir_path =  os.path.join(root_dir, "data")
version_file_path = os.path.join(root_dir, "iceberg.version")