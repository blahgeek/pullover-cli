#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: BlahGeek
# @Date:   2016-11-22
# @Last Modified by:   BlahGeek
# @Last Modified time: 2016-11-23


import logging
import argparse
import threading
import asyncio
import aiohttp
import notify2
import pyperclip

import gi
gi.require_version('Gtk', '3.0')

from gi.repository import Gtk
from pullover.client import PulloverClient


logger = logging.getLogger(__name__)


def notification_copy(notification, action, text):
    pyperclip.copy(text)
    logger.info('Action: notification copied')


def notify_send(msg):
    title = msg.get('title') or msg.get('app', '')
    body = msg.get('message', '')
    url = ' <i>{}</i>'.format(msg['url']) if 'url' in msg else ''

    notification = notify2.Notification(title, body + url)
    notification.add_action('copy_text', 'Copy Text: {:.30}'.format(body),
                            notification_copy, body)
    notification.show()


async def main(loop, secret, device_id, pull_interval):
    async with aiohttp.ClientSession(loop=loop) as session:
        client = PulloverClient(session, secret, device_id)

        def _do_pull():
            asyncio.ensure_future(client.message_get_and_update(notify_send))
            loop.call_later(pull_interval, _do_pull)

        loop.call_later(pull_interval, _do_pull)
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

    notify2.init(args.appname, 'glib')
    glib_thread = threading.Thread(target=lambda: Gtk.main())
    glib_thread.start()

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(loop, args.secret, args.device_id,
                                 args.pull_interval))
