"""Official MCP SDK. Rukan still decides which server may be called."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from typing import TypeVar

T = TypeVar("T")


def serve_acceptance(host: str = "127.0.0.1", port: int = 8766) -> None:
    """Deterministic ping server for local tests and the server campaign."""
    from mcp.server.fastmcp import FastMCP

    server = FastMCP(
        "rukan-acceptance",
        host=host,
        port=port,
        json_response=True,
        stateless_http=True,
        log_level="ERROR",
    )

    @server.tool()
    def ping() -> str:
        """Return a fixed token so a caller can see the tool ran."""
        return "pong"

    @server.tool()
    def add(a: int, b: int) -> int:
        """Add two integers."""
        return a + b

    @server.resource("status://project")
    def project_status() -> str:
        """Fixed project status resource."""
        return "ok"

    @server.prompt()
    def summarize_status() -> str:
        """Prompt the model to summarize project status."""
        return "Summarize the project status."

    server.run(transport="streamable-http")


def tool_names(url: str) -> list[str]:
    try:
        return list_tool_names(url)
    except Exception:
        return []


def describe_server(url: str) -> dict[str, object]:
    async def action() -> dict[str, object]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(url) as streams:
            read, write, _session_id = streams
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
                resources = await session.list_resources()
                prompts = await session.list_prompts()
                return {
                    "tools": [item.name for item in tools.tools],
                    "resources": [str(item.uri) for item in resources.resources],
                    "prompts": [item.name for item in prompts.prompts],
                }

    return _run(action)


def read_resource(url: str, uri: str) -> str:
    async def action() -> str:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(url) as streams:
            read, write, _session_id = streams
            async with ClientSession(read, write) as session:
                await session.initialize()
                from pydantic import AnyUrl

                result = await session.read_resource(AnyUrl(uri))
                texts: list[str] = []
                for block in result.contents:
                    text = getattr(block, "text", "")
                    if isinstance(text, str):
                        texts.append(text)
                return "".join(texts)

    return _run(action)


def get_prompt_text(url: str, name: str) -> str:
    async def action() -> str:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(url) as streams:
            read, write, _session_id = streams
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.get_prompt(name)
                texts: list[str] = []
                for message in result.messages:
                    content = getattr(message, "content", None)
                    text = getattr(content, "text", "")
                    if isinstance(text, str):
                        texts.append(text)
                return "\n".join(texts)

    return _run(action)


def list_tool_names(url: str) -> list[str]:
    async def action() -> list[str]:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(url) as streams:
            read, write, _session_id = streams
            async with ClientSession(read, write) as session:
                await session.initialize()
                listed = await session.list_tools()
                return [item.name for item in listed.tools]

    return _run(action)


def call_tool(url: str, name: str, arguments: dict[str, object]) -> str:
    async def action() -> str:
        from mcp import ClientSession
        from mcp.client.streamable_http import streamable_http_client

        async with streamable_http_client(url) as streams:
            read, write, _session_id = streams
            async with ClientSession(read, write) as session:
                await session.initialize()
                result = await session.call_tool(name, arguments)
                texts: list[str] = []
                for block in result.content:
                    text = getattr(block, "text", "")
                    if isinstance(text, str) and text:
                        texts.append(text)
                return "".join(texts)

    return _run(action)


def _run(action: Callable[[], Awaitable[T]]) -> T:
    import anyio

    return anyio.run(action)
