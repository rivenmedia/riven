import regex

from utils import data_dir_path

ignore_file_path = data_dir_path / "ignore.txt"

def get_ignore_hashes() -> set:
    """Read the ignore.txt file and return a set of infohashes to ignore."""
    infohashes = set()
    infohash_pattern = regex.compile(r"[a-fA-F0-9]{40}")

    if ignore_file_path.exists():
        with open(ignore_file_path, "r") as file:
            for line in file:
                match = infohash_pattern.search(line)
                if match:
                    infohashes.add(match.group(0))
    return infohashes
