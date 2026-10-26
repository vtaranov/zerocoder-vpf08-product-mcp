"""MCP SDK выполняет initialize, tools/list и tools/call по HTTP."""
import json
from contextlib import asynccontextmanager
from mcp import Client


class MCPConnection:
    def __init__(self, client):
        self.client = client
        self.names = set()

    async def tools(self):
        result = await self.client.list_tools()
        self.names = {tool.name for tool in result.tools}
        return [{'type': 'function', 'name': tool.name,
                 'description': tool.description or '', 'parameters': tool.input_schema,
                 'strict': False} for tool in result.tools]

    async def call(self, name, arguments):
        if name not in self.names or not isinstance(arguments, dict):
            return {'error': 'Неизвестный инструмент или некорректные аргументы'}
        result = await self.client.call_tool(name, arguments)
        if result.is_error:
            return {'error': '\n'.join(c.text for c in result.content if c.type == 'text')}
        if result.structured_content is not None:
            return result.structured_content
        parts = [c.text for c in result.content if c.type == 'text']
        if len(parts) == 1:
            try:
                return json.loads(parts[0])
            except json.JSONDecodeError:
                pass
        return {'text': '\n'.join(parts)}


@asynccontextmanager
async def connect(url):
    async with Client(url) as client:
        yield MCPConnection(client)
