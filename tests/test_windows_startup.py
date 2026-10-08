"""Exercise actual startup when the loop lacks Windows signal support."""
import asyncio
import json
from pathlib import Path
import signal
import socket
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import patch
from websockets.asyncio.client import connect
from server.main import main
from server.storage import Store


class WindowsStartupTests(unittest.IsolatedAsyncioTestCase):
    async def test_unsupported_loop_signals_still_start_and_save_on_shutdown(self):
        with tempfile.TemporaryDirectory() as temp, socket.socket() as listener:
            listener.bind(('127.0.0.1', 0))
            port = listener.getsockname()[1]
            listener.close()
            database = Path(temp)/'windows.sqlite3'
            args = SimpleNamespace(host='127.0.0.1', port=port, database=database)
            loop = asyncio.get_running_loop()
            with patch.object(loop, 'add_signal_handler', side_effect=NotImplementedError), patch('server.main.signal.signal') as handler:
                task = asyncio.create_task(main(args))
                try:
                    for _ in range(40):
                        if handler.call_count == 2:
                            break
                        await asyncio.sleep(.025)
                    self.assertEqual([call.args[0] for call in handler.call_args_list], [signal.SIGTERM, signal.SIGINT])
                    async with connect(f'ws://127.0.0.1:{port}', max_size=2**22) as ws:
                        await ws.send(json.dumps({'type':'auth', 'name':'WindowsExplorer', 'password':'test-password', 'register':True}))
                        welcome = json.loads(await asyncio.wait_for(ws.recv(), 3))
                        self.assertEqual(welcome['type'], 'welcome')
                        self.assertEqual(welcome['world']['meta']['name'], 'NEXUS')
                    handler.call_args_list[1].args[1](signal.SIGINT, None)
                    await asyncio.wait_for(task, 3)
                    store = Store(database)
                    try:
                        self.assertEqual(store.resume(welcome['token']), welcome['id'])
                        self.assertEqual(len(store.player(welcome['id'])['inventory']), 30)
                    finally:
                        store.close()
                finally:
                    if not task.done():
                        task.cancel()
                        try:
                            await task
                        except asyncio.CancelledError:
                            pass
