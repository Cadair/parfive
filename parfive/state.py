from abc import ABCMeta, abstractmethod


class DownloadState:
    def __init__(self):
        self._observers = []

    def add_observer(self, observer):
        self._observers.append(observer)

    def update(self, chunk, offset=None):
        for obs in self._observers:
            obs.notify(chunk, offset)


class Observer(metaclass=ABCMeta):
    @abstractmethod
    def notify(self, chunk):
        """
        Callback for the observer after a chunk has been downloaded

        Paramaeters
        -----------

        chunk: bytes
            The downloaded chunk of file.
        """
        raise NotImplementedError


class FileWriter(Observer):
    def __init__(self, filepath):
        self._filepath = filepath
        self._file = open(filepath, 'wb')

    def notify(self, chunk, offset, *args):
        self._write_chunk(chunk, offset)

    def _write_chunk(self, chunk, offset):
        # with open(self._filepath, 'wb') as f:
        if offset:
            self._file.seek(offset)
        self._file.write(chunk)
        self._file.flush()


class DownloadProgress(Observer):
    def __init__(self, file_pb):
        self._file_pb = file_pb

    def notify(self, chunk, *args):
        self._file_pb.update(len(chunk))
