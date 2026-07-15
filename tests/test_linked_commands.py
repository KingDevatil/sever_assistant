import sys
import unittest
from unittest.mock import patch, MagicMock, ANY

from PyQt5.QtWidgets import QApplication
app = QApplication.instance() or QApplication(sys.argv)

import main


class TestFindLinkedCommand(unittest.TestCase):
    def setUp(self):
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            self.sa = main.ServerAssistant()
        self.sa.command_manager = MagicMock()

    def test_find_linked_command_valid(self):
        """正常查找：给定有效的 category 和 name，返回对应指令"""
        self.sa.command_manager.commands = [
            {
                "name": "分类1",
                "commands": [
                    {"name": "指令A", "command": "echo A"},
                    {"name": "指令B", "command": "echo B"}
                ]
            },
            {
                "name": "分类2",
                "commands": [
                    {"name": "指令C", "command": "echo C"}
                ]
            }
        ]
        result = self.sa.find_linked_command({"category": "分类1", "name": "指令B"})
        self.assertIsNotNone(result)
        self.assertEqual(result["name"], "指令B")
        self.assertEqual(result["command"], "echo B")

    def test_find_linked_command_none_input(self):
        """输入 None，返回 None"""
        self.sa.command_manager.commands = []
        result = self.sa.find_linked_command(None)
        self.assertIsNone(result)

    def test_find_linked_command_non_dict_input(self):
        """输入非 dict 类型，返回 None"""
        self.sa.command_manager.commands = []
        result = self.sa.find_linked_command("invalid")
        self.assertIsNone(result)

    def test_find_linked_command_missing_keys(self):
        """输入 dict 但缺少 category 或 name，返回 None"""
        self.sa.command_manager.commands = [
            {"name": "分类1", "commands": [{"name": "指令A", "command": "echo A"}]}
        ]
        self.assertIsNone(self.sa.find_linked_command({"category": "分类1"}))
        self.assertIsNone(self.sa.find_linked_command({"name": "指令A"}))

    def test_find_linked_command_not_found(self):
        """category 或 name 不存在，返回 None"""
        self.sa.command_manager.commands = [
            {"name": "分类1", "commands": [{"name": "指令A", "command": "echo A"}]}
        ]
        self.assertIsNone(self.sa.find_linked_command({"category": "不存在的分类", "name": "指令A"}))
        self.assertIsNone(self.sa.find_linked_command({"category": "分类1", "name": "不存在的指令"}))


