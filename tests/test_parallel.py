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
--cpu
CPU usage: 39.70% user, 14.94% sys, 45.36% idle
"""


def reading(**kw):
    r = {'ncpu': 8, 'memory_mb': 16384, 'memory_level': 60, 'available_mb': 8000, 'load1': 2.0, 'disk_free_gb': 100.0,
         'cpu_idle_pct': 70.0}
    r.update(kw)
    return r


class CapacityTest(unittest.TestCase):
    def test_parses_a_macs_readings(self):
        r = capacity.parse(SAMPLE)
        self.assertEqual((r['ncpu'], r['memory_mb'], r['memory_level'], r['load1']), (12, 32768, 58, 3.2))
        self.assertEqual(r['available_mb'], (40000 + 150000 + 10000) * 16384 // (1024 * 1024))
        self.assertAlmostEqual(r['disk_free_gb'], round(217900000 / 1024 / 1024, 1))
        self.assertEqual(r['cpu_idle_pct'], 45.4)
        self.assertIsNone(capacity.parse(SAMPLE.split('--cpu')[0])['cpu_idle_pct'])     # no top: CPU unknown

    def test_checks_an_extra_session_for_memory_cpu_and_disk(self):
        lim = dict(capacity.DEFAULTS)
        kinds = lambda r, running=1: [k for k, _ in capacity.check(r, lim, running)]
        self.assertEqual(kinds(reading()), [])
        self.assertEqual(capacity.check(reading(available_mb=2048), lim),
                         [('memory', '2 GB memory free, a session needs 3 GB')])
        self.assertEqual(kinds(reading(memory_level=10)), ['memory'])                    # kernel says pressure
        self.assertEqual(capacity.check(reading(cpu_idle_pct=10), lim), [('cpu', 'CPU 90% used, limit 85%')])
        self.assertEqual(kinds(reading(load1=40.0)), [])                                 # load average isn't used
        self.assertEqual(kinds(reading(disk_free_gb=3)), ['disk'])
        self.assertEqual(kinds(reading(cpu_idle_pct=None)), [])                          # CPU unread: no CPU hold
        self.assertEqual(capacity.check(None, lim), [])                                   # unread: don't hold
        after = capacity.started(reading(available_mb=4000), lim)
        self.assertEqual((after['available_mb'], after['cpu_idle_pct']), (4000 - 3072, 70.0 - 12.5))

    def test_the_first_session_waits_only_for_disk_or_critical_memory(self):
        lim = dict(capacity.DEFAULTS)
        busy = reading(cpu_idle_pct=2, available_mb=500, memory_level=12, load1=30)
        self.assertEqual(capacity.check(busy, lim, running=0), [])
        self.assertEqual([k for k, _ in capacity.check(busy, lim, running=1)], ['memory', 'cpu'])
        self.assertEqual(capacity.check(reading(memory_level=3), lim, running=0),
                         [('memory', 'memory pressure critical (3% free)')])
        self.assertEqual([k for k, _ in capacity.check(reading(disk_free_gb=1), lim, running=0)], ['disk'])
        self.assertEqual(capacity.summary(reading(available_mb=9420)), 'CPU 30% used · 9.2 GB free')

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
        self.runner.reading = reading(available_mb=1024)
        self.loop.tick()
        self.assertEqual(self.building(), [a])                                   # a keeps going
        self.assertEqual(db.ticket(self.con, b)['hold'],
                         'waiting: This Mac is busy (1 GB memory free, a session needs 3 GB)')
        mac = next(r for r in status.snapshot(self.con)['runners'] if r['name'] == 'This Mac')
        self.assertEqual((mac['load']['hold'], mac['load']['summary']), ('busy (memory)', 'CPU 30% used · 1 GB free'))
        self.assertEqual((mac['load']['sessions_running'], mac['load']['sessions_max']), (1, 3))
        self.runner.reading = reading()                                           # room again: it starts
        self.loop.tick()
        self.assertEqual(self.building(), [a, b])
        self.assertIsNone(db.ticket(self.con, b)['hold'])
        mac = next(r for r in status.snapshot(self.con)['runners'] if r['name'] == 'This Mac')
        self.assertEqual(mac['load']['hold'], None)
        self.assertEqual(mac['load']['cpu_used_pct'], 30)

    def test_one_tick_only_starts_what_fits_and_reads_once(self):
        a, b, c = (self.file(title=x, touches=[x]) for x in 'abc')
        self.runner.reading = reading(available_mb=7000)                # room for two at 3072 each
        self.loop.tick()
        self.assertEqual(self.building(), [a, b])
        self.assertEqual(db.ticket(self.con, c)['hold'], 'waiting: This Mac is busy (0.8 GB memory free, a session '
                         'needs 3 GB counting the sessions just started)')
        self.assertEqual(self.runner.reads, 1)

    def test_the_first_ticket_starts_on_a_busy_mac_and_the_second_waits_for_cpu(self):
        a, b = self.file(title='A', touches=['a']), self.file(title='B', touches=['b'])
        self.runner.reading = reading(cpu_idle_pct=5)              # e.g. Spotlight indexing
        self.loop.tick()
        self.assertEqual(self.building(), [a])
        self.assertEqual(db.ticket(self.con, b)['hold'], 'waiting: This Mac is busy (CPU 95% used, limit 85%)')

    def test_start_anyway_skips_the_check_once(self):
        a, b, c = (self.file(title=x, touches=[x]) for x in 'abc')
        self.runner.reading = reading(cpu_idle_pct=5)
        self.loop.tick()
        self.assertEqual(self.building(), [a])
        self.con.execute('UPDATE tickets SET ignore_capacity=1 WHERE id=?', (b,))
        self.loop.tick()
        self.assertEqual(self.building(), [a, b])                 # b went anyway; c still waits
        self.assertEqual(db.ticket(self.con, b)['ignore_capacity'], 0)
        self.assertIn('CPU 95% used', db.ticket(self.con, c)['hold'])

    def test_limits_are_per_runner(self):
        self.con.execute("UPDATE runners SET per_session_mb=1024, min_cpu_idle_pct=5 WHERE name='This Mac'")
        self.runner.reading = reading(available_mb=2500, cpu_idle_pct=20)  # room for two under these limits
        a, b = self.file(title='A', touches=['a']), self.file(title='B', touches=['b'])
        self.loop.tick()
        self.assertEqual(self.building(), [a, b])                           # 20% idle, then ~7.5% after a: >= 5


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
