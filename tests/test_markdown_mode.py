import ast
import re
import unittest
from pathlib import Path
from typing import Any, Dict, List


def load_markdown_helpers():
    source_path = Path(__file__).resolve().parents[1] / "keepsync_notes.py"
    module = ast.parse(source_path.read_text(encoding="utf-8"))
    helper_names = {
        "is_markdown_label",
        "note_uses_markdown",
        "split_inline_markdown",
        "markdown_preview_blocks",
        "markdown_preview_text",
    }
    selected = [
        node
        for node in module.body
        if isinstance(node, ast.FunctionDef) and node.name in helper_names
    ]
    helper_module = ast.Module(body=selected, type_ignores=[])
    ast.fix_missing_locations(helper_module)
    namespace = {"Any": Any, "Dict": Dict, "List": List, "re": re}
    exec(compile(helper_module, str(source_path), "exec"), namespace)
    return namespace


class MarkdownModeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.helpers = load_markdown_helpers()

    def test_md_label_enables_markdown_mode(self):
        note_uses_markdown = self.helpers["note_uses_markdown"]

        self.assertTrue(note_uses_markdown(["project", ".md"]))
        self.assertTrue(note_uses_markdown([" .MD "]))
        self.assertFalse(note_uses_markdown(["markdown", "md"]))

    def test_markdown_blocks_strip_formatting_for_preview(self):
        markdown_preview_blocks = self.helpers["markdown_preview_blocks"]

        blocks = markdown_preview_blocks("# Heading\n\n- **bold** and `code`\n> _quote_")
        rendered = [
            "".join(segment["text"] for segment in block["segments"])
            for block in blocks
            if block["segments"]
        ]
        styles = [block["style"] for block in blocks if block["segments"]]

        self.assertEqual(rendered, ["Heading", "- bold and code", "quote"])
        self.assertEqual(styles, ["heading_1", "list_item", "quote"])

    def test_markdown_preview_text_uses_rendered_plain_text(self):
        markdown_preview_text = self.helpers["markdown_preview_text"]

        preview = markdown_preview_text("## Title\n- [x] **Done**\n- [ ] Next", limit=80)

        self.assertEqual(preview, "Title [x] Done [ ] Next")


if __name__ == "__main__":
    unittest.main()
