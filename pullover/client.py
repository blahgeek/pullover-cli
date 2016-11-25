#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: BlahGeek
# @Date:   2016-11-22
# @Last Modified by:   BlahGeek
# @Last Modified time: 2016-11-24


import enum
import logging
import asyncio

import aiohttp
import websockets


class PushoverException(Exception):
    pass


class PulloverClient:

    KEEPALIVE_TIMEOUT = 60
    RETRY_SLEEP = 30

    API_ENDPOINT = 'https://api.pushover.net/1'
    WSS_ENDPOINT = 'wss://client.pushover.net/push'

    class PushMessage(enum.Enum):
        KEEPALIVE = b'#'
        NEWMESSAGE = b'!'
        RELOADREQUEST = b'R'
        ERROR = b'E'

    logger = logging.getLogger(__name__)

    session = None
    secret = None
    device_id = None

    wss = None
    lock = None

    @classmethod
    async def register(cls, email, password, device_name):
        cls.logger.info('Registering device {}'.format(device_name))
        async with aiohttp.ClientSession() as session:
            async with session.post(cls.API_ENDPOINT + '/users/login.json',
                                    data={
                                        'email': email,
                                        'password': password,
                                    }) as response:
                result = await response.json()
                cls.logger.debug('Login result: {}'.format(result))
                cls._check_result(result)
                secret = result['secret']
                cls.logger.debug('Got user secert = {}'.format(secret))
            async with session.post(cls.API_ENDPOINT + '/devices.json',
                                    data={
                                        'secret': secret,
                                        'name': device_name,
                                        'os': 'O',
                                    }) as response:
                result = await response.json()
                cls.logger.debug('Register result: {}'.format(result))
                cls._check_result(result)
                device_id = result['id']
                cls.logger.debug('Got new device ID = {}'.format(device_id))
            return secret, device_id

    def __init__(self, session, secret, device_id):
        '''Init client with aiohttp session, secret and device id'''
        self.session = session
        self.secret = secret
        self.device_id = device_id
        self.lock = asyncio.Lock()

    @staticmethod
    def _check_result(result):
        if result.get('status', 0) != 1:
            raise PushoverException(str(result.get('errors', 'Unknown Error')))

    async def messages(self):
        '''Get message list'''
        async with self.session.get(self.API_ENDPOINT + '/messages.json',
                                    params={
                                        'secret': self.secret,
                                        'device_id': self.device_id,
                                    }) as response:
            result = await response.json()
            self.logger.debug('Got messages: {}'.format(result))
            self._check_result(result)
            return result['messages']

    async def update_highest_message(self, message_id):
        '''Update highest message to message_id'''
        url = '/devices/{}/update_highest_message.json'.format(self.device_id)
        async with self.session.post(self.API_ENDPOINT + url, data={
                                        'secret': self.secret,
                                        'message': message_id,
                                     }) as response:
            result = await response.json()
            self.logger.debug('Update result: {}'.format(result))
            self._check_result(result)
            self.logger.info('Highest message updated to {}'
                             .format(message_id))

    async def message_get_and_update(self, callback, max_retry=3):
        self.logger.info('Get and updating messages (Retry {})'
                         .format(max_retry))
        async with self.lock:
            try:
                messages = await self.messages()
            except:
                self.logger.exception('Error getting messages')
                if max_retry > 0:
                    asyncio.ensure_future(
                        self.message_get_and_update(callback, max_retry-1))
                return
            self.logger.info('Got {} messages'.format(len(messages)))
            for msg in messages:
                self.logger.info('Processing message {}'.format(msg['id']))
                callback(msg)
            if messages:
                await self.update_highest_message(max(map(lambda x: x['id'],
                                                          messages)))

    async def wss_init(self):
        self.logger.info('Connecting websocket')
        self.wss = await websockets.connect(self.WSS_ENDPOINT)
        await self.wss.send('login:{}:{}\n'
                            .format(self.device_id, self.secret))

    async def wss_wait(self):
        msg = await self.wss.recv()
        self.logger.debug('wss_wait: got {}'.format(repr(msg)))
        for msg_typ in self.PushMessage:
            if msg_typ.value == msg:
                break
        else:
            raise PushoverException('Unknown push message {}'.format(msg))
        self.logger.info('Got push message {}'.format(msg_typ))
        return msg_typ

    def wss_destroy(self):
        if self.wss is None:
            return
        self.logger.info('Destroying websocket')
        asyncio.ensure_future(self.wss.close())
        self.wss = None

    async def watch_loop(self, callback):
        while True:
            self.logger.info('Start watch loop')
            asyncio.ensure_future(self.message_get_and_update(callback))
            try:
                await asyncio.wait_for(self.wss_init(), self.KEEPALIVE_TIMEOUT)
                while True:
                    push_msg = await asyncio.wait_for(self.wss_wait(),
                                                      self.KEEPALIVE_TIMEOUT)
                    if push_msg is self.PushMessage.KEEPALIVE:
                        continue
                    elif push_msg is self.PushMessage.NEWMESSAGE:
                        asyncio.ensure_future(
                            self.message_get_and_update(callback))
                    else:
                        break
            except:
                self.logger.exception('Got exception while pulling')
                self.logger.info('Restarting websocket connection')
                await asyncio.sleep(self.RETRY_SLEEP)
                continue
            finally:
                self.wss_destroy()


if __name__ == '__main__':
    import sys

    logging.basicConfig(level=logging.DEBUG)

    secret = sys.argv[1]
    device_id = sys.argv[2]

    async def main(loop):
        async with aiohttp.ClientSession(loop=loop) as session:
            client = PulloverClient(session, secret, device_id)
            await client.watch_loop(lambda msg: print(msg))

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(loop))
