"""Map a stage's progress onto its share of one archive import."""


def progress_range(callback, start=0, end=100):
    if callback is None:
        return lambda percent, message: None

    def report(percent, message):
        callback(start + (end - start) * percent // 100, message)

    return report
