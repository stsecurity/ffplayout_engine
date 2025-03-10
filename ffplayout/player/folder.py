# This file is part of ffplayout.
#
# ffplayout is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# ffplayout is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with ffplayout. If not, see <http://www.gnu.org/licenses/>.

# ------------------------------------------------------------------------------

"""
This module handles folder reading. It monitor file adding, deleting or moving
"""

import random
import time
from copy import deepcopy
from pathlib import Path

from watchdog.events import PatternMatchingEventHandler
from watchdog.observers import Observer

from ..filters.default import build_filtergraph
from ..utils import (MediaProbe, ff_proc, get_float, messenger, stdin_args,
                    storage)

# ------------------------------------------------------------------------------
# folder watcher
# ------------------------------------------------------------------------------


class MediaStore:
    """
    fill media list for playing
    MediaWatch will interact with add and remove
    """

    def __init__(self):
        self.store = []

        if stdin_args.folder:
            self.folder = stdin_args.folder
        else:
            self.folder = storage.path

        self.fill()

    def fill(self):
        """
        fill media list
        """
        for ext in storage.extensions:
            self.store.extend(
                [str(f) for f in Path(self.folder).rglob(f'*{ext}')])

    def sort_or_radomize(self):
        """
        sort or randomize file list
        """
        if storage.shuffle:
            self.rand()
        else:
            self.sort()

    def add(self, file):
        """
        add new file to media list
        """
        self.store.append(file)
        self.sort_or_radomize()

    def remove(self, file):
        """
        remove file from media list
        """
        self.store.remove(file)
        self.sort_or_radomize()

    def sort(self):
        """
        sort list for sorted playing
        """
        self.store = sorted(self.store)

    def rand(self):
        """
        randomize list for playing
        """
        random.shuffle(self.store)


class MediaWatcher:
    """
    watch given folder for file changes and update media list
    """

    def __init__(self, media):
        self._media = media
        self.extensions = [f'*{ext}' for ext in storage.extensions]
        self.current_clip = None

        self.event_handler = PatternMatchingEventHandler(
            patterns=self.extensions)
        self.event_handler.on_created = self.on_created
        self.event_handler.on_moved = self.on_moved
        self.event_handler.on_deleted = self.on_deleted

        self.observer = Observer()
        self.observer.schedule(self.event_handler, self._media.folder,
                               recursive=True)

        self.observer.start()

    def on_created(self, event):
        """
        add file to media list only if it is completely copied
        """
        file_size = -1
        while file_size != Path(event.src_path).stat().st_size:
            file_size = Path(event.src_path).stat().st_size
            time.sleep(1)

        self._media.add(event.src_path)

        messenger.info(f'Add file to media list: "{event.src_path}"')

    def on_moved(self, event):
        """
        operation when file on storage are moved
        """
        self._media.remove(event.src_path)
        self._media.add(event.dest_path)

        messenger.info(
            f'Move file from "{event.src_path}" to "{event.dest_path}"')

        if self.current_clip == event.src_path:
            ff_proc.decoder.terminate()

    def on_deleted(self, event):
        """
        operation when file on storage are deleted
        """
        self._media.remove(event.src_path)

        messenger.info(f'Remove file from media list: "{event.src_path}"')

        if self.current_clip == event.src_path:
            ff_proc.decoder.terminate()

    def stop(self):
        """
        stop monitoring storage
        """
        self.observer.stop()
        self.observer.join()


class GetSourceIter:
    """
    give next clip, depending on shuffle mode
    """

    def __init__(self):
        self.media = MediaStore()
        self.watcher = MediaWatcher(self.media)

        self.last_played = []
        self.index = 0
        self.probe = MediaProbe()
        self.next_probe = MediaProbe()
        self.node = None
        self.node_last = None
        self.node_next = None

    def stop(self):
        self.watcher.stop()

    def next(self):
        """
        generator for getting always a new file
        """
        while True:
            while self.index < len(self.media.store):
                if self.node_next:
                    self.node = deepcopy(self.node_next)
                    self.probe = deepcopy(self.next_probe)
                else:
                    self.probe.load(self.media.store[self.index])
                    duration = get_float(self.probe.format.get('duration'), 0)
                    self.node = {
                        'in': 0,
                        'seek': 0,
                        'out': duration,
                        'duration': duration,
                        'source': self.media.store[self.index],
                        'probe': self.probe
                    }
                if self.index < len(self.media.store) - 1:
                    self.next_probe.load(self.media.store[self.index + 1])
                    next_duration = get_float(
                        self.next_probe.format.get('duration'), 0)
                    self.node_next = {
                        'in': 0,
                        'seek': 0,
                        'out': next_duration,
                        'duration': next_duration,
                        'source': self.media.store[self.index + 1],
                        'probe': self.next_probe
                    }
                else:
                    self.media.rand()
                    self.node_next = None

                self.node['src_cmd'] = ['-i', self.media.store[self.index]]
                self.node['filter'] = build_filtergraph(
                    self.node, self.node_last, self.node_next)

                self.watcher.current_clip = self.node.get('source')
                yield self.node
                self.index += 1
                self.node_last = deepcopy(self.node)

            self.index = 0
