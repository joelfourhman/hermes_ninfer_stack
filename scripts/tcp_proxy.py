#!/usr/bin/env python3
"""Minimal credential-free TCP relay for Docker Desktop loopback publication."""

from __future__ import annotations

import argparse
import asyncio


async def copy_stream(reader: asyncio.StreamReader, writer: asyncio.StreamWriter) -> None:
    try:
        while data := await reader.read(64 * 1024):
            writer.write(data)
            await writer.drain()
        if writer.can_write_eof():
            writer.write_eof()
            await writer.drain()
    except (ConnectionError, asyncio.CancelledError):
        pass


async def relay(
    client_reader: asyncio.StreamReader,
    client_writer: asyncio.StreamWriter,
    target_host: str,
    target_port: int,
) -> None:
    try:
        target_reader, target_writer = await asyncio.open_connection(target_host, target_port)
    except (OSError, asyncio.TimeoutError):
        client_writer.close()
        await client_writer.wait_closed()
        return

    await asyncio.gather(
        copy_stream(client_reader, target_writer),
        copy_stream(target_reader, client_writer),
    )
    target_writer.close()
    client_writer.close()
    await asyncio.gather(
        target_writer.wait_closed(),
        client_writer.wait_closed(),
        return_exceptions=True,
    )


async def serve(listen_port: int, target_host: str, target_port: int) -> None:
    server = await asyncio.start_server(
        lambda reader, writer: relay(reader, writer, target_host, target_port),
        host="0.0.0.0",
        port=listen_port,
    )
    async with server:
        await server.serve_forever()


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--listen-port", type=int, default=8080)
    parser.add_argument("--target-host", required=True)
    parser.add_argument("--target-port", type=int, required=True)
    args = parser.parse_args()
    asyncio.run(serve(args.listen_port, args.target_host, args.target_port))


if __name__ == "__main__":
    main()
