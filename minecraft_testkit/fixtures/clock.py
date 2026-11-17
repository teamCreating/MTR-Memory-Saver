"""Explicit logical sampling clock; worker synchronization still uses real events."""
import datetime as dt


class SamplingClock:
    def __init__(self, initial):
        self.initial = initial
        self.elapsed = 0.0

    def monotonic(self):
        return self.elapsed

    def now(self):
        return self.initial + dt.timedelta(seconds=self.elapsed)

    def advance(self, seconds):
        if seconds < 0:
            raise ValueError("A test sampling clock cannot move backwards")
        self.elapsed += seconds

    def wait_for_sample(self, deadline, request_path):
        self.elapsed = max(self.elapsed, deadline)
