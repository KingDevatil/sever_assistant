import sys
import threading
import time
import unittest
from unittest.mock import patch, MagicMock

from PyQt5.QtWidgets import QApplication, QTextEdit, QPushButton
from PyQt5.QtCore import QMutex, QPoint, Qt
from PyQt5.QtGui import QFont, QFontMetrics
app = QApplication.instance() or QApplication(sys.argv)

import main


class TestCommandManagerCopy(unittest.TestCase):
    def setUp(self):
        with patch.object(main.CommandManager, '__init__', lambda manager: None):
            self.manager = main.CommandManager()
        self.manager.commands = [
            {
                'name': '常用',
                'commands': [
                    {
                        'name': '发布服务',
                        'command': './deploy.sh',
                        'params': [{'name': 'env', 'prompt': '环境'}],
                        'linked_enabled': True,
                        'linked_command': {'category': '常用', 'name': '检查服务'},
                        'target_server': 'srvB',
                    },
                    {'name': '发布服务 - 副本', 'command': 'old copy'},
                ],
            }
        ]
        self.manager.save_commands = MagicMock()

    def test_copy_command_deep_copies_full_config_and_uses_unique_name(self):
        copied = self.manager.copy_command(0, 0)

        self.assertEqual(copied['name'], '发布服务 - 副本 2')
        self.assertEqual(copied['command'], './deploy.sh')
        self.assertEqual(copied['target_server'], 'srvB')
        self.assertEqual(copied['linked_command']['name'], '检查服务')
        self.assertIsNot(copied, self.manager.commands[0]['commands'][0])
        self.assertIsNot(
            copied['params'],
            self.manager.commands[0]['commands'][0]['params'],
        )
        self.assertIs(
            self.manager.commands[0]['commands'][1],
            copied,
        )
        self.manager.save_commands.assert_called_once()

    def test_copying_an_existing_copy_continues_the_same_number_sequence(self):
        copied = self.manager.copy_command(0, 1)

        self.assertEqual(copied['name'], '发布服务 - 副本 2')


class TestCommandButtonContextMenu(unittest.TestCase):
    def test_command_button_right_click_opens_menu_for_its_command(self):
        window = main.ServerAssistant()
        try:
            window.command_manager.commands = [
                {
                    'name': '常用',
                    'commands': [
                        {'name': '启动服务', 'command': './start.sh'},
                        {'name': '停止服务', 'command': './stop.sh'},
                    ],
                }
            ]
            with patch.object(window, 'show_command_button_context_menu') as show_menu:
                window.refresh_default_command_buttons()
                button = next(
                    candidate
                    for candidate in window.default_command_layout.parentWidget().findChildren(QPushButton)
                    if candidate.text() == '停止服务'
                )
                self.assertEqual(button.contextMenuPolicy(), Qt.CustomContextMenu)

                position = QPoint(5, 5)
                button.customContextMenuRequested.emit(position)

            show_menu.assert_called_once_with(button, position, 0, 1)
        finally:
            window.close()