class TestExecuteCommandLinked(unittest.TestCase):
    def setUp(self):
        with patch.object(main.ServerAssistant, '__init__', lambda x: None):
            self.sa = main.ServerAssistant()
        self.sa.command_manager = MagicMock()
        self.sa.command_log = MagicMock()

    def test_execute_command_no_linked(self):
        """linked_enabled=False 时，直接调用 _execute_command_main"""
        with patch.object(self.sa, '_execute_command_main') as mock_main:
            cmd = {'name': '指令A', 'command': 'echo A', 'linked_enabled': False}
            self.sa.execute_command('srv1', cmd)
            mock_main.assert_called_once_with('srv1', cmd)

    def test_execute_command_with_linked_valid(self):
        """主指令的延时必须从前置指令真正完成后开始计算。"""
        linked_cmd = {'name': '前置指令', 'command': 'echo pre'}
        main_cmd = {
            'name': '主指令', 'command': 'echo main',
            'linked_enabled': True,
            'linked_command': {'category': '分类1', 'name': '前置指令'},
            'linked_delay': 500
        }
        self.sa.command_manager.commands = [
            {'name': '分类1', 'commands': [linked_cmd]}
        ]

        with patch.object(self.sa, '_execute_command_main') as mock_main:
            with patch('main.QTimer.singleShot') as mock_timer:
                self.sa.execute_command('srv1', main_cmd)

                self.assertEqual(mock_main.call_count, 1)
                self.assertEqual(mock_main.call_args.args, ('srv1', linked_cmd))
                completion_callback = mock_main.call_args.kwargs['completion_callback']
                # 前置指令尚未完成时，不能提前启动延时计时器。
                mock_timer.assert_not_called()

                completion_callback()
                mock_timer.assert_called_once_with(500, ANY)
                callback = mock_timer.call_args[0][1]
                callback()
                mock_main.assert_called_with('srv1', main_cmd)
                self.assertEqual(mock_main.call_count, 2)

    def test_execute_command_linked_not_found(self):
        """linked_enabled=True 但关联指令不存在时，输出警告并直接执行自身"""
        main_cmd = {
            'name': '主指令', 'command': 'echo main',
            'linked_enabled': True,
            'linked_command': {'category': '不存在', 'name': '不存在'},
            'linked_delay': 0
        }
        self.sa.command_manager.commands = []

        with patch.object(self.sa, '_execute_command_main') as mock_main:
            self.sa.execute_command('srv1', main_cmd)
            # 应输出警告到 command_log
            self.sa.command_log.append.assert_called_once()
            call_args = self.sa.command_log.append.call_args[0][0]
            self.assertIn('警告', call_args)
            self.assertIn('未找到关联指令', call_args)
            # 直接执行自身指令
            mock_main.assert_called_once_with('srv1', main_cmd)

    def test_execute_command_from_linked_prevents_recursion(self):
        """from_linked=True 时，即使 linked_enabled=True 也不触发关联，防止递归"""
        linked_cmd = {
            'name': '前置指令', 'command': 'echo pre',
            'linked_enabled': True,
            'linked_command': {'category': '分类1', 'name': '主指令'},
            'linked_delay': 100
        }
        self.sa.command_manager.commands = [
            {'name': '分类1', 'commands': [linked_cmd]}
        ]

        with patch.object(self.sa, '_execute_command_main') as mock_main:
            with patch('main.QTimer.singleShot') as mock_timer:
                # 从关联指令入口调用，不应再次触发关联
                self.sa.execute_command('srv1', linked_cmd, from_linked=True)
                mock_main.assert_called_once_with('srv1', linked_cmd)
                mock_timer.assert_not_called()


class TestCommandDialogLinkedConfig(unittest.TestCase):
    def setUp(self):
        self.mock_cm = MagicMock()
        self.mock_cm.commands = [
            {
                'name': '分类1',
                'commands': [
                    {'name': '指令A', 'command': 'echo A'},
                    {'name': '指令B', 'command': 'echo B'}
                ]
            }
        ]
        self.dialog = main.CommandDialog(command_manager=self.mock_cm)

    def test_get_command_info_linked_disabled(self):
        """未启用关联指令时，get_command_info 返回 linked_enabled=False 和 linked_command=None"""
        self.dialog.enable_linked_checkbox.setChecked(False)
        self.dialog.name_edit.setText('测试指令')
        self.dialog.command_edit.setText('echo test')
        info = self.dialog.get_command_info()
        self.assertFalse(info['linked_enabled'])
        self.assertIsNone(info['linked_command'])
        self.assertEqual(info['linked_delay'], 0)

    def test_get_command_info_linked_enabled(self):
        """启用关联指令并选择指令、设置延迟后，get_command_info 返回正确配置"""
        self.dialog.enable_linked_checkbox.setChecked(True)
        # 索引 0 是 "请选择..."，1 是指令 A，2 是指令 B
        self.dialog.linked_command_combo.setCurrentIndex(2)
        self.dialog.linked_delay_spinbox.setValue(1500)
        self.dialog.name_edit.setText('测试指令')
        self.dialog.command_edit.setText('echo test')
        info = self.dialog.get_command_info()
        self.assertTrue(info['linked_enabled'])
        self.assertEqual(info['linked_command'], {'category': '分类1', 'name': '指令B'})
        self.assertEqual(info['linked_delay'], 1500)


if __name__ == '__main__':
    unittest.main()
