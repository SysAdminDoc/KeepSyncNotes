import unittest

from keepsync_note_text import (
    markdown_preview_blocks,
    markdown_preview_text,
    note_uses_markdown,
)


class MarkdownModeTests(unittest.TestCase):
    def test_md_label_enables_markdown_mode(self):
        self.assertTrue(note_uses_markdown(["project", ".md"]))
        self.assertTrue(note_uses_markdown([" .MD "]))
        self.assertFalse(note_uses_markdown(["markdown", "md"]))

    def test_markdown_blocks_strip_formatting_for_preview(self):
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
        preview = markdown_preview_text("## Title\n- [x] **Done**\n- [ ] Next", limit=80)

        self.assertEqual(preview, "Title [x] Done [ ] Next")


if __name__ == "__main__":
    unittest.main()