class TestCommandDialogParamDeletion(unittest.TestCase):
    def test_clicked_param_row_disappears_immediately_and_order_stays_stable(self):
        command_manager = MagicMock()
        command_manager.commands = []
        dialog = main.CommandDialog(command_manager=command_manager)
        try:
            for name in ('参数A', '参数B', '参数C'):
                dialog.add_param(name, '')
            dialog.show()
            app.processEvents()

            deleted_widget = dialog.params[1][2]
            delete_button = next(
                button
                for button in deleted_widget.findChildren(QPushButton)
                if button.text() == '删除'
            )
            delete_button.click()

            self.assertFalse(deleted_widget.isVisible())
            self.assertIsNone(deleted_widget.parent())
            self.assertEqual(
                [param_edit.text() for param_edit, _, _ in dialog.params],
                ['参数A', '参数C'],
            )
            self.assertEqual(
                [
                    dialog.params_layout.itemAt(index).widget()
                    for index in range(dialog.params_layout.count())
                ],
                [entry[2] for entry in dialog.params],
            )
        finally:
            dialog.close()


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

    def test_preserves_one_space_after_native_shell_prompt(self):
        """原生提示符末尾空格需保留，使下一条命令显示为 `$ command`。"""
        text = self.sa.highlight_keywords('[user@host ~]$   ')

        self.assertTrue(text.endswith('$ '))

    def test_renders_ansi_green_without_leaking_escape_character(self):
        """ANSI 绿色应转成 HTML，而不是把 ESC 显示成方框"""
        text = self.sa.highlight_keywords('\x1b[32mready\x1b[0m')

        self.assertNotIn('\x1b', text)
        self.assertIn('<span style="color: #0dbc79">ready</span>', text)

    def test_supports_empty_and_zero_padded_sgr_parameters(self):
        """兼容截图中的 ESC[;32m 与 ESC[01;34m 写法"""
        green = self.sa.highlight_keywords('\x1b[;32mgreen\x1b[0m')
        blue_bold = self.sa.highlight_keywords('\x1b[01;34mblue\x1b[0m')

        self.assertIn('<span style="color: #0dbc79">green</span>', green)
        self.assertIn(
            '<span style="color: #2472c8; font-weight: bold">blue</span>',
            blue_bold,
        )

    def test_ansi_foreground_takes_priority_over_keyword_color(self):
        """服务端指定的终端颜色应优先于本地关键词高亮"""
        text = self.sa.highlight_keywords('\x1b[31mSUCCESS\x1b[0m')

        self.assertIn('<span style="color: #cd3131">SUCCESS</span>', text)
        self.assertNotIn('#4caf50', text)

    def test_handles_ansi_sequence_split_between_output_flushes(self):
        """SSH 分包截断 ANSI 序列时，不应泄漏半个控制序列"""
        first = self.sa.highlight_keywords('\x1b[')
        second = self.sa.highlight_keywords('32mready\x1b[0m')

        self.assertEqual(first, '')
        self.assertIn('<span style="color: #0dbc79">ready</span>', second)
        self.assertNotIn('\x1b', first + second)

    def test_escapes_server_text_before_inserting_html(self):
        """服务器返回的普通文本不能被 QTextEdit 当作 HTML 标签解析"""
        text = self.sa.highlight_keywords('<service>&value')

        self.assertIn('&lt;service&gt;&amp;value', text)
        self.assertNotIn('<service>', text)

    def test_append_output_preserves_ll_column_spacing_across_ansi_spans(self):
        """ll 输出经富文本和 ANSI 颜色渲染后，连续空格仍须逐个保留"""
        self.sa.server_output = QTextEdit()
        self.sa.output_mutex = QMutex()
        raw = '-rw-r--r--  1 enjoymi users    128 Jul 15 12:00 \x1b[01;34mapp.log\x1b[0m'

        self.sa.append_output(self.sa.highlight_keywords(raw))

        self.assertEqual(
            self.sa.server_output.toPlainText(),
            '-rw-r--r--  1 enjoymi users    128 Jul 15 12:00 app.log',
        )


class TestTerminalOutputWidget(unittest.TestCase):
    def test_uses_fixed_pitch_font_and_eight_column_tab_stops(self):
        """服务器输出区域应使用终端等宽字体和 8 列 Tab 宽度"""
        window = main.ServerAssistant()
        try:
            font = window.server_output.font()
            expected_tab_width = QFontMetrics(font).horizontalAdvance(' ') * 8

            self.assertTrue(font.fixedPitch())
            self.assertEqual(font.styleHint(), QFont.Monospace)
            self.assertAlmostEqual(
                window.server_output.tabStopDistance(),
                expected_tab_width,
            )
        finally:
            window.close()


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


