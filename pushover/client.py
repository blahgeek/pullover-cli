#!/usr/bin/env python
# -*- coding: utf-8 -*-
# @Author: BlahGeek
# @Date:   2016-11-22
# @Last Modified by:   BlahGeek
# @Last Modified time: 2016-11-22


import enum
import logging
import aiohttp
import websockets


class PushoverException(Exception):
    pass


class PushoverClient:

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

    def __init__(self, session, secret, device_id):
        '''Init client with aiohttp session, secret and device id'''
        self.session = session
        self.secret = secret
        self.device_id = device_id

    def _check_result(self, result):
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

    async def message_get_and_update(self, callback):
        self.logger.info('Get and updating messages')
        messages = await self.messages()
        for msg in messages:
            self.logger.info('Processing message {}'.format(msg['id']))
            callback(msg)
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
        self.logger.info('Destroying websocket')
        asyncio.ensure_future(self.wss.close())
        self.wss = None

    async def watch_loop(self, callback):
        while True:
            try:
                await self.wss_init()
                while True:
                    push_msg = await self.wss_wait()
                    if push_msg is self.PushMessage.KEEPALIVE:
                        continue
                    if push_msg in (self.PushMessage.ERROR,
                                    self.PushMessage.RELOADREQUEST):
                        break
                    asyncio.ensure_future(
                        self.message_get_and_update(callback))
            except KeyboardInterrupt:
                self.logger.info('Got KeyboardInterrupt')
                break
            except:
                self.logger.exception('Got exception while pulling')
                self.logger.info('Restarting websocket connection')
                continue
            finally:
                self.wss_destroy()


if __name__ == '__main__':
    import sys
    import asyncio

    logging.basicConfig(level=logging.DEBUG)

    secret = sys.argv[1]
    device_id = sys.argv[2]

    async def main(loop):
        async with aiohttp.ClientSession(loop=loop) as session:
            client = PushoverClient(session, secret, device_id)
            await client.watch_loop(lambda msg: print(msg))

    loop = asyncio.get_event_loop()
    loop.run_until_complete(main(loop))
