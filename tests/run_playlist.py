#!/usr/bin/env python3

import datetime
import os
import sys
from time import sleep
from zoneinfo import ZoneInfo

import time_machine

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


# set time zone
_TZ = ZoneInfo("Europe/Berlin")
# fake date and time
SOURCE_TIME = [2021, 2, 27, 23, 55, 0]


@time_machine.travel(datetime.datetime(*SOURCE_TIME, tzinfo=_TZ))
def main():
    get_source = GetSourceIter()

    for node in get_source.next():
        messenger.info(f'Play: {node["source"]}')
        # print(node)
        sleep(node['out'] - node['seek'])


if __name__ == '__main__':
    from ffplayout.player.playlist import GetSourceIter
    from ffplayout.utils import messenger
    try:
        main()
    except KeyboardInterrupt:
        print('\n', end='')
