import sys
import unittest
from unittest.mock import patch

from PyQt5.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

import main


class TestIsContinuousCommand(unittest.TestCase):
    def test_tail_f_returns_true(self):
        """tail -f 应被识别为持续输出命令"""
        self.assertTrue(main.is_continuous_command('tail -f /var/log/app.log'))

    def test_tailf_returns_true(self):
        """tailf 应被识别为持续输出命令"""
        self.assertTrue(main.is_continuous_command('tailf /var/log/syslog'))

    def test_watch_returns_true(self):
        """watch 应被识别为持续输出命令"""
        self.assertTrue(main.is_continuous_command('watch -n 1 ls'))

    def test_top_returns_true(self):
        """top 应被识别为持续输出命令"""
        self.assertTrue(main.is_continuous_command('top'))

    def test_htop_returns_true(self):
        """htop 应被识别为持续输出命令"""
        self.assertTrue(main.is_continuous_command('htop'))

    def test_journalctl_f_returns_true(self):
        """journalctl -f 应被识别为持续输出命令"""
        self.assertTrue(main.is_continuous_command('journalctl -f -u nginx'))

    def test_ls_returns_false(self):
        """普通命令 ls 不应被识别为持续输出命令"""
        self.assertFalse(main.is_continuous_command('ls -la'))

    def test_cd_returns_false(self):
        """普通命令 cd 不应被识别为持续输出命令"""
        self.assertFalse(main.is_continuous_command('cd /home'))

    def test_stop_returns_false(self):
        """stop 不应被误识别为持续命令（避免子串匹配 top）"""
        self.assertFalse(main.is_continuous_command('stop'))

    def test_case_insensitive(self):
        """大小写不敏感：TAIL -F 应被识别"""
        self.assertTrue(main.is_continuous_command('TAIL -F /var/log'))


class TestHighlightKeywords(unittest.TestCase):
    def setUp(self):
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            self.sa = main.ServerAssistant()

    def test_removes_carriage_return(self):
        """\\r 应被去除，避免渲染为空格"""
        text = self.sa.highlight_keywords('line1\r\nline2')
        self.assertNotIn('\r', text)

    def test_newline_replaced_with_br(self):
        """\\n 应被替换为 <br>"""
        text = self.sa.highlight_keywords('line1\nline2')
        self.assertIn('<br>', text)
        self.assertNotIn('\n', text)

    def test_strips_trailing_spaces(self):
        """末尾多余空格应被去除"""
        text = self.sa.highlight_keywords('hello   ')
        self.assertFalse(text.endswith(' '))


if __name__ == '__main__':
    unittest.main()
