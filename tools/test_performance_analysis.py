import datetime as dt
import unittest
from analyze_performance_jfr import duration, stats, summarize


class PerformanceAnalysisTests(unittest.TestCase):
    def test_iso_duration_units(self):
        self.assertEqual(duration('PT1H2M3.5S'), 3723.5)
        self.assertEqual(duration('PT0.00005S'), .00005)
        with self.assertRaises(ValueError):
            duration('50ms')

    def test_quantiles_and_empty_window(self):
        self.assertEqual(stats([]), {'count': 0})
        self.assertEqual(stats([1, 2, 3, 100])['p50'], 2.5)
        self.assertAlmostEqual(stats([1, 2, 3, 100])['p95'], 85.45)

    def test_frames_exclude_pause_menu_and_cross_window_interval(self):
        base = dt.datetime(2026, 11, 5, tzinfo=dt.timezone.utc)
        events = []
        for offset, interval, paused, screen in [(0.01, 50, False, 'game'), (.1, 20, False, 'game'),
                                                 (.2, 90, True, 'game'), (.3, 80, False, 'menu')]:
            events.append({'type': 'mtrtest.ClientFrame', 'values': {
                'startTime': (base + dt.timedelta(seconds=offset)).isoformat(),
                'intervalMs': interval, 'inWorld': True, 'paused': paused, 'screen': screen}})
        result = summarize(events, base, base + dt.timedelta(seconds=1))
        self.assertEqual(result['game_frame_interval_ms']['count'], 1)
        self.assertEqual(result['effective_fps_from_intervals'], 50)

    def test_gc_top_level_pauses_do_not_double_count_children(self):
        base = dt.datetime(2026, 11, 5, tzinfo=dt.timezone.utc)
        events = [{'type': kind, 'values': {'startTime': base.isoformat(), 'duration': length}}
                  for kind, length in [('jdk.GCPhasePause', 'PT0.1S'), ('jdk.GCPhasePauseLevel1', 'PT0.08S')]]
        result = summarize(events, base, base + dt.timedelta(seconds=1))
        self.assertEqual(result['gc_pause_ms']['sum'], 100)


if __name__ == '__main__':
    unittest.main()
