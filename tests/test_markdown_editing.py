import unittest

import keepsync_markdown_editing as editing
import keepsync_notes as app


class MarkdownEditingTests(unittest.TestCase):
    def test_inline_markdown_formats_selection(self):
        self.assertEqual(editing.format_markdown_selection("word", "bold"), "**word**")
        self.assertEqual(editing.format_markdown_selection("word", "italic"), "_word_")
        self.assertEqual(editing.format_markdown_selection("word", "code"), "`word`")
        self.assertEqual(editing.format_markdown_selection("Example", "link"), "[Example](url)")

    def test_task_formatting_prefixes_each_selected_line(self):
        self.assertEqual(
            editing.format_markdown_selection("First\nSecond", "task"),
            "- [ ] First\n- [ ] Second",
        )

    def test_empty_selection_uses_placeholders(self):
        self.assertEqual(editing.format_markdown_selection("", "bold"), "**bold text**")
        self.assertEqual(editing.format_markdown_selection("", "task"), "- [ ] Task item")

    def test_app_reexports_markdown_editing_helpers_for_compatibility(self):
        self.assertIs(app.format_markdown_selection, editing.format_markdown_selection)
        self.assertIs(app.MARKDOWN_PLACEHOLDERS, editing.MARKDOWN_PLACEHOLDERS)


if __name__ == "__main__":
    unittest.main()
