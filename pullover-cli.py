#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: BlahGeek
# @Date:   2016-11-22
# @Last Modified by:   BlahGeek
# @Last Modified time: 2016-11-22


import logging
import argparse
import asyncio
import aiohttp

import gi
gi.require_version('Notify', '0.7')

from gi.repository import Notify
from pullover.client import PulloverClient


def notify_send(msg):
    title = msg.get('title') or msg.get('app', '')
    body = msg.get('message', '')
    if 'url' in msg:
        body += ' [{}]'.format(msg['url'])
    notification = Notify.Notification.new(title, body)
    notification.show()


async def main(loop, secret, device_id, pull_interval):
    async with aiohttp.ClientSession(loop=loop) as session:
        client = PulloverClient(session, secret, device_id)

        def _do_pull():
            asyncio.ensure_future(client.message_get_and_update(notify_send))
            loop.call_later(pull_interval, _do_pull)

        loop.call_soon(_do_pull)
        await client.watch_loop(notify_send)


if __name__ == '__main__':
    parser = argparse.ArgumentParser('Pullover-CLI')
    parser.add_argument('secret', help='Pushover secret key')
    parser.add_argument('device_id', help='Pushover device ID')
    parser.add_argument('--appname', default='Pullover',
                        help='App name for libnotify')
    parser.add_argument('--pull-interval', type=int, default=600,
                        help='Pull interval in seconds, to prevent push lost')
    parser.add_argument('-v', dest='loglevel',
                        choices=['DEBUG', 'INFO', 'WARNING'])

    args = parser.parse_args()
    if args.loglevel:
        logging.basicConfig(level=getattr(logging, args.loglevel))

    Notify.init(args.appname)

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(loop, args.secret, args.device_id,
                                 args.pull_interval))
