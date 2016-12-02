#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: BlahGeek
# @Date:   2016-11-22
# @Last Modified by:   BlahGeek
# @Last Modified time: 2016-12-02


import os
import sys
import json
import time
import heapq
import socket
import getpass
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
from gi.repository import GdkPixbuf
from pullover.client import PulloverClient


logger = logging.getLogger(__name__)


# Hack to notify2
# Keep notifications for a while, for actions
class TimeoutDict(dict):

    def __init__(self, timeout, *args, **kwargs):
        self.timeout = timeout
        self.timers = list()
        super().__init__(*args, **kwargs)

    def _cleanup(self):
        now = time.time()
        while self.timers and now > self.timers[0][0] + self.timeout:
            _, key = heapq.heappop(self.timers)
            super().__delitem__(key)

    def __setitem__(self, key, value):
        now = time.time()
        heapq.heappush(self.timers, (now, key))
        self._cleanup()
        return super().__setitem__(key, value)

    def __delitem__(self, key):
        self._cleanup()
        # and do nothing


def notification_copy(notification, action, text):
    pyperclip.copy(text)
    logger.info('Action: notification copied')


def notify_send(msg):
    title = msg.get('title') or msg.get('app', '').strip()
    body = msg.get('message', '').strip()

    if 'url' in msg:
        url = '\n<i>{}</i>'.format(msg['url'] if 'url_title' not in msg
                                   else msg['url_title'] + ': ' + msg['url'])
    else:
        url = ''

    notification = notify2.Notification(title, body + url)

    if msg.get('icon', ''):
        notification.icon = msg['icon']
        icon_data = GdkPixbuf.Pixbuf.new_from_file(msg['icon'])
        notification.set_icon_from_pixbuf(icon_data)

    priority = msg.get('priority', 0)
    if priority < 0:
        notification.set_urgency(notify2.URGENCY_LOW)
    elif priority > 0:
        notification.set_urgency(notify2.URGENCY_CRITICAL)
    else:
        notification.set_urgency(notify2.URGENCY_NORMAL)

    notification.add_action('copy_text', 'Copy Text: {:.30}'.format(body),
                            notification_copy, body)
    notification.show()


async def main(loop, secret, device_id, pull_interval, cache_dir):
    async with aiohttp.ClientSession(loop=loop) as session:
        client = PulloverClient(session, secret, device_id, cache_dir)

        def _do_pull():
            asyncio.ensure_future(client.message_get_and_update(notify_send))
            loop.call_later(pull_interval, _do_pull)

        loop.call_later(pull_interval, _do_pull)
        await client.watch_loop(notify_send)


if __name__ == '__main__':
    parser = argparse.ArgumentParser('Pullover-CLI')
    parser.add_argument('-c', '--conf', dest='conf',
                        help='File to store user secret, default: %(default)s',
                        default=os.path.expanduser('~/.pullover/config'))
    parser.add_argument('-v', dest='loglevel',
                        choices=['DEBUG', 'INFO', 'WARNING'])

    subparsers = parser.add_subparsers(title='Subcommand', dest='subcommand')

    parser_reg = subparsers.add_parser('register', help='Register new device, '
                                                        'Store secret to conf')
    parser_reg.add_argument('email', help='Email (username)')
    parser_reg.add_argument('--name', help='Device name, default: %(default)s',
                            default=socket.gethostname())

    parser_pull = subparsers.add_parser('pull', help='Pull messages')
    parser_pull.add_argument('--cache',
                             help='Cache directory, default: %(default)s',
                             default=os.path.expanduser('~/.pullover'))
    parser_pull.add_argument('--action-timeout', dest='action_timeout',
                             help='Seconds allowed to use action',
                             default=3600*24)
    parser_pull.add_argument('--appname', default='Pullover',
                             help='App name for libnotify')
    parser_pull.add_argument('--pull-interval', type=int, default=600,
                             help='Pull interval in seconds, '
                                  'to prevent push lost')

    parser_info = subparsers.add_parser('info', help='Print current conf')

    args = parser.parse_args()
    if args.loglevel:
        logging.basicConfig(level=getattr(logging, args.loglevel))

    if not args.subcommand:
        print('No subcommand specified.')
        sys.exit(1)

    loop = asyncio.get_event_loop()

    if args.subcommand == 'register':
        print('Registering device {} for user {}'
              .format(args.name, args.email))
        password = getpass.getpass()
        secret, device_id = loop.run_until_complete(
                                PulloverClient.register(
                                    args.email, password, args.name))
        os.makedirs(os.path.dirname(args.conf))
        json.dump({
                      'email': args.email,
                      'secret': secret,
                      'device_id': device_id,
                      'device_name': args.name,
                  }, open(args.conf, 'w'))
        print('Infomation written to {}'.format(args.conf))
        sys.exit(0)

    infos = json.load(open(args.conf))
    print('User:', infos['email'])
    print('Device Name:', infos['device_name'])
    if args.subcommand == 'info':
        sys.exit(0)

    notify2.notifications_registry = TimeoutDict(args.action_timeout)
    notify2.init(args.appname, 'glib')
    glib_thread = threading.Thread(target=lambda: Gtk.main())
    glib_thread.start()

    loop.run_until_complete(main(loop, infos['secret'], infos['device_id'],
                                 args.pull_interval, args.cache))
