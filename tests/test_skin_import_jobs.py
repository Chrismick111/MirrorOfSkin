import sys
import threading
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'MirrorOfSkin' / 'Workbench'))
from skin_import_jobs import ImportJobs


FIRST = Path.cwd() / 'first.zip'
SECOND = Path.cwd() / 'second.zip'


class ImportJobsTest(unittest.TestCase):
    def make_jobs(self, pick, importer):
        jobs = ImportJobs(pick, importer)
        self.addCleanup(jobs.join)
        self.addCleanup(jobs.stop)
        return jobs

    def test_repeated_start_reuses_picker_then_reports_batch_progress(self):
        picker_entered = threading.Event()
        allow_pick = threading.Event()
        importer_entered = threading.Event()
        allow_import = threading.Event()
        calls = []

        def pick():
            calls.append('pick')
            picker_entered.set()
            allow_pick.wait(5)
            return [str(FIRST), str(SECOND)]

        def importer(path, *, progress, check_cancelled):
            calls.append(path)
            if path == FIRST:
                progress(50, 'composing')
                importer_entered.set()
                allow_import.wait(5)
                return [{'name': 'first'}]
            raise ValueError('broken archive')

        jobs = self.make_jobs(pick, importer)
        self.addCleanup(allow_pick.set)
        self.addCleanup(allow_import.set)
        self.assertEqual(jobs.state()['stage'], 'idle')
        started = jobs.start()
        self.assertTrue(picker_entered.wait(5))
        self.assertEqual(jobs.state()['stage'], 'picking')
        self.assertEqual(jobs.start()['jobId'], started['jobId'])
        with self.assertRaises(ValueError):
            jobs.run([str(FIRST)])
        allow_pick.set()
        self.assertTrue(importer_entered.wait(5))
        state = jobs.state()
        self.assertEqual((state['stage'], state['done'], state['total']), ('importing', 0, 2))
        self.assertEqual((state['filename'], state['percent'], state['message']), (FIRST.name, 25, 'composing'))
        allow_import.set()
        jobs.join()
        state = jobs.state()
        self.assertEqual(calls, ['pick', FIRST, SECOND])
        self.assertEqual((state['stage'], state['percent']), ('done', 100))
        self.assertEqual(state['rows'], [{'name': 'first'}])
        self.assertEqual(state['errors'], ['second.zip：broken archive'])

    def test_cancelled_picker_keeps_empty_results(self):
        jobs = self.make_jobs(lambda: [], self.fail)
        self.assertEqual(jobs.run(), {'rows': [], 'errors': []})
        self.assertTrue(jobs.state()['cancelled'])

    def test_shutdown_stops_before_commit(self):
        waiting = threading.Event()
        resume = threading.Event()
        wrote = []

        def importer(path, *, progress, check_cancelled):
            waiting.set()
            resume.wait(5)
            progress(75, 'indexing')
            wrote.append(path)

        jobs = self.make_jobs(lambda: [], importer)
        self.addCleanup(resume.set)
        jobs.start([str(FIRST), str(SECOND)])
        self.assertTrue(waiting.wait(5))
        jobs.stop()
        resume.set()
        jobs.join()
        self.assertEqual(wrote, [])

    def test_shutdown_finishes_committed_archive_and_skips_rest(self):
        committing = threading.Event()
        resume = threading.Event()
        wrote = []

        def importer(path, *, progress, check_cancelled):
            check_cancelled(committing=True)
            committing.set()
            resume.wait(5)
            progress(99, 'synchronizing')
            wrote.append(path)
            return [{'name': path.name}]

        jobs = self.make_jobs(lambda: [], importer)
        self.addCleanup(resume.set)
        jobs.start([str(FIRST), str(SECOND)])
        self.assertTrue(committing.wait(5))
        jobs.stop()
        resume.set()
        jobs.join()
        self.assertEqual(wrote, [FIRST])
        self.assertEqual(jobs.state()['rows'], [{'name': FIRST.name}])


if __name__ == '__main__':
    unittest.main()
