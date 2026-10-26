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
