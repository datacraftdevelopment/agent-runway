import json
import unittest

from runway import capacity, db, status, take
from runway.loop import touches_overlap

from tests.test_loop import FakeRunner, LoopTest

# What the capacity script prints on a Mac: sysctl lines, vm_stat, then the df line.
SAMPLE = """12
34359738368
58
{ 3.20 2.90 2.50 }
--vm
Mach Virtual Memory Statistics: (page size of 16384 bytes)
Pages free:                               40000.
Pages active:                            700000.
Pages inactive:                          150000.
Pages speculative:                        10000.
--df
/dev/disk3s5  971350180 750000000 217900000    78%  3000000 2000000000    0%   /System/Volumes/Data
"""


def reading(**kw):
    r = {'ncpu': 8, 'memory_mb': 16384, 'memory_level': 60, 'available_mb': 8000, 'load1': 2.0, 'disk_free_gb': 100.0}
    r.update(kw)
    return r


class CapacityTest(unittest.TestCase):
    def test_parses_a_macs_readings(self):
        r = capacity.parse(SAMPLE)
        self.assertEqual((r['ncpu'], r['memory_mb'], r['memory_level'], r['load1']), (12, 32768, 58, 3.2))
        self.assertEqual(r['available_mb'], (40000 + 150000 + 10000) * 16384 // (1024 * 1024))
        self.assertAlmostEqual(r['disk_free_gb'], round(217900000 / 1024 / 1024, 1))

    def test_checks_memory_cpu_and_disk(self):
        lim = dict(capacity.DEFAULTS)
        self.assertEqual(capacity.check(reading(), lim), [])
        self.assertEqual(capacity.check(reading(available_mb=2000), lim), ['memory'])
        self.assertEqual(capacity.check(reading(memory_level=10), lim), ['memory'])     # kernel says pressure
        self.assertEqual(capacity.check(reading(load1=7.0), lim), ['cpu'])                # 7/8 >= 0.85
        self.assertEqual(capacity.check(reading(disk_free_gb=3), lim), ['disk'])
        self.assertEqual(capacity.check(None, lim), [])                                    # unread: don't hold
        self.assertEqual(capacity.check(reading(load1=7.0), {**lim, 'max_load': 0.95}), [])
        after = capacity.started(reading(available_mb=4000), lim)
        self.assertEqual((after['available_mb'], after['load1']), (4000 - 3072, 3.0))

    def test_suggests_sessions_from_the_macs_size(self):
        self.assertEqual(capacity.suggest_sessions(32768, 12), 6)      # min(6, (32-8)/3 = 8)
        self.assertEqual(capacity.suggest_sessions(16384, 10), 2)      # min(5, (16-8)/3 = 2)
        self.assertEqual(capacity.suggest_sessions(8192, 8), 1)        # never less than one

    def test_touches_overlap(self):
        self.assertTrue(touches_overlap(['src/a.py'], ['src/a.py']))
        self.assertTrue(touches_overlap(['src/'], ['src/a.py']))
        self.assertTrue(touches_overlap(['./src/a.py'], ['src/*.py']))
        self.assertFalse(touches_overlap(['src/a.py'], ['src/ab.py']))
        self.assertFalse(touches_overlap(['docs/'], ['src/a.py']))


class ReadingRunner(FakeRunner):
    """A fake runner whose Mac reads as given."""

    def __init__(self, home, reading=None):
        super().__init__(home)
        self.reading = reading
        self.reads = 0

    def capacity(self):
        self.reads += 1
        return self.reading


class ParallelTest(LoopTest):
    def setUp(self):
        super().setUp()
        self.runner = ReadingRunner(self.tmp.name, reading())
        self.runner.cfg = {'check_cmd': 'true'}                       # the real default: no free hand
        self.loop.runner = self.runner
        self.con.execute("UPDATE runners SET slots=3 WHERE name='This Mac'")

    def building(self):
        return sorted(r['ticket'] for r in self.con.execute('SELECT ticket FROM runs WHERE ended_at IS NULL'))

    def test_disjoint_touches_run_together_and_overlapping_ones_wait(self):
        a = self.file(title='A', touches=['src/a.py'])
        b = self.file(title='B', touches=['src/b.py'])
        c = self.file(title='C', touches=['src/'])
        self.loop.tick()
        self.assertEqual(self.building(), [a, b])
        self.assertEqual(db.ticket(self.con, c)['hold'], f'waiting: touches the same files as {a}')
        snap = {t['id']: t for t in status.snapshot(self.con)['tickets']}
        self.assertEqual(snap[c]['hold'], f'waiting: touches the same files as {a}')
        self.assertIsNone(snap[a]['hold'])

    def test_no_touches_means_one_at_a_time_unless_the_repo_says_otherwise(self):
        a, b = self.file(title='A'), self.file(title='B')
        self.loop.tick()
        self.assertEqual(self.building(), [a])
        self.assertIn(a, db.ticket(self.con, b)['hold'])
        self.runner.cfg['parallel_without_touches'] = True
        self.loop.tick()
        self.assertEqual(self.building(), [a, b])
        self.assertIsNone(db.ticket(self.con, b)['hold'])

    def test_a_busy_mac_holds_new_work_and_never_stops_running_work(self):
        a = self.file(title='A', touches=['a'])
        self.loop.tick()
        self.assertEqual(self.building(), [a])
        b = self.file(title='B', touches=['b'])
        self.runner.reading = reading(available_mb=1000)
        self.loop.tick()
        self.assertEqual(self.building(), [a])                                   # a keeps going
        self.assertEqual(db.ticket(self.con, b)['hold'], 'waiting: This Mac is busy (memory)')
        mac = next(r for r in status.snapshot(self.con)['runners'] if r['name'] == 'This Mac')
        self.assertEqual((mac['load']['hold'], mac['load']['summary']), ('busy (memory)', 'busy (memory)'))
        self.assertEqual((mac['load']['sessions_running'], mac['load']['sessions_max']), (1, 3))
        self.runner.reading = reading()                                           # room again: it starts
        self.loop.tick()
        self.assertEqual(self.building(), [a, b])
        self.assertIsNone(db.ticket(self.con, b)['hold'])
        mac = next(r for r in status.snapshot(self.con)['runners'] if r['name'] == 'This Mac')
        self.assertEqual((mac['load']['hold'], mac['load']['summary']), (None, 'memory ok'))

    def test_one_tick_only_starts_what_fits_and_reads_once(self):
        a, b, c = (self.file(title=x, touches=[x]) for x in 'abc')
        self.runner.reading = reading(available_mb=7000)                # room for two at 3072 each
        self.loop.tick()
        self.assertEqual(self.building(), [a, b])
        self.assertEqual(db.ticket(self.con, c)['hold'], 'waiting: This Mac is busy (memory)')
        self.assertEqual(self.runner.reads, 1)

    def test_limits_are_per_runner(self):
        self.con.execute("UPDATE runners SET per_session_mb=1024, max_load=0.95 WHERE name='This Mac'")
        self.runner.reading = reading(available_mb=2500, load1=7.2)       # fine under these limits
        a = self.file(title='A', touches=['a'])
        self.loop.tick()
        self.assertEqual(self.building(), [a])


class BlockedTest(LoopTest):
    def test_status_says_what_blocks_what(self):
        a = self.file(title='First', key='a')
        b = self.file(title='Second', key='b', blocked_by=[a])
        c = self.file(title='Third', key='c', blocked_by=[b])
        snap = {t['id']: t for t in status.snapshot(self.con)['tickets']}
        self.assertEqual(snap[a]['blocks'], [b])
        self.assertEqual(snap[b]['blocks'], [c])
        self.assertEqual(snap[c]['blocked_by'], [{'id': b, 'title': 'Second', 'column': 'up_next', 'waits_on': [a]}])
        self.assertEqual(snap[a]['blocked_by'], [])
        # The take-back prompt for the blocker says what finishing it frees.
        self.assertIn(f'It blocks {b}: finishing it (runway give {a} or runway done {a})', take.prompt(self.con, a))
        db.update_ticket(self.con, a, state='done')
        snap = {t['id']: t for t in status.snapshot(self.con)['tickets']}
        self.assertEqual(snap[b]['blocked_by'], [])


if __name__ == '__main__':
    unittest.main()
