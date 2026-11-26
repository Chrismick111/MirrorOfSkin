"""Run one local skin import at a time, with a status snapshot for the workbench."""

from pathlib import Path
from threading import Event, Lock, Thread
from uuid import uuid4


class _ImportStopped(BaseException):
    """Unwind temporary resources even through importer fallback handlers."""


def _paths(raw):
    if not isinstance(raw, list) or len(raw) > 128:
        raise ValueError('一次最多选择 128 个文件')
    if any(not isinstance(path, str) or not Path(path).is_absolute() for path in raw):
        raise ValueError('请选择本地文件')
    return [Path(path) for path in raw]


def _state(stage='idle', job_id=None, message=''):
    return dict(stage=stage, jobId=job_id, message=message, percent=0, done=0,
                total=0, filename='', rows=[], errors=[], cancelled=False)


def _copy(state):
    return dict(state, rows=list(state['rows']), errors=list(state['errors']))


class ImportJobs:
    def __init__(self, pick, importer):
        self._pick = pick
        self._import = importer
        self._lock = Lock()
        self._stopping = Event()
        self._thread = None
        self._state = _state()

    def state(self):
        with self._lock:
            return _copy(self._state)

    def start(self, paths=None):
        return self._submit(paths, background=True)

    def run(self, paths=None):
        state = self._submit(paths, background=False)
        return {'rows': state['rows'], 'errors': state['errors']}

    def stop(self):
        with self._lock:
            self._stopping.set()

    def join(self):
        with self._lock:
            thread = self._thread
        if thread is not None:
            thread.join()

    def _submit(self, paths, *, background):
        paths = _paths(paths) if paths is not None else None
        with self._lock:
            if self._stopping.is_set():
                raise ValueError('工作台正在退出')
            if self._state['stage'] in ('picking', 'importing'):
                if background:
                    return _copy(self._state)
                raise ValueError('已有本地外观导入正在进行')
            stage = 'picking' if paths is None else 'importing'
            message = '请选择要导入的模组文件' if paths is None else '正在准备导入'
            job = self._state = _state(stage, uuid4().hex, message)
            if background:
                self._thread = Thread(target=self._run, args=(job, paths, False),
                                      name='local-skin-import')
                self._thread.start()
                return _copy(job)
        return self._run(job, paths, True)

    def _run(self, job, paths, synchronous):
        def update(**fields):
            with self._lock:
                job.update(fields)
                return _copy(job)

        in_commit = False

        def check_cancelled(*, committing=False):
            nonlocal in_commit
            if self._stopping.is_set() and not in_commit:
                raise _ImportStopped()
            in_commit = in_commit or committing

        rows, errors = [], []
        try:
            check_cancelled()
            if paths is None:
                paths = _paths(self._pick())
            if not paths:
                return update(stage='done', cancelled=True, message='已取消文件选择')
            total = len(paths)
            for index, path in enumerate(paths):
                in_commit = False
                check_cancelled()
                base = index * 100 // total
                update(stage='importing', message='正在准备导入', filename=path.name,
                       done=index, total=total, percent=base)

                def report(percent, message):
                    check_cancelled()
                    update(percent=max(job['percent'], min(99, (index * 100 + percent) // total)),
                           message=message)

                try:
                    rows.extend(self._import(path, progress=report, check_cancelled=check_cancelled))
                except Exception as error:
                    errors.append(path.name + '：' + str(error))
                update(done=index + 1, rows=list(rows), errors=list(errors))
            failed = bool(errors and not rows)
            return update(stage='error' if failed else 'done', percent=100, filename='',
                          message='导入失败' if failed else '导入完成')
        except _ImportStopped:
            return update(stage='done', cancelled=True, message='工作台已关闭导入任务')
        except Exception as error:
            state = update(stage='error', errors=[str(error)], message=str(error))
            if synchronous:
                raise
            return state
