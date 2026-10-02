"""Formatting checks run on both Windows and Linux without a learner session."""
from pathlib import Path
import sys
import unittest

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))
from terminal_notes import display_width, render_markdown


SAMPLE = '''## tail — 看末尾

**命令名**：`tail` 是“尾部”。

| 参数 | 英文原词 | 作用说明 | 记忆联想 |
| --- | --- | --- | --- |
| `-f` | follow | 显示末尾后继续等待新内容 | Follow = 跟着日志走 |
| `-n 数字` | lines | 默认 10 行；可以指定行数 | 数多少行 |
'''


class TerminalNotesTest(unittest.TestCase):
    def test_wide_table_aligns_chinese_and_ascii(self):
        output = render_markdown(SAMPLE, 80)
        rows = [line for line in output.splitlines() if line.startswith(('│', '┌', '├', '└'))]
        self.assertTrue(rows)
        self.assertTrue(all(display_width(row) == 80 for row in rows))
        columns = []
        for row in rows:
            if row.startswith('│'):
                columns.append([display_width(row[:i]) for i, char in enumerate(row) if char == '│'])
        self.assertTrue(all(positions == columns[0] for positions in columns))
        for marker in ['**', '`', '| ---', '## ']:
            self.assertNotIn(marker, output)
        self.assertIn('follow', output)

    def test_narrow_screen_uses_labeled_entries(self):
        output = render_markdown(SAMPLE, 40)
        self.assertIn('参数：-f', output)
        self.assertIn('英文原词：follow', output)
        self.assertNotIn('│', output)
        self.assertTrue(all(display_width(line) <= 40 for line in output.splitlines()))

    def test_whole_notes_fit_supported_widths(self):
        text = (APP / 'notes.md').read_text(encoding='utf-8')
        for width in (40, 80, 100, 120):
            with self.subTest(width=width):
                output = render_markdown(text, width)
                self.assertTrue(all(display_width(line) <= width for line in output.splitlines()))
                self.assertNotIn('| ---', output)
                self.assertNotIn('**', output)

    def test_inline_symbols_links_and_combining_characters(self):
        self.assertEqual(display_width('文件'), 4)
        self.assertEqual(display_width('cafe\u0301'), 4)
        output = render_markdown('`*.txt` 与 `notes/`。**说明**：[帮助](https://example.org)', 80)
        self.assertIn('*.txt', output)
        self.assertIn('notes/', output)
        self.assertIn('https://example.org', output)
        self.assertNotIn('**', output)


if __name__ == '__main__':
    unittest.main()
