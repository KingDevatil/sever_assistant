import sys
import unittest
from unittest.mock import patch, MagicMock

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


class TestPartialOutputBuffer(unittest.TestCase):
    def setUp(self):
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            self.sa = main.ServerAssistant()
        self.sa.partial_output_buffer = []
        self.sa.partial_output_buffer_chars = 0
        self.sa.partial_output_timer = MagicMock()
        self.sa.partial_output_timer.isActive.return_value = False
        self.sa.highlight_keywords = MagicMock(side_effect=lambda text: f'<b>{text}</b>')
        self.sa.append_output = MagicMock()

    def test_append_partial_output_batches_and_starts_timer(self):
        self.sa.append_partial_output('line1\n')
        self.assertEqual(self.sa.partial_output_buffer, ['line1\n'])
        self.assertEqual(self.sa.partial_output_buffer_chars, 6)
        self.sa.partial_output_timer.start.assert_called_once()

    def test_flush_partial_output_highlights_once(self):
        self.sa.partial_output_buffer = ['line1\n', 'line2\n']
        self.sa.partial_output_buffer_chars = len('line1\nline2\n')
        self.sa.flush_partial_output()
        self.sa.highlight_keywords.assert_called_once_with('line1\nline2\n')
        self.sa.append_output.assert_called_once_with('<b>line1\nline2\n</b>')
        self.assertEqual(self.sa.partial_output_buffer, [])
        self.assertEqual(self.sa.partial_output_buffer_chars, 0)

    def test_append_partial_output_flushes_large_buffer_immediately(self):
        text = 'x' * main.PARTIAL_OUTPUT_FLUSH_CHARS
        self.sa.append_partial_output(text)
        self.sa.highlight_keywords.assert_called_once_with(text)
        self.sa.append_output.assert_called_once_with(f'<b>{text}</b>')
        self.sa.partial_output_timer.start.assert_not_called()


class TestCommandRunnableConnectionHandling(unittest.TestCase):
    def test_recv_marks_runnable_stopped_when_transport_inactive(self):
        client = MagicMock()
        transport = MagicMock()
        transport.is_active.return_value = False
        client.get_transport.return_value = transport
        runnable = main.CommandRunnable(client, 'tail -f app.log', MagicMock(), 'srv1', MagicMock(), {}, True)
        runnable.shell = MagicMock()
        runnable.shell.closed = False
        runnable.shell.eof_received = False

        result = runnable.recv_with_timeout(0.01)

        self.assertEqual(result, '')
        self.assertFalse(runnable.is_running)
        self.assertEqual(runnable.stop_reason, 'shell_closed')


class TestServerAssistantRunnableStop(unittest.TestCase):
    def test_stop_runnable_for_server_stops_matching_running_runnable(self):
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            sa = main.ServerAssistant()
        runnable = MagicMock()
        runnable.server_name = 'srv1'
        runnable.is_running = True
        sa.current_runnable = runnable

        sa.stop_runnable_for_server('srv1')

        runnable.stop.assert_called_once()

    def test_stop_runnable_for_server_ignores_other_server(self):
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            sa = main.ServerAssistant()
        runnable = MagicMock()
        runnable.server_name = 'srv1'
        runnable.is_running = True
        sa.current_runnable = runnable

        sa.stop_runnable_for_server('srv2')

        runnable.stop.assert_not_called()

    def test_remove_stop_button_for_runnable_ignores_stale_runnable(self):
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            sa = main.ServerAssistant()
        stale_runnable = MagicMock()
        current_runnable = MagicMock()
        sa.current_runnable = current_runnable

        with patch.object(sa, 'remove_stop_button') as mock_remove:
            sa.remove_stop_button_for_runnable(stale_runnable)

        mock_remove.assert_not_called()
        self.assertIs(sa.current_runnable, current_runnable)


if __name__ == '__main__':
    unittest.main()