class TestShellStatusFrameParser(unittest.TestCase):
    def test_extracts_split_status_frame_without_exposing_it(self):
        """状态帧即使跨 SSH 分包，也只能更新元数据，不能显示在终端窗口。"""
        parser = main.ShellStatusFrameParser('token-1')

        first_text, first_frames = parser.feed(
            'command output\r\n\x1b]777;SERVER_ASSISTANT;tok'
        )
        second_text, second_frames = parser.feed(
            'en-1;DONE;7;/workspace/game data\x07[user@host game data]$ '
        )

        self.assertEqual(first_text, 'command output\r\n')
        self.assertEqual(first_frames, [])
        self.assertEqual(second_text, '[user@host game data]$ ')
        self.assertEqual(
            second_frames,
            [{'kind': 'DONE', 'exit_status': 7, 'cwd': '/workspace/game data'}],
        )
        self.assertEqual(parser.text_after_last_frame, '[user@host game data]$ ')
        self.assertNotIn('SERVER_ASSISTANT', first_text + second_text)

    def test_leaves_unrelated_terminal_osc_for_the_ansi_formatter(self):
        """服务端已有的标题等 OSC 序列不能被状态帧解析器误吞。"""
        parser = main.ShellStatusFrameParser('token-1')

        text, frames = parser.feed('\x1b]0;remote title\x07hello')

        self.assertEqual(text, '\x1b]0;remote title\x07hello')
        self.assertEqual(frames, [])


class _TimedShell:
    def __init__(self, schedule):
        self.schedule = list(schedule)
        self.started_at = time.monotonic()
        self.sent = []
        self.closed = False
        self.eof_received = False

    def send(self, value):
        self.sent.append(value)

    def recv_ready(self):
        if not self.schedule:
            return False
        return time.monotonic() - self.started_at >= self.schedule[0][0]

    def recv(self, _size):
        if not self.recv_ready():
            return b''
        _delay, value = self.schedule.pop(0)
        return value.encode('utf-8')


class TestCommandRunnablePromptCompletion(unittest.TestCase):
    def test_waits_for_status_frame_across_long_silence_and_keeps_native_prompt(self):
        """超过旧版 0.5 秒静默阈值时，仍应等到真实提示符再结束。"""
        token = 'status-token'
        shell = _TimedShell([
            (0.00, '[user@host ~]$ slow\r\n'),
            (0.65, 'SLOW_DONE\r\n\x1b]777;SERVER_ASSISTANT;status-token;DONE;0;/srv/work\x07'),
            (0.68, '[user@host work]$ '),
        ])
        client = MagicMock()
        client.get_transport.return_value.is_active.return_value = True
        server_manager = MagicMock()
        server_manager.get_shell.return_value = shell
        server_manager.get_shell_status_token.return_value = token
        server_manager.get_shell_lock.return_value = threading.Lock()
        results = []
        directories = []
        runnable = main.CommandRunnable(
            client, 'slow', MagicMock(), 'srv1', server_manager, {'srv1': '/home'}, False
        )
        runnable.command_timeout = 2
        runnable.signals.result.connect(results.append)
        runnable.signals.current_dir_updated.connect(
            lambda server, cwd: directories.append((server, cwd))
        )

        started_at = time.monotonic()
        runnable.run()
        elapsed = time.monotonic() - started_at

        self.assertGreaterEqual(elapsed, 0.64)
        self.assertEqual(shell.sent, ['slow\n'])
        self.assertEqual(directories, [('srv1', '/srv/work')])
        self.assertEqual(len(results), 1)
        self.assertIn('SLOW_DONE', results[0])
        self.assertTrue(results[0].endswith('[user@host work]$ '))
        self.assertNotIn('SERVER_ASSISTANT', results[0])
        self.assertFalse(runnable.is_running)

    def test_stop_sends_ctrl_c_once_and_waits_for_prompt_frame(self):
        """停止持续命令只发送一次 Ctrl+C，并读取到恢复后的原生提示符。"""
        token = 'status-token'
        shell = _TimedShell([
            (0.00, '[user@host ~]$ tail -f app.log\r\nline 1\r\n'),
            (0.20, '^C\r\n\x1b]777;SERVER_ASSISTANT;status-token;DONE;130;/srv/log\x07'),
            (0.22, '[user@host log]$ '),
        ])
        client = MagicMock()
        client.get_transport.return_value.is_active.return_value = True
        server_manager = MagicMock()
        server_manager.get_shell.return_value = shell
        server_manager.get_shell_status_token.return_value = token
        server_manager.get_shell_lock.return_value = threading.Lock()
        partial_results = []
        runnable = main.CommandRunnable(
            client, 'tail -f app.log', MagicMock(), 'srv1', server_manager,
            {'srv1': '/srv'}, True,
        )
        runnable.command_timeout = 2
        runnable.signals.partial_result.connect(partial_results.append)

        worker = threading.Thread(target=runnable.run)
        worker.start()
        time.sleep(0.08)
        runnable.stop()
        runnable.stop()
        worker.join(2)
        app.processEvents()

        self.assertFalse(worker.is_alive())
        self.assertEqual(shell.sent.count('\x03'), 1)
        self.assertNotIn('pwd\n', shell.sent)
        rendered = ''.join(partial_results)
        self.assertIn('[user@host log]$ ', rendered)
        self.assertNotIn('SERVER_ASSISTANT', rendered)
        self.assertFalse(runnable.is_running)

    def test_prompt_aware_command_is_not_interrupted_by_legacy_time_limit(self):
        """交互 shell 应像 Xshell 一样等提示符，不能因旧 60 秒阈值强制中断。"""
        token = 'status-token'
        shell = _TimedShell([
            (0.00, '[user@host ~]$ slow-job\r\n'),
            (0.20, 'DONE\r\n\x1b]777;SERVER_ASSISTANT;status-token;DONE;0;/srv\x07'),
            (0.22, '[user@host srv]$ '),
        ])
        client = MagicMock()
        client.get_transport.return_value.is_active.return_value = True
        server_manager = MagicMock()
        server_manager.get_shell.return_value = shell
        server_manager.get_shell_status_token.return_value = token
        server_manager.get_shell_lock.return_value = threading.Lock()
        runnable = main.CommandRunnable(
            client, 'slow-job', MagicMock(), 'srv1', server_manager, {}, False
        )
        runnable.command_timeout = 0.05

        runnable.run()

        self.assertEqual(shell.sent, ['slow-job\n'])
        self.assertIsNone(runnable.stop_reason)


