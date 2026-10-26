import os
import unittest

from runway import worker

TICKET = {'id': 'T-5', 'title': 'Detection rules', 'body': 'b', 'risk': 'low',
          'acceptance': '["A3: change the feet-off threshold 0.5 to 0.3 and see a fixture test fail"]'}


class ReviewPromptTest(unittest.TestCase):
    def prompt(self, role):
        return worker.review_prompt(TICKET, 'app', 'abc1234', 'origin/main', 'swift test', '/tmp/out.json',
                                    ['swift test'], role=role)

    def test_the_function_reviewer_may_run_and_undo_an_experiment(self):
        p = self.prompt('function')
        self.assertIn('you may change files here for an experiment', p)
        self.assertIn('git restore', p)
        self.assertIn('never commit or push', p)
        self.assertNotIn('you never edit', p)

    def test_the_code_reviewer_stays_read_only(self):
        p = self.prompt('code')
        self.assertIn('you never edit, commit or push', p)
        self.assertNotIn('experiment', p)

    def test_sessions_may_undo_with_git_restore_but_not_commit(self):
        tools = worker.allowed_tools(['swift test'], '/tmp/run')
        self.assertIn('Bash(git restore:*)', tools)
        self.assertNotIn('Bash(git commit:*)', tools)
        self.assertNotIn('Bash(git push:*)', tools)


if __name__ == '__main__':
    unittest.main()


class BuildCachesTest(unittest.TestCase):
    """Swift and iOS builds under the sandbox: own temp and module cache, and Codex may write the tool caches."""

    def setUp(self):
        import tempfile
        from pathlib import Path
        self.tmp = tempfile.TemporaryDirectory()
        self.home = Path(self.tmp.name) / 'home'
        (self.home / 'Library/Developer/Xcode/DerivedData').mkdir(parents=True)
        (self.home / 'Library/Caches/org.swift.swiftpm').mkdir(parents=True)
        self.cache = Path(self.tmp.name) / 'runway' / 'cache' / 'app'
        self.old = os.environ.get('HOME')
        os.environ['HOME'] = str(self.home)

    def tearDown(self):
        os.environ['HOME'] = self.old
        self.tmp.cleanup()

    def line(self, agent):
        from pathlib import Path
        return worker.command(agent, Path('/r/prompt.md'), Path('/r'), Path('/wt'), ['swift test'], session_id='s',
                              cache=self.cache)

    def test_codex_gets_the_tool_caches_as_writable_folders(self):
        line = self.line('codex')
        self.assertTrue(line.startswith(f'export TMPDIR={self.cache}/tmp/ CLANG_MODULE_CACHE_PATH={self.cache}/ModuleCache;'))
        self.assertIn(f'--add-dir {self.home}/Library/Developer/Xcode/DerivedData', line)
        self.assertIn(f'--add-dir {self.home}/Library/Caches/org.swift.swiftpm', line)
        self.assertIn(f'--add-dir {self.cache}', line)
        self.assertNotIn('CoreSimulator', line)                      # only folders that exist
        self.assertIn('-s workspace-write', line)                    # the sandbox itself is unchanged
        self.assertTrue((self.cache / 'ModuleCache').is_dir())

    def test_claude_gets_the_same_env_and_no_extra_folders(self):
        line = self.line('claude')
        self.assertIn(f'CLANG_MODULE_CACHE_PATH={self.cache}/ModuleCache', line)
        self.assertNotIn('DerivedData', line)

    def test_without_a_cache_nothing_changes(self):
        from pathlib import Path
        line = worker.command('codex', Path('/r/prompt.md'), Path('/r'), Path('/wt'), ['swift test'])
        self.assertTrue(line.startswith('codex exec'))
