import sys
import unittest
from unittest.mock import patch, MagicMock, ANY

from PyQt5.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

import main


class TestExecuteCommandTargetServer(unittest.TestCase):
    def setUp(self):
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            self.sa = main.ServerAssistant()
        self.sa.command_manager = MagicMock()
        self.sa.command_log = MagicMock()
        self.sa.server_manager = MagicMock()

    def test_execute_command_with_target_server(self):
        """配置了 target_server 时，自动切换到目标服务器执行"""
        cmd = {'name': '指令A', 'command': 'echo A', 'target_server': 'srvB'}
        self.sa.server_manager.ensure_connection.return_value = True

        with patch.object(self.sa, '_execute_command_main') as mock_main, \
             patch.object(self.sa, '_ensure_server_ui_ready') as mock_ready:
            self.sa.execute_command('srv1', cmd)
            # ensure_connection 被调用以确认目标服务器已连接
            self.sa.server_manager.ensure_connection.assert_called_once_with('srvB')
            # _ensure_server_ui_ready 被调用以刷新 UI
            mock_ready.assert_called_once_with('srvB')
            # _execute_command_main 使用目标服务器名称
            mock_main.assert_called_once_with('srvB', cmd)

    def test_execute_command_target_server_auto_connect(self):
        """目标服务器未连接时，ensure_connection 被调用以自动连接"""
        cmd = {'name': '指令A', 'command': 'echo A', 'target_server': 'srvB'}
        self.sa.server_manager.ensure_connection.return_value = True

        with patch.object(self.sa, '_execute_command_main') as mock_main, \
             patch.object(self.sa, '_ensure_server_ui_ready') as mock_ready:
            self.sa.execute_command('srv1', cmd)
            self.sa.server_manager.ensure_connection.assert_called_once_with('srvB')
            mock_ready.assert_called_once_with('srvB')
            mock_main.assert_called_once_with('srvB', cmd)

    def test_execute_command_target_server_connect_failed(self):
        """目标服务器连接失败时，输出错误并终止执行"""
        cmd = {'name': '指令A', 'command': 'echo A', 'target_server': 'srvB'}
        self.sa.server_manager.ensure_connection.return_value = False

        with patch.object(self.sa, '_execute_command_main') as mock_main:
            self.sa.execute_command('srv1', cmd)
            self.sa.server_manager.ensure_connection.assert_called_once_with('srvB')
            # 应记录错误日志
            self.sa.command_log.append.assert_called_once()
            call_args = self.sa.command_log.append.call_args[0][0]
            self.assertIn('错误', call_args)
            self.assertIn('srvB', call_args)
            # 不执行指令
            mock_main.assert_not_called()

    def test_execute_command_from_linked_no_switch(self):
        """from_linked=True 时，不切换目标服务器（继承主指令解析后的服务器）"""
        cmd = {'name': '指令A', 'command': 'echo A', 'target_server': 'srvB'}
        self.sa.server_manager.ensure_connection.return_value = True

        with patch.object(self.sa, '_execute_command_main') as mock_main:
            self.sa.execute_command('srv1', cmd, from_linked=True)
            # 不应尝试连接目标服务器
            self.sa.server_manager.ensure_connection.assert_not_called()
            # 使用传入的 server_name，而非 target_server
            mock_main.assert_called_once_with('srv1', cmd)

    def test_execute_command_no_target_server(self):
        """未配置 target_server 时，保持原有逻辑"""
        cmd = {'name': '指令A', 'command': 'echo A'}

        with patch.object(self.sa, '_execute_command_main') as mock_main:
            self.sa.execute_command('srv1', cmd)
            self.sa.server_manager.ensure_connection.assert_not_called()
            mock_main.assert_called_once_with('srv1', cmd)


class TestExecuteDefaultCommandTargetServer(unittest.TestCase):
    def setUp(self):
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            self.sa = main.ServerAssistant()
        self.sa.command_manager = MagicMock()
        self.sa.command_log = MagicMock()
        self.sa.server_manager = MagicMock()

    def test_execute_default_command_with_target(self):
        """默认面板指令配置了 target_server 时，直接定向执行"""
        cmd = {'name': '指令A', 'command': 'echo A', 'target_server': 'srvB'}
        self.sa.server_manager.ensure_connection.return_value = True

        with patch.object(self.sa, 'execute_command') as mock_exec:
            self.sa.execute_default_command(cmd)
            self.sa.server_manager.ensure_connection.assert_called_once_with('srvB')
            mock_exec.assert_called_once_with('srvB', cmd)

    def test_execute_default_command_target_connect_failed(self):
        """默认面板指令目标服务器连接失败时，记录错误并返回"""
        cmd = {'name': '指令A', 'command': 'echo A', 'target_server': 'srvB'}
        self.sa.server_manager.ensure_connection.return_value = False

        with patch.object(self.sa, 'execute_command') as mock_exec:
            self.sa.execute_default_command(cmd)
            self.sa.server_manager.ensure_connection.assert_called_once_with('srvB')
            self.sa.command_log.append.assert_called_once()
            mock_exec.assert_not_called()

    def test_execute_default_command_no_target(self):
        """默认面板指令未配置 target_server 时，保持原有逻辑（使用当前页签服务器）"""
        cmd = {'name': '指令A', 'command': 'echo A'}
        self.sa.server_manager.servers = [{'name': 'srv1'}]
        self.sa.server_manager.is_connected.return_value = True
        self.sa.server_tabs = MagicMock()
        self.sa.server_tabs.currentIndex.return_value = 0
        self.sa.server_tabs.tabText.return_value = 'srv1'

        with patch.object(self.sa, 'execute_command') as mock_exec:
            self.sa.execute_default_command(cmd)
            # 不触发 target_server 相关逻辑
            self.sa.server_manager.ensure_connection.assert_not_called()
            # 原有逻辑：使用当前页签服务器执行
            mock_exec.assert_called_once_with('srv1', cmd)