class TestShellPromptHook(unittest.TestCase):
    def test_hook_is_session_only_and_preserves_existing_prompt_callbacks(self):
        command = main.build_shell_prompt_hook_command('token-1')

        self.assertIn('PROMPT_COMMAND', command)
        self.assertIn('precmd_functions', command)
        self.assertIn('token-1', command)
        self.assertNotIn('.bashrc', command)
        self.assertNotIn('.zshrc', command)


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

    def test_stop_keeps_runnable_registered_until_worker_finishes(self):
        """发送 Ctrl+C 后仍需由原任务收完提示符，不能立即清空任务引用。"""
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            sa = main.ServerAssistant()
        runnable = MagicMock()
        runnable.is_running = True
        sa.current_runnable = runnable
        sa.stop_button = MagicMock()
        sa.command_log = MagicMock()

        sa.stop_current_command()

        runnable.stop.assert_called_once()
        self.assertIs(sa.current_runnable, runnable)
        sa.stop_button.setEnabled.assert_called_with(False)

    def test_tab_switch_does_not_detach_running_runnable(self):
        """切换页签不能让后台任务失去停止和完成回调管理。"""
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            sa = main.ServerAssistant()
        runnable = MagicMock()
        runnable.is_running = True
        runnable.server_name = 'srv1'
        sa.current_runnable = runnable
        sa.stop_button = MagicMock()
        sa.server_output = MagicMock()

        sa.on_server_tab_changed(-1)

        self.assertIs(sa.current_runnable, runnable)

    def test_disconnecting_other_server_keeps_running_runnable_registered(self):
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            sa = main.ServerAssistant()
        runnable = MagicMock()
        runnable.is_running = True
        runnable.server_name = 'srvA'
        sa.current_runnable = runnable
        sa.stop_button = MagicMock()
        sa.server_manager = MagicMock()
        sa.server_tabs = MagicMock()
        sa.server_tabs.count.return_value = 0
        sa.server_button_layouts = {}
        sa.current_dirs = {'srvA': '/a'}
        sa.command_log = MagicMock()

        with patch.object(sa, 'refresh_server_list'):
            sa.disconnect_server('srvB')

        self.assertIs(sa.current_runnable, runnable)
        runnable.stop.assert_not_called()


