import asyncio

import aiohttp
import pytest

from parfive.utils import session_head_or_get


def deny_head(server, environ, start_response):
    if environ["REQUEST_METHOD"] != "GET":
        status = "405"
        response_headers = [("Content-type", "text/plain")]
        start_response(status, response_headers)
        return [b""]


def head_302(server, environ, start_response):
    if environ["REQUEST_METHOD"] != "GET":
        status = "302"
        response_headers = [("Content-type", "text/plain")]
        start_response(status, response_headers)
        return [b""]


@pytest.mark.asyncio
async def test_head_or_get(namedserver):
    url = namedserver.url
    async with aiohttp.ClientSession() as session:
        async with session_head_or_get(
            session,
            url,
        ) as resp:
            assert resp.ok
            assert resp.method == "HEAD"
            assert resp.status == 200

    namedserver.callback = deny_head

    async with aiohttp.ClientSession() as session:
        async with session_head_or_get(
            session,
            url,
        ) as resp:
            assert resp.ok
            assert resp.method == "GET"
            assert resp.status == 200


@pytest.mark.asyncio
async def test_head_302(namedserver):  # blame jsoc
    url = namedserver.url
    async with aiohttp.ClientSession() as session:
        async with session_head_or_get(
            session,
            url,
        ) as resp:
            assert resp.ok
            assert resp.method == "HEAD"
            assert resp.status == 200

    namedserver.callback = head_302

    async with aiohttp.ClientSession() as session:
        async with session_head_or_get(
            session,
            url,
        ) as resp:
            assert resp.ok
            assert resp.method == "GET"
            assert resp.status == 200


@pytest.mark.asyncio
async def test_head_disconnect_falls_back_to_get():
    # Some servers drop the connection on a HEAD request instead of answering it (#185)
    async def handle(reader, writer):
        request = await reader.readuntil(b"\r\n\r\n")
        if not request.startswith(b"HEAD"):
            writer.write(b"HTTP/1.1 200 OK\r\nContent-Length: 13\r\nConnection: close\r\n\r\nHello world!\n")
            await writer.drain()
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    url = f"http://127.0.0.1:{server.sockets[0].getsockname()[1]}/"
    async with server, aiohttp.ClientSession() as session:
        async with session_head_or_get(session, url) as resp:
            assert resp.method == "GET"
            assert await resp.read() == b"Hello world!\n"
