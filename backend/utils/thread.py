"""Threading helper"""
import threading
import time
from pathos.multiprocessing import Pool


class ThreadRunner(threading.Thread):
    """Thread runner"""

    def __init__(self, target_method, run_interval=30, args=None):
        threading.Thread.__init__(self, name=target_method.__name__)
        self.target_method = target_method
        self.args = args
        self.run_interval = run_interval  # in seconds
        self.is_running = False

    def run(self):
        self.is_running = True
        while self.is_running:
            if self.args is not None:
                self.target_method(self.args)
            else:
                self.target_method()
            time.sleep(self.run_interval)

    def stop(self):
        """Stops the thread"""
        self.is_running = False
        if self.is_alive():
            self.join()


def split_and_execute_in_parallel(lst, method):
    # Define the minimum number of items in each sublist
    MIN_ITEMS = 20

    # Split list into sublists with at least MIN_ITEMS
    sublists = [lst[i : i + MIN_ITEMS] for i in range(0, len(lst), MIN_ITEMS)]

    # Use a Pool of processes
    pool = Pool()
    results = pool.map(method, sublists)

    return results