class TestManualCommandSubmission(unittest.TestCase):
    def test_manual_input_uses_the_same_busy_check_as_command_buttons(self):
        """手工回车不能绕过正在运行任务的串行化入口。"""
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            sa = main.ServerAssistant()
        sa.command_input = MagicMock()
        sa.command_input.text.return_value = 'echo hello'
        sa.server_tabs = MagicMock()
        sa.server_tabs.count.return_value = 1
        sa.server_tabs.currentIndex.return_value = 0
        sa.server_tabs.tabText.return_value = 'srv1'
        sa.server_list_widget = MagicMock()
        sa.server_manager = MagicMock()
        sa.server_manager.is_connected.return_value = True

        with patch.object(sa, '_execute_command_main') as execute_main, \
             patch.object(sa, '_execute_command_continue') as execute_continue:
            sa.on_command_input_return()

        execute_main.assert_called_once()
        execute_continue.assert_not_called()

    def test_replacement_waits_for_previous_finished_signal(self):
        """新指令应等待旧任务恢复提示符，而不是依赖固定 200ms 延时。"""
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            sa = main.ServerAssistant()
        callbacks = []
        previous = MagicMock()
        previous.is_running = True
        previous.stop_requested = False
        previous.signals.finished.connect.side_effect = callbacks.append
        sa.current_runnable = previous
        sa.server_manager = MagicMock()
        sa.server_manager.is_connection_alive.return_value = True
        sa.server_manager.get_connection.return_value = MagicMock()
        sa.command_log = MagicMock()
        sa.stop_button = MagicMock()
        command_info = {'name': 'next', 'command': 'echo next'}

        with patch.object(main.QMessageBox, 'question', return_value=main.QMessageBox.Yes), \
             patch.object(sa, '_execute_command_continue') as execute_continue, \
             patch.object(main.QTimer, 'singleShot') as single_shot:
            sa._execute_command_main('srv1', command_info)
            execute_continue.assert_not_called()
            single_shot.assert_not_called()
            self.assertEqual(len(callbacks), 1)

            callbacks[0]()

        previous.stop.assert_called_once()
        execute_continue.assert_called_once_with(command_info, 'srv1', None)

    def test_reconnecting_other_server_does_not_detach_running_command(self):
        """目标服务器重连时不能清掉原服务器任务引用并造成并发抢读。"""
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            sa = main.ServerAssistant()
        previous = MagicMock()
        previous.is_running = True
        previous.stop_requested = False
        previous.server_name = 'srvA'
        sa.current_runnable = previous
        sa.server_manager = MagicMock()
        sa.server_manager.is_connection_alive.return_value = False
        sa.server_manager.ensure_connection.return_value = True
        sa.server_manager.get_connection.return_value = MagicMock()
        sa.server_manager.get_shell_current_dir.return_value = '/home/b'
        sa.current_dirs = {'srvA': '/home/a'}
        sa.command_log = MagicMock()
        sa.stop_button = MagicMock()

        with patch.object(sa, 'refresh_server_list'), \
             patch.object(sa, 'remove_stop_button') as remove_stop, \
             patch.object(sa, '_execute_command_continue') as execute_continue, \
             patch.object(main.QMessageBox, 'question', return_value=main.QMessageBox.No):
            sa._execute_command_main(
                'srvB', {'name': 'target', 'command': 'echo target'}
            )

        remove_stop.assert_not_called()
        self.assertIs(sa.current_runnable, previous)
        execute_continue.assert_not_called()


