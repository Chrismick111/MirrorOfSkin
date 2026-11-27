import os
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

    def test_batch_exposes_completed_files_in_order_with_row_ranges(self):
        bad = Path.cwd() / 'bad.zip'
        last_started = threading.Event()
        resume = threading.Event()
        calls = []

        def importer(path, *, progress, check_cancelled):
            calls.append(path)
            if path == FIRST:
                return [{'name': 'one'}, {'name': 'two'}]
            if path == bad:
                # A partial iterator result must stay isolated from the other files.
                def broken_archive():
                    yield {'name': 'discard me'}
                    raise ValueError('bad archive')
                return broken_archive()
            progress(50, 'third file')
            last_started.set()
            resume.wait(5)
            return [{'name': 'three'}]

        jobs = self.make_jobs(lambda: [], importer)
        self.addCleanup(resume.set)
        started = jobs.start([str(FIRST), str(bad), str(SECOND)])
        self.assertTrue(last_started.wait(5))
        state = jobs.state()
        self.assertEqual((state['jobId'], state['done'], state['total'], state['percent']),
                         (started['jobId'], 2, 3, 83))
        first_two = [
            {'filename': FIRST.name, 'rowStart': 0, 'rowCount': 2, 'error': ''},
            {'filename': bad.name, 'rowStart': 2, 'rowCount': 0, 'error': 'bad archive'},
        ]
        self.assertEqual(state['files'], first_two)
        state['files'][0]['error'] = 'mutated snapshot'
        state['files'].clear()
        self.assertEqual(jobs.state()['files'], first_two)
        resume.set()
        jobs.join()
        final = jobs.state()
        self.assertEqual(calls, [FIRST, bad, SECOND])
        self.assertEqual((final['stage'], final['done'], final['percent']), ('done', 3, 100))
        self.assertEqual([row['name'] for row in final['rows']], ['one', 'two', 'three'])
        self.assertEqual(final['errors'], ['bad.zip：bad archive'])
        self.assertEqual(final['files'], first_two + [
            {'filename': SECOND.name, 'rowStart': 2, 'rowCount': 1, 'error': ''},
        ])

    def test_path_aliases_are_deduplicated_but_same_basename_is_preserved(self):
        same_basename = FIRST.parent / 'subdir' / FIRST.name
        alternate_path = str(FIRST.parent / 'unrelated' / '..' / FIRST.name)
        if os.name == 'nt':
            alternate_path = alternate_path.upper().replace('\\', '/')
        calls = []

        def importer(path, **kwargs):
            calls.append(path)
            return [{'name': path.name}]

        jobs = self.make_jobs(lambda: [str(FIRST), alternate_path, str(same_basename)], importer)
        self.assertEqual(jobs.run(), {'rows': [{'name': FIRST.name}] * 2, 'errors': []})
        self.assertEqual(calls, [FIRST, same_basename])
        self.assertEqual(jobs.state()['total'], 2)
        self.assertEqual([file['rowStart'] for file in jobs.state()['files']], [0, 1])

    def test_single_file_api_keeps_legacy_result_and_replaces_previous_job(self):
        def importer(path, **kwargs):
            if path == SECOND:
                raise ValueError('bad file')
            return [{'name': path.name}]

        jobs = self.make_jobs(lambda: [], importer)
        self.assertEqual(jobs.run([str(FIRST)]), {'rows': [{'name': FIRST.name}], 'errors': []})
        first_job = jobs.state()
        self.assertEqual(first_job['files'], [
            {'filename': FIRST.name, 'rowStart': 0, 'rowCount': 1, 'error': ''},
        ])
        self.assertEqual(jobs.run([str(SECOND)]), {'rows': [], 'errors': ['second.zip：bad file']})
        second_job = jobs.state()
        self.assertNotEqual(second_job['jobId'], first_job['jobId'])
        self.assertEqual(second_job['stage'], 'error')
        self.assertEqual(second_job['files'], [
            {'filename': SECOND.name, 'rowStart': 0, 'rowCount': 0, 'error': 'bad file'},
        ])

    def test_cancelled_picker_keeps_empty_results(self):
        jobs = self.make_jobs(lambda: [], self.fail)
        self.assertEqual(jobs.run(), {'rows': [], 'errors': []})
        self.assertTrue(jobs.state()['cancelled'])
        self.assertEqual(jobs.state()['files'], [])

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
        self.assertEqual(jobs.state()['files'], [])

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
        self.assertEqual(jobs.state()['files'], [
            {'filename': FIRST.name, 'rowStart': 0, 'rowCount': 1, 'error': ''},
        ])


if __name__ == '__main__':
    unittest.main()
