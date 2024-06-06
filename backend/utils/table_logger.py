from rich.table import Table
from .logger import console


class FileLogger:
    """A logger for rich tables."""

    def __init__(self, title, show_header=False, header_style=None):
        self.title = title
        self.show_header = show_header
        self.header_style = header_style
        self.create_new_table()

    def create_new_table(self):
        """Create a new table with the initial configuration."""
        self.table = Table(title=self.title, header_style=self.header_style or "bold white", row_styles=["bold green", "bold white", "bold green"])

    def add_column(self, column_name, style="bold green"):
        """Add a column to the table."""
        self.table.add_column(column_name, style=style)
    
    def add_row(self, *args):
        """Add a row to the table."""
        self.table.add_row(*args)
    
    def log_table(self):
        """Log the table to the console."""
        console.print(self.table)
        self.clear_table()

    def clear_table(self):
        """Clear the table by reinitializing it."""
        self.create_new_table()

    def progress_bar(self, *args):
        """Add a progress bar to the table."""
        self.table.add_row(*args)

table = FileLogger("Downloaded Files", show_header=True)