class TestAsyncFileCompleter(unittest.TestCase):
    def test_file_listing_is_submitted_to_worker_instead_of_blocking_gui(self):
        """命令完成后的远端 ls 不能在 GUI 线程同步等待。"""
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            sa = main.ServerAssistant()
        sa.server_tabs = MagicMock()
        sa.server_tabs.count.return_value = 1
        sa.server_tabs.currentIndex.return_value = 0
        sa.server_tabs.tabText.return_value = 'srv1'
        sa.current_dirs = {'srv1': '/srv/work'}
        sa.server_manager = MagicMock()
        sa.server_manager.is_connected.return_value = True
        client = MagicMock()
        sa.server_manager.get_connection.return_value = client
        sa.command_completer_model = ['ls']
        sa.command_completer = MagicMock()
        sa._file_list_runnables = set()
        pool = MagicMock()

        with patch.object(main.QThreadPool, 'globalInstance', return_value=pool):
            sa.update_command_completer_with_files()

        pool.start.assert_called_once()
        client.exec_command.assert_not_called()

    def test_tab_path_completion_does_not_execute_remote_ls_on_gui_thread(self):
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            sa = main.ServerAssistant()
        sa.command_input = MagicMock()
        sa.command_input.text.return_value = 'cd /opt/ap'
        sa.command_input.completer.return_value = MagicMock()
        sa.server_tabs = MagicMock()
        sa.server_tabs.count.return_value = 1
        sa.server_tabs.currentIndex.return_value = 0
        sa.server_tabs.tabText.return_value = 'srv1'
        sa.current_dirs = {'srv1': '/srv/work'}
        sa.server_manager = MagicMock()
        sa.server_manager.is_connected.return_value = True
        client = MagicMock()
        sa.server_manager.get_connection.return_value = client
        sa.command_log = MagicMock()
        sa._file_list_runnables = set()
        pool = MagicMock()

        with patch.object(main.QThreadPool, 'globalInstance', return_value=pool):
            sa.on_tab_pressed()

        pool.start.assert_called_once()
        client.exec_command.assert_not_called()


class TestOutputShellContext(unittest.TestCase):
    def test_target_server_prompt_can_restore_to_original_server(self):
        """同一输出窗执行目标服务器后，下一条原服务器指令应接回原提示符。"""
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            sa = main.ServerAssistant()
        sa.server_output = QTextEdit()
        sa.server_output.setPlainText('[a@host ~]$ ')
        sa.output_mutex = QMutex()
        sa.output_shell_server = 'srvA'
        sa.server_manager = MagicMock()
        sa.server_manager.get_shell_prompt.side_effect = {
            'srvA': '[a@host ~]$ ',
            'srvB': '[b@host /opt]$ ',
        }.get

        sa.prepare_output_shell_context('srvB')
        after_target = sa.server_output.toPlainText()
        sa.prepare_output_shell_context('srvA')
        after_restore = sa.server_output.toPlainText()

        self.assertIn('\n[b@host /opt]$ ', after_target)
        self.assertTrue(after_restore.endswith('\n[a@host ~]$ '))


class TestOutputTabHistory(unittest.TestCase):
    def setUp(self):
        self.window = main.ServerAssistant()
        self.window.server_manager.servers = [
            {'name': 'srvA', 'host': 'a.example', 'port': 22, 'username': 'a'},
            {'name': 'srvB', 'host': 'b.example', 'port': 22, 'username': 'b'},
        ]
        self.window.add_server_tab('srvA')
        self.window.append_output('A_HISTORY', is_html=False)
        self.window.add_server_tab('srvB')
        self.window.append_output('B_HISTORY', is_html=False)

    def tearDown(self):
        self.window.close()

    def _switch_to(self, server_name):
        for index in range(self.window.server_tabs.count()):
            if self.window.server_tabs.tabText(index) == server_name:
                self.window.server_tabs.setCurrentIndex(index)
                app.processEvents()
                return
        self.fail(f'未找到页签 {server_name}')

    def test_switching_back_restores_each_tabs_output_history(self):
        self._switch_to('srvA')
        self.assertIn('A_HISTORY', self.window.server_output.toPlainText())
        self.assertNotIn('B_HISTORY', self.window.server_output.toPlainText())

        self._switch_to('srvB')
        self.assertIn('B_HISTORY', self.window.server_output.toPlainText())
        self.assertNotIn('A_HISTORY', self.window.server_output.toPlainText())

    def test_late_output_is_routed_to_originating_inactive_tab(self):
        self.window.append_output(
            'LATE_A',
            is_html=False,
            output_tab_key='srvA',
        )
        self.assertNotIn('LATE_A', self.window.server_output.toPlainText())

        self._switch_to('srvA')
        self.assertIn('LATE_A', self.window.server_output.toPlainText())


if __name__ == '__main__':
    unittest.main()