class TestCommandDialogTargetServer(unittest.TestCase):
    def setUp(self):
        self.mock_cm = MagicMock()
        self.mock_cm.commands = [
            {'name': '分类1', 'commands': [{'name': '指令A', 'command': 'echo A'}]}
        ]
        self.mock_sm = MagicMock()
        self.mock_sm.servers = [
            {'name': 'srvA'},
            {'name': 'srvB'}
        ]
        self.dialog = main.CommandDialog(command_manager=self.mock_cm, server_manager=self.mock_sm)

    def test_get_command_info_no_target(self):
        """未选择目标服务器时，target_server 为 None"""
        self.dialog.name_edit.setText('测试指令')
        self.dialog.command_edit.setText('echo test')
        info = self.dialog.get_command_info()
        self.assertIsNone(info['target_server'])

    def test_get_command_info_with_target(self):
        """选择了目标服务器时，target_server 返回对应名称"""
        self.dialog.name_edit.setText('测试指令')
        self.dialog.command_edit.setText('echo test')
        # 索引 0 是 "当前服务器（默认）"，1 是 srvA，2 是 srvB
        self.dialog.target_server_combo.setCurrentIndex(2)
        info = self.dialog.get_command_info()
        self.assertEqual(info['target_server'], 'srvB')

    def test_restore_target_server(self):
        """编辑指令时，恢复已保存的 target_server"""
        cmd = {
            'name': '测试指令',
            'command': 'echo test',
            'params': [],
            'target_server': 'srvA'
        }
        dialog = main.CommandDialog(cmd, command_manager=self.mock_cm, server_manager=self.mock_sm)
        self.assertEqual(dialog.target_server_combo.currentData(), 'srvA')


class TestEnsureServerUiReady(unittest.TestCase):
    def setUp(self):
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            self.sa = main.ServerAssistant()
        self.sa.server_manager = MagicMock()
        self.sa.current_dirs = {}

    def test_refreshes_server_list(self):
        """自动连接后刷新左侧服务器列表"""
        with patch.object(self.sa, 'refresh_server_list') as mock_refresh, \
             patch.object(self.sa, 'add_server_tab'):
            self.sa._ensure_server_ui_ready('srvB')
            mock_refresh.assert_called_once()

    def test_adds_tab_without_switching(self):
        """为目标服务器创建页签，但不切换当前页签"""
        with patch.object(self.sa, 'refresh_server_list'), \
             patch.object(self.sa, 'add_server_tab') as mock_add:
            self.sa._ensure_server_ui_ready('srvB')
            mock_add.assert_called_once_with('srvB', switch=False)

    def test_initializes_current_dir(self):
        """自动连接后初始化目标服务器的当前目录"""
        client = MagicMock()
        stdout = MagicMock()
        stdout.read.return_value = b'/home/user\n'
        client.exec_command.return_value = (None, stdout, None)
        self.sa.server_manager.get_connection.return_value = client

        with patch.object(self.sa, 'refresh_server_list'), \
             patch.object(self.sa, 'add_server_tab'):
            self.sa._ensure_server_ui_ready('srvB')
            self.assertEqual(self.sa.current_dirs['srvB'], '/home/user')

    def test_does_not_override_existing_current_dir(self):
        """已存在 current_dirs 时不重复初始化"""
        self.sa.current_dirs['srvB'] = '/existing'
        with patch.object(self.sa, 'refresh_server_list'), \
             patch.object(self.sa, 'add_server_tab'), \
             patch.object(self.sa.server_manager, 'get_connection') as mock_get:
            self.sa._ensure_server_ui_ready('srvB')
            mock_get.assert_not_called()
            self.assertEqual(self.sa.current_dirs['srvB'], '/existing')

    def test_sets_default_dir_on_exception(self):
        """获取当前目录失败时默认设置为根目录"""
        self.sa.server_manager.get_connection.return_value = None
        with patch.object(self.sa, 'refresh_server_list'), \
             patch.object(self.sa, 'add_server_tab'):
            self.sa._ensure_server_ui_ready('srvB')
            self.assertEqual(self.sa.current_dirs['srvB'], '/')


if __name__ == '__main__':
    unittest.main()
