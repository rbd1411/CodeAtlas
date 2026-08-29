from codeatlas.chunking import chunk_source


def test_python_chunking_preserves_symbols_and_lines():
    source = '''"""Module docs."""
import os

def greet(name: str) -> str:
    return f"Hello {name}"

class Greeter:
    prefix = "Hello"

    def greet(self, name: str) -> str:
        return f"{self.prefix} {name}"
'''
    chunks = chunk_source("greeter.py", "python", source, chunk_lines=40, overlap=4)
    symbols = {chunk.symbol for chunk in chunks}
    assert "greet" in symbols
    assert "Greeter" in symbols
    assert "Greeter.greet" in symbols
    method = next(chunk for chunk in chunks if chunk.symbol == "Greeter.greet")
    assert method.start_line == 10
    assert "self.prefix" in method.content


def test_markdown_chunking_uses_headings():
    chunks = chunk_source("README.md", "markdown", "# Start\nIntro\n\n## Run\nDo it")
    assert [chunk.symbol for chunk in chunks] == ["Start", "Run"]

