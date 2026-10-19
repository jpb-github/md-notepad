from mdviewer.core.filewatch import Watcher, WatchEvent


class FakeStat:
    def __init__(self, mtime_ns: int, size: int):
        self.st_mtime_ns = mtime_ns
        self.st_size = size


class Disk:
    """Fake disk: state is (mtime_ns, size), or None when the file is gone."""

    def __init__(self):
        self.state = None

    def stat(self, path):
        if self.state is None:
            raise FileNotFoundError(str(path))
        return FakeStat(*self.state)


def make_watcher(disk: Disk) -> Watcher:
    return Watcher("test.md", disk.stat)


def test_first_poll_baselines_unchanged():
    disk = Disk()
    disk.state = (100, 10)
    assert make_watcher(disk).poll() == WatchEvent.UNCHANGED


def test_external_change_detected():
    disk = Disk()
    disk.state = (100, 10)
    watcher = make_watcher(disk)
    watcher.poll()
    disk.state = (200, 11)
    assert watcher.poll() == WatchEvent.CHANGED
    assert watcher.poll() == WatchEvent.UNCHANGED


def test_own_save_echo_suppressed():
    disk = Disk()
    disk.state = (100, 10)
    watcher = make_watcher(disk)
    watcher.poll()
    watcher.note_write(300, 99)
    disk.state = (300, 99)
    assert watcher.poll() == WatchEvent.UNCHANGED


def test_external_change_differs_from_expected_write():
    disk = Disk()
    disk.state = (100, 10)
    watcher = make_watcher(disk)
    watcher.poll()
    watcher.note_write(300, 99)
    disk.state = (400, 12)
    assert watcher.poll() == WatchEvent.CHANGED


def test_missing_file_reports_once():
    disk = Disk()
    disk.state = (100, 10)
    watcher = make_watcher(disk)
    watcher.poll()
    disk.state = None
    assert watcher.poll() == WatchEvent.MISSING
    assert watcher.poll() == WatchEvent.UNCHANGED


def test_reappearing_file_reports_changed():
    disk = Disk()
    disk.state = (100, 10)
    watcher = make_watcher(disk)
    watcher.poll()
    disk.state = None
    assert watcher.poll() == WatchEvent.MISSING
    disk.state = (500, 42)
    assert watcher.poll() == WatchEvent.CHANGED
    assert watcher.poll() == WatchEvent.UNCHANGED


def test_missing_before_first_poll_is_unchanged():
    disk = Disk()
    disk.state = None
    assert make_watcher(disk).poll() == WatchEvent.UNCHANGED


def test_event_values_are_plain_strings():
    assert WatchEvent.CHANGED == "changed"
    assert WatchEvent.MISSING == "missing"
    assert WatchEvent.UNCHANGED == "unchanged"
