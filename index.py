'''This Module represents the index.dat file soupchef uses to keep track of already scraped recipe IDs.

The index automatically manages an internal list of scraped IDs and makes sure that the
index.dat file gets written correctly to disk when the program is interrupted or terminated'''

import sys
import os
import signal
import logging

_logger = logging.getLogger('soupchef.index')
_instance = None

def open_index(index_file_path: str) -> None:
    '''Opens a new index file
    Parameters
    ----------
    index_file_path: str or path-like object
        The path to the index file to be opened.
    '''

    _logger.info('Opening index file ' + index_file_path)

    global _instance
    if not _instance or _instance._index_file_path != index_file_path:
        if _instance:
            _instance._close_index()
        _instance = _Index(index_file_path)
    return _instance

class _Index():
    '''Magical internal helper class of the index module'''

    def add(self, element: str) -> None:
        '''Adds an element to the index. Automatically manages duplicate entries by only adding new IDs.
        
        Parameters
        ----------
        element: str
            A new element to be added to the index. The element should be a str. If not it will be converted to str.
        '''

        if element not in self._index:
            self._index.append(element)
            self._index_file.write(str(element) + '\n')

    def _close_index(self):
        '''Closes the currently open index file'''

        if self._index_file and not self._index_file.closed:
            _logger.info('Flushing index file')
            self._index_file.flush()
            os.fsync(self._index_file.fileno())
            self._index_file.close()
            _logger.info('Index file closed')

    def _sigint_handler(self, sig, frame):
        '''Handler to catch SIGINT (Ctrl+C). In case of SIGINT this handler flushes and writes out the index.dat file'''

        _logger.info('SIGINT received')
        self._close_index()
        sys.exit(0)

    def __iter__(self):
        return self._index.__iter__()

    def __len__(self):
        return len(self._index)

    def __contains__(self, item):
        return item in self._index

    def __init__(self, index_file_path):
        self._index_file_path = index_file_path
        _logger.debug('New instance of Index created')
        try:
            with open(index_file_path, mode='r', encoding='utf-8-sig') as infile:
                self._index = [line.strip() for line in infile]
        except FileNotFoundError:
            _logger.info('Index file not found. Creating new one.')
            dirname = os.path.dirname(index_file_path)
            os.makedirs(dirname)
            self._index = []
        
        signal.signal(signal.SIGINT, self._sigint_handler)
        self._index_file = open(index_file_path, mode='a', encoding='utf-8-sig')
