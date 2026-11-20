"""Fake httpx client used to mock the Agnes upstream in tests."""

from __future__ import annotations

import inspect

import httpx


class FakeResponse:
    def __init__(self, json_data=None, status_code: int = 200, content: bytes = b"", headers=None):
        self._json = json_data
        self.status_code = status_code
        self.content = content
        self.headers = headers or {}

    @property
    def is_success(self) -> bool:
        return 200 <= self.status_code < 300

    @property
    def text(self) -> str:
        return str(self._json)

    def json(self):
        return self._json

    def raise_for_status(self):
        if not self.is_success:
            raise httpx.HTTPStatusError("error", request=None, response=None)  # type: ignore[arg-type]


class FakeAsyncClient:
    """Routes are ``{(method, url): handler}``; handlers take the JSON body or params."""

    routes: dict = {}

    def __init__(self, *args, **kwargs):
        pass

    async def __aenter__(self):
        return self

    async def __aexit__(self, *args):
        return False

    async def post(self, url, json=None, headers=None, params=None, data=None, files=None):
        handler = self.routes.get(("POST", url))
        if handler is None:
            raise AssertionError(f"unexpected POST {url}")
        kwargs = {}
        if data is not None:
            kwargs["data"] = data
        if files is not None:
            kwargs["files"] = files
        result = handler(json, **kwargs)
        if inspect.isawaitable(result):
            result = await result
        return result

    async def get(self, url, params=None, headers=None):
        handler = self.routes.get(("GET", url))
        if handler is None:
            raise AssertionError(f"unexpected GET {url}")
        result = handler(params)
        if inspect.isawaitable(result):
            result = await result
        return result
