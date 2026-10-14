"""Owned Windows loop bootstrap for the exact pinned preset server.

Windows socketpair creates a loopback connection while creating the event loop.
Create that internal loop before the original server denies all socket.connect,
then serve on that same loop. No SDK/voice/inference implementation is changed.
"""
import argparse
import asyncio
import importlib.util
from pathlib import Path
import sys
import uvicorn

REPO=Path(__file__).resolve().parents[1]


def main():
    parser=argparse.ArgumentParser()
    parser.add_argument('--model',type=Path,required=True)
    parser.add_argument('--codec',type=Path,required=True)
    parser.add_argument('--sdk-source',type=Path,required=True)
    parser.add_argument('--cache',type=Path,required=True)
    parser.add_argument('--threads',type=int,choices=range(1,9),default=2)
    args=parser.parse_args()
    if sys.platform!='win32':raise RuntimeError('SPOKEN_WINDOWS_BOOTSTRAP_ONLY')
    # This loop's private socketpair is internal plumbing, before any model load.
    loop=asyncio.new_event_loop();asyncio.set_event_loop(loop)
    original=uvicorn.run
    def owned_run(app,*,host,port,access_log):
        if host!='127.0.0.1' or port!=18083 or access_log is not False:
            raise RuntimeError('SPOKEN_PINNED_LOCAL_BIND_REQUIRED')
        if asyncio.get_event_loop() is not loop or loop.is_running():
            raise RuntimeError('SPOKEN_EXACT_PRECREATED_LOOP_REQUIRED')
        config=uvicorn.Config(app,host=host,port=port,access_log=False,loop='asyncio',
            limit_max_requests=2,timeout_keep_alive=1)
        server=uvicorn.Server(config)
        # Server.serve never creates a Runner or another loop; use the one above.
        return loop.run_until_complete(server.serve())
    try:
        uvicorn.run=owned_run
        spec=importlib.util.spec_from_file_location('pinned_vieneu_local_server',REPO/'scripts/vieneu-local-server.py')
        module=importlib.util.module_from_spec(spec);sys.modules[spec.name]=module
        spec.loader.exec_module(module)
        module.run(args)
    finally:
        uvicorn.run=original
        loop.run_until_complete(loop.shutdown_asyncgens())
        loop.close();asyncio.set_event_loop(None)


if __name__=='__main__':
    main()
