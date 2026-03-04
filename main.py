#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget, QVBoxLayout, QWidget, QSplitter, QPushButton, QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QDialog, QFormLayout, QLineEdit, QLabel, QComboBox, QMenu, QAction, QTextEdit, QFileDialog, QMessageBox, QGridLayout, QHBoxLayout, QSizePolicy
from PyQt5.QtCore import QStandardPaths
from PyQt5.QtCore import Qt, QSettings, QSize, QMimeData, QEvent, QMutex, QMutexLocker
from PyQt5.QtGui import QIcon, QFont, QColor, QDrag, QTextCursor
import paramiko
import json
import os
import time

# 自定义事件类
class CommandResultEvent(QEvent):
    EventType = QEvent.Type(QEvent.registerEventType())
    
    def __init__(self, output):
        super().__init__(self.EventType)
        self.output = output

class DraggableTreeWidget(QTreeWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent
        # 完全禁用拖拽功能
        self.setDragEnabled(False)
        self.setAcceptDrops(False)
        self.setDragDropMode(QTreeWidget.NoDragDrop)
        self.setSelectionMode(QTreeWidget.SingleSelection)
    
    def startDrag(self, supportedActions):
        # 完全禁用拖拽
        pass
    
    def dragEnterEvent(self, event):
        # 拒绝所有拖拽事件
        event.ignore()
    
    def dragMoveEvent(self, event):
        # 拒绝所有拖拽事件
        event.ignore()
    
    def dropEvent(self, event):
        # 拒绝所有放置事件
        event.ignore()

class ServerManager:
    def __init__(self):
        self.servers = []
        self.connections = {}
        self.shells = {}  # 存储持久的shell会话
        # 获取程序所在目录（支持PyInstaller打包）
        if hasattr(sys, '_MEIPASS'):
            # 当程序被PyInstaller打包时
            self.base_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            # 当程序在开发环境中运行时
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.load_servers()
    
    def load_servers(self):
        servers_file = os.path.join(self.base_dir, 'servers.json')
        if os.path.exists(servers_file):
            with open(servers_file, 'r', encoding='utf-8') as f:
                self.servers = json.load(f)
    
    def save_servers(self):
        servers_file = os.path.join(self.base_dir, 'servers.json')
        with open(servers_file, 'w', encoding='utf-8') as f:
            json.dump(self.servers, f, ensure_ascii=False, indent=2)
    
    def add_server(self, server_info):
        self.servers.append(server_info)
        self.save_servers()
    
    def remove_server(self, index):
        if index < len(self.servers):
            server_name = self.servers[index]['name']
            if server_name in self.connections:
                self.disconnect_server(server_name)
            del self.servers[index]
            self.save_servers()
    
    def update_server(self, index, server_info):
        if index < len(self.servers):
            old_name = self.servers[index]['name']
            self.servers[index] = server_info
            if old_name != server_info['name']:
                if old_name in self.connections:
                    conn = self.connections.pop(old_name)
                    self.connections[server_info['name']] = conn
            self.save_servers()
    
    def copy_server(self, index):
        if index < len(self.servers):
            server_info = self.servers[index].copy()
            base_name = server_info['name']
            count = 1
            new_name = f"{base_name}_{count}"
            while any(s['name'] == new_name for s in self.servers):
                count += 1
                new_name = f"{base_name}_{count}"
            server_info['name'] = new_name
            self.servers.insert(index + 1, server_info)
            self.save_servers()
            return new_name
    
    def connect_server(self, server_name):
        for server in self.servers:
            if server['name'] == server_name:
                try:
                    client = paramiko.SSHClient()
                    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                    client.connect(
                        server['host'],
                        port=server['port'],
                        username=server['username'],
                        password=server['password']
                    )
                    self.connections[server_name] = client
                    # 创建持久的shell会话
                    shell = client.invoke_shell()
                    self.shells[server_name] = shell
                    return True
                except Exception as e:
                    print(f"连接失败: {e}")
                    return False
        return False
    
    def disconnect_server(self, server_name):
        if server_name in self.connections:
            try:
                self.connections[server_name].close()
                del self.connections[server_name]
            except:
                pass
        if server_name in self.shells:
            try:
                self.shells[server_name].close()
                del self.shells[server_name]
            except:
                pass
    
    def get_shell(self, server_name):
        return self.shells.get(server_name)
    
    def is_connected(self, server_name):
        return server_name in self.connections
    
    def get_connection(self, server_name):
        return self.connections.get(server_name)

class CommandManager:
    def __init__(self):
        self.commands = []
        # 获取程序所在目录（支持PyInstaller打包）
        if hasattr(sys, '_MEIPASS'):
            # 当程序被PyInstaller打包时
            self.base_dir = os.path.dirname(os.path.abspath(sys.executable))
        else:
            # 当程序在开发环境中运行时
            self.base_dir = os.path.dirname(os.path.abspath(__file__))
        self.load_commands()
    
    def load_commands(self):
        commands_file = os.path.join(self.base_dir, 'commands.json')
        if os.path.exists(commands_file):
            with open(commands_file, 'r', encoding='utf-8') as f:
                self.commands = json.load(f)
    
    def save_commands(self):
        commands_file = os.path.join(self.base_dir, 'commands.json')
        with open(commands_file, 'w', encoding='utf-8') as f:
            json.dump(self.commands, f, ensure_ascii=False, indent=2)
    
    def add_category(self, category_name):
        if not any(c['name'] == category_name for c in self.commands):
            self.commands.append({
                'name': category_name,
                'commands': []
            })
            self.save_commands()
    
    def add_command(self, category_name, command_info):
        for category in self.commands:
            if category['name'] == category_name:
                category['commands'].append(command_info)
                self.save_commands()
                break
    
    def update_command(self, category_index, command_index, command_info):
        if category_index < len(self.commands):
            category = self.commands[category_index]
            if command_index < len(category['commands']):
                category['commands'][command_index] = command_info
                self.save_commands()
    
    def remove_command(self, category_index, command_index):
        if category_index < len(self.commands):
            category = self.commands[category_index]
            if command_index < len(category['commands']):
                del category['commands'][command_index]
                self.save_commands()
    
    def remove_category(self, category_index):
        if category_index < len(self.commands):
            del self.commands[category_index]
            self.save_commands()

class ServerDialog(QDialog):
    def __init__(self, server_info=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('编辑服务器' if server_info else '添加服务器')
        self.setGeometry(100, 100, 400, 200)
        # 确保对话框在父窗口中央弹出
        if parent:
            self.move(parent.frameGeometry().center() - self.frameGeometry().center())
        
        layout = QFormLayout()
        
        self.name_edit = QLineEdit()
        self.host_edit = QLineEdit()
        self.port_edit = QLineEdit()
        self.username_edit = QLineEdit()
        self.password_edit = QLineEdit()
        self.password_edit.setEchoMode(QLineEdit.Password)
        
        layout.addRow('服务器名称:', self.name_edit)
        layout.addRow('服务器地址:', self.host_edit)
        layout.addRow('端口:', self.port_edit)
        layout.addRow('用户名:', self.username_edit)
        layout.addRow('密码:', self.password_edit)
        
        if server_info:
            self.name_edit.setText(server_info['name'])
            self.host_edit.setText(server_info['host'])
            self.port_edit.setText(str(server_info['port']))
            self.username_edit.setText(server_info['username'])
            self.password_edit.setText(server_info['password'])
        else:
            self.port_edit.setText('22')
        
        button_box = QVBoxLayout()
        save_button = QPushButton('保存')
        cancel_button = QPushButton('取消')
        
        save_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        button_box.addWidget(save_button)
        button_box.addWidget(cancel_button)
        layout.addRow(button_box)
        
        self.setLayout(layout)
    
    def get_server_info(self):
        return {
            'name': self.name_edit.text(),
            'host': self.host_edit.text(),
            'port': int(self.port_edit.text()),
            'username': self.username_edit.text(),
            'password': self.password_edit.text()
        }

class CommandDialog(QDialog):
    def __init__(self, command_info=None, command_manager=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('编辑指令' if command_info else '添加指令')
        self.setGeometry(100, 100, 500, 300)
        # 确保对话框在父窗口中央弹出
        if parent:
            self.move(parent.frameGeometry().center() - self.frameGeometry().center())
        
        self.command_manager = command_manager
        
        layout = QVBoxLayout()
        
        form_layout = QFormLayout()
        
        # 分类选择
        self.category_combo = QComboBox()
        self.load_categories()
        
        self.name_edit = QLineEdit()
        self.command_edit = QLineEdit()
        
        form_layout.addRow('分类:', self.category_combo)
        form_layout.addRow('指令名称:', self.name_edit)
        form_layout.addRow('指令内容:', self.command_edit)
        
        layout.addLayout(form_layout)
        
        # 参数管理
        param_layout = QVBoxLayout()
        param_label = QLabel('参数管理')
        param_label.setFont(QFont('Arial', 10, QFont.Bold))
        param_layout.addWidget(param_label)
        
        self.params_layout = QVBoxLayout()
        self.params = []
        
        add_param_button = QPushButton('添加参数')
        add_param_button.clicked.connect(self.add_param)
        
        param_layout.addLayout(self.params_layout)
        param_layout.addWidget(add_param_button)
        
        layout.addLayout(param_layout)
        
        # 按钮
        button_box = QHBoxLayout()
        save_button = QPushButton('保存')
        cancel_button = QPushButton('取消')
        
        save_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        button_box.addWidget(save_button)
        button_box.addWidget(cancel_button)
        layout.addLayout(button_box)
        
        self.setLayout(layout)
        
        if command_info:
            self.name_edit.setText(command_info['name'])
            self.command_edit.setText(command_info['command'])
            # 加载参数
            if 'params' in command_info:
                params = command_info['params']
                # 确保params是列表
                if isinstance(params, list):
                    for param in params:
                        if isinstance(param, dict) and 'name' in param:
                            # 新格式，包含参数名称和提示
                            self.add_param(param['name'], param.get('hint', ''))
                        elif isinstance(param, str):
                            # 旧格式，只有参数名称
                            self.add_param(param, '')
                elif isinstance(params, bool):
                    # 兼容旧的has_param字段
                    pass
    
    def load_categories(self):
        # 加载分类列表
        if self.command_manager:
            for category in self.command_manager.commands:
                self.category_combo.addItem(category['name'])
    
    def add_param(self, param_name='', param_hint=''):
        param_widget = QWidget()
        param_hlayout = QHBoxLayout()
        
        param_edit = QLineEdit()
        # 确保param_name是字符串类型
        if isinstance(param_name, bool):
            param_name = ''
        param_edit.setText(param_name)
        param_edit.setPlaceholderText('参数名称')
        
        hint_edit = QLineEdit()
        hint_edit.setText(param_hint)
        hint_edit.setPlaceholderText('参数提示')
        
        delete_button = QPushButton('删除')
        delete_button.clicked.connect(lambda: self.delete_param(param_widget))
        
        param_hlayout.addWidget(param_edit)
        param_hlayout.addWidget(hint_edit)
        param_hlayout.addWidget(delete_button)
        param_widget.setLayout(param_hlayout)
        
        self.params_layout.addWidget(param_widget)
        self.params.append((param_edit, hint_edit))
    
    def delete_param(self, param_widget):
        index = self.params_layout.indexOf(param_widget)
        if index >= 0:
            widget = self.params_layout.takeAt(index).widget()
            if widget:
                widget.deleteLater()
            # 从params列表中移除
            for i, (param_edit, hint_edit) in enumerate(self.params):
                if param_edit.parent() == param_widget:
                    self.params.pop(i)
                    break
    
    def get_command_info(self):
        params = []
        for param_edit, hint_edit in self.params:
            param_name = param_edit.text()
            if param_name:
                params.append({
                    'name': param_name,
                    'hint': hint_edit.text()
                })
        return {
            'name': self.name_edit.text(),
            'command': self.command_edit.text(),
            'params': params
        }
    
    def get_category(self):
        return self.category_combo.currentText()

class ParamDialog(QDialog):
    def __init__(self, command_name, params, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f'输入{command_name}的参数')
        self.setGeometry(100, 100, 400, 200)
        # 确保对话框在父窗口中央弹出
        if parent:
            self.move(parent.frameGeometry().center() - self.frameGeometry().center())
        
        layout = QVBoxLayout()
        
        self.param_edits = []
        for param in params:
            param_layout = QFormLayout()
            param_edit = QLineEdit()
            if isinstance(param, dict) and 'name' in param:
                # 新格式，包含参数名称和提示
                param_name = param['name']
                param_hint = param.get('hint', '')
                if param_hint:
                    param_edit.setPlaceholderText(f'请输入{param_name} ({param_hint})')
                else:
                    param_edit.setPlaceholderText(f'请输入{param_name}')
                param_layout.addRow(f'{param_name}:', param_edit)
            elif isinstance(param, str):
                # 旧格式，只有参数名称
                param_edit.setPlaceholderText(f'请输入{param}')
                param_layout.addRow(f'{param}:', param_edit)
            # 将参数布局添加到主布局中
            layout.addLayout(param_layout)
            self.param_edits.append(param_edit)
        
        button_box = QHBoxLayout()
        ok_button = QPushButton('确定')
        cancel_button = QPushButton('取消')
        
        ok_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        button_box.addWidget(ok_button)
        button_box.addWidget(cancel_button)
        layout.addLayout(button_box)
        
        self.setLayout(layout)
    
    def get_params(self):
        return [edit.text() for edit in self.param_edits]

class ServerAssistant(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle('服务器后台指令快捷输入工具')
        
        self.server_manager = ServerManager()
        self.command_manager = CommandManager()
        self.server_button_layouts = {}  # 存储每个服务器页签的按钮布局
        self.test_mode = False  # 取消测试模式，始终使用实际服务器连接
        self.current_dirs = {}  # 存储每个服务器的当前目录
        self.settings_file = os.path.join(self.server_manager.base_dir, 'settings.json')
        
        # 布局参数默认值
        self.layout_params = {
            'category_spacing': 0,  # 分类之间的间距
            'title_button_spacing': -5,  # 标题与按钮之间的间距
            'button_spacing': 5,  # 按钮之间的间距
            'button_width': 150,  # 按钮宽度
            'button_height': 30,  # 按钮高度
            'category_font_size': 12,  # 分类标题字号
            'category_line_height': 0.5,  # 分类标题行高倍数
            'command_panel_height': 400,  # 指令面板高度
            'output_panel_height': 400,  # 输出面板高度
            'window_width': 1200,  # 程序窗口默认宽度
            'window_height': 800  # 程序窗口默认高度
        }
        
        self.dark_mode = False  # 默认浅色模式
        
        # 输出锁，确保多线程环境下输出顺序正确
        self.output_mutex = QMutex()
        
        # 加载保存的设置
        self.load_settings()
        
        # 调整窗口默认大小，确保能显示完整的6个指令按钮
        self.setGeometry(100, 100, self.layout_params['window_width'], self.layout_params['window_height'])
        
        self.init_ui()
    
    def append_output(self, text, is_html=True):
        with QMutexLocker(self.output_mutex):
            cursor = self.server_output.textCursor()
            cursor.movePosition(QTextCursor.End)
            self.server_output.setTextCursor(cursor)
            if is_html:
                self.server_output.insertHtml(text)
            else:
                self.server_output.insertPlainText(text)
            self.server_output.ensureCursorVisible()
    

    
    def highlight_keywords(self, text):
        # 关键字高亮功能
        # 根据当前模式选择颜色
        if self.dark_mode:
            # 深色模式下的颜色
            keywords = {
                'ERROR': '#ff5252',  # 亮红色
                'error': '#ff5252',  # 亮红色
                'Error': '#ff5252',  # 亮红色
                'WARN': '#ff9800',  # 亮橙色
                'warn': '#ff9800',  # 亮橙色
                'Warn': '#ff9800',  # 亮橙色
                'OK': '#4caf50',  # 亮绿色
                'ok': '#4caf50',  # 亮绿色
                'Ok': '#4caf50',  # 亮绿色
                'SUCCESS': '#4caf50',  # 亮绿色
                'success': '#4caf50',  # 亮绿色
                'Success': '#4caf50',  # 亮绿色
                'FAILED': '#ff5252',  # 亮红色
                'failed': '#ff5252',  # 亮红色
                'Failed': '#ff5252',  # 亮红色
            }
            ip_color = '#2196f3'  # 亮蓝色
        else:
            # 浅色模式下的颜色
            keywords = {
                'ERROR': '#e74c3c',  # 红色
                'error': '#e74c3c',  # 红色
                'Error': '#e74c3c',  # 红色
                'WARN': '#f39c12',  # 橙色
                'warn': '#f39c12',  # 橙色
                'Warn': '#f39c12',  # 橙色
                'OK': '#27ae60',  # 绿色
                'ok': '#27ae60',  # 绿色
                'Ok': '#27ae60',  # 绿色
                'SUCCESS': '#27ae60',  # 绿色
                'success': '#27ae60',  # 绿色
                'Success': '#27ae60',  # 绿色
                'FAILED': '#e74c3c',  # 红色
                'failed': '#e74c3c',  # 红色
                'Failed': '#e74c3c',  # 红色
            }
            ip_color = '#3498db'  # 蓝色
        
        # 高亮IP地址
        import re
        # IP地址正则表达式
        ip_pattern = r'\b(?:\d{1,3}\.){3}\d{1,3}\b'
        # 高亮IP地址
        replacement = '<span style="color: ' + ip_color + '">\\g<0></span>'
        text = re.sub(ip_pattern, replacement, text)
        
        # 高亮关键字
        for keyword, color in keywords.items():
            # 使用正则表达式进行全词匹配
            pattern = r'\b' + re.escape(keyword) + r'\b'
            text = re.sub(pattern, f'<span style="color: {color}">{keyword}</span>', text)
        
        # 确保文本在HTML中能够正确换行
        text = text.replace('\n', '<br>')
        
        return text
    
    def toggle_dark_mode(self, checked):
        # 切换深色模式
        self.dark_mode = checked
        
        # 只更新输出面板样式
        if self.dark_mode:
            # 深色模式样式 - 只应用到输出面板
            self.server_output.setStyleSheet('background-color: #1e1e1e; color: #ffffff; border: 1px solid #3d3d3d;')
            self.command_log.setStyleSheet('background-color: #1e1e1e; color: #ffffff; border: 1px solid #3d3d3d;')
        else:
            # 浅色模式样式
            self.server_output.setStyleSheet('background-color: white; color: black; border: 1px solid #d0d0d0;')
            self.command_log.setStyleSheet('background-color: white; color: black; border: 1px solid #d0d0d0;')
        
        # 保存设置
        self.save_settings()
    
    def load_settings(self):
        # 加载保存的设置
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    if 'layout_params' in settings:
                        self.layout_params.update(settings['layout_params'])
                    if 'dark_mode' in settings:
                        self.dark_mode = settings['dark_mode']
            except Exception as e:
                print(f"加载设置失败: {e}")
    
    def save_settings(self):
        # 保存设置到文件
        try:
            settings = {
                'layout_params': self.layout_params,
                'dark_mode': self.dark_mode
            }
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存设置失败: {e}")
    
    def init_ui(self):
        # 主布局
        central_widget = QWidget()
        main_layout = QVBoxLayout(central_widget)
        
        # 分割器
        splitter = QSplitter(Qt.Horizontal)
        
        # 左侧面板
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        
        # 左侧页签
        self.left_tab = QTabWidget()
        
        # 服务器列表
        self.server_list_widget = QListWidget()
        self.refresh_server_list()
        
        server_buttons = QVBoxLayout()
        add_server_button = QPushButton('添加服务器')
        delete_server_button = QPushButton('删除服务器')
        add_server_button.clicked.connect(self.add_server)
        delete_server_button.clicked.connect(self.delete_server)
        server_buttons.addWidget(add_server_button)
        server_buttons.addWidget(delete_server_button)
        
        server_widget = QWidget()
        server_layout = QVBoxLayout(server_widget)
        server_layout.addWidget(self.server_list_widget)
        server_layout.addLayout(server_buttons)
        
        # 指令管理
        self.command_tree = DraggableTreeWidget(self)
        self.command_tree.setHeaderLabels(['指令管理'])
        # 启用拖拽功能
        self.command_tree.setDragEnabled(True)
        self.command_tree.setAcceptDrops(True)
        self.command_tree.setDropIndicatorShown(True)
        self.command_tree.setSelectionMode(QTreeWidget.SingleSelection)
        self.command_tree.setDefaultDropAction(Qt.MoveAction)
        self.command_tree.setDragDropMode(QTreeWidget.InternalMove)
        self.refresh_command_tree()
        
        command_buttons = QVBoxLayout()
        add_category_button = QPushButton('添加分类')
        add_command_button = QPushButton('添加指令')
        add_category_button.clicked.connect(self.add_category)
        add_command_button.clicked.connect(self.add_command)
        command_buttons.addWidget(add_category_button)
        command_buttons.addWidget(add_command_button)
        
        command_widget = QWidget()
        command_layout = QVBoxLayout(command_widget)
        command_layout.addWidget(self.command_tree)
        command_layout.addLayout(command_buttons)
        
        self.left_tab.addTab(server_widget, '服务器列表')
        self.left_tab.addTab(command_widget, '指令管理')
        
        left_layout.addWidget(self.left_tab)
        
        # 右侧面板
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        
        # 服务器页签
        self.server_tabs = QTabWidget()
        # 设置固定高度为25
        self.server_tabs.setFixedHeight(25)
        
        # 指令按钮面板（默认显示，不需要连接服务器）
        self.default_command_panel = QWidget()
        self.default_command_layout = QVBoxLayout()
        # 设置顶对齐
        self.default_command_layout.setAlignment(Qt.AlignTop)
        self.default_command_panel.setLayout(self.default_command_layout)
        # 添加现代化样式，去除边框
        self.default_command_panel.setStyleSheet('''
            QWidget {
                background-color: white;
                padding: 10px;
            }
            QLabel {
                color: #333333;
                font-weight: bold;
                margin-bottom: 5px;
            }
            QPushButton {
                background-color: #ffffff;
                color: #333333;
                border: 1px solid #d9d9d9;
                border-radius: 6px;
                padding: 8px 12px;
                font-size: 13px;
            }
            QPushButton:hover {
                background-color: #f0f5ff;
                border-color: #1890ff;
                color: #1890ff;
            }
            QPushButton:pressed {
                background-color: #e6f7ff;
            }
        ''')
        
        # 刷新默认指令按钮
        self.refresh_default_command_buttons()
        
        # 输出面板 - 改为TabWidget
        self.output_tabs = QTabWidget()
        
        # 服务器返回信息页签
        self.server_output = QTextEdit()
        self.server_output.setReadOnly(True)
        self.server_output.setText('系统就绪，等待连接...')
        self.server_output.setStyleSheet('background-color: white; color: black;')
        # 设置为富文本模式，支持HTML格式
        self.server_output.setAcceptRichText(True)
        # 启用自动换行
        self.server_output.setLineWrapMode(QTextEdit.WidgetWidth)
        
        # 指令执行日志页签
        self.command_log = QTextEdit()
        self.command_log.setReadOnly(True)
        self.command_log.setText('指令执行日志:\n')
        self.command_log.setStyleSheet('background-color: white; color: black;')
        
        # 添加页签
        self.output_tabs.addTab(self.server_output, '服务器返回')
        self.output_tabs.addTab(self.command_log, '执行日志')
        
        # 使用QSplitter分割指令面板和输出面板
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.addWidget(self.default_command_panel)
        right_splitter.addWidget(self.output_tabs)
        # 设置默认大小比例
        right_splitter.setSizes([self.layout_params['command_panel_height'], self.layout_params['output_panel_height']])
        
        # 添加按钮布局
        self.button_layout = QHBoxLayout()
        # 设置布局左对齐
        self.button_layout.setAlignment(Qt.AlignLeft)
        # 左侧按钮：上传文件、下载文件、刷新输出
        self.upload_button = QPushButton('上传文件')
        self.download_button = QPushButton('下载文件')
        self.refresh_output_button = QPushButton('刷新输出')
        # 设置按钮宽度为150
        self.upload_button.setFixedWidth(150)
        self.download_button.setFixedWidth(150)
        self.refresh_output_button.setFixedWidth(150)
        self.upload_button.clicked.connect(self.upload_file_from_button)
        self.download_button.clicked.connect(self.download_file_from_button)
        self.refresh_output_button.clicked.connect(self.refresh_output_from_shell)
        self.button_layout.addWidget(self.upload_button)
        self.button_layout.addWidget(self.download_button)
        self.button_layout.addWidget(self.refresh_output_button)
        # 右侧按钮：停止命令
        self.stop_button_layout = QHBoxLayout()
        self.stop_button_layout.setAlignment(Qt.AlignRight)
        # 添加弹簧将停止按钮推到右侧
        self.button_layout.addStretch(1)
        self.button_layout.addLayout(self.stop_button_layout)
        
        right_layout.addWidget(self.server_tabs)
        right_layout.addWidget(right_splitter)
        right_layout.addLayout(self.button_layout)
        
        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        # 设置左侧面板宽度固定为300
        splitter.setSizes([300, 900])
        # 禁用左侧面板的大小调整
        splitter.setStretchFactor(0, 0)
        splitter.setStretchFactor(1, 1)
        
        main_layout.addWidget(splitter)
        
        # 菜单
        menubar = self.menuBar()
        file_menu = menubar.addMenu('文件')
        
        export_action = QAction('导出配置', self)
        import_action = QAction('导入配置', self)
        export_action.triggered.connect(self.export_config)
        import_action.triggered.connect(self.import_config)
        
        file_menu.addAction(export_action)
        file_menu.addAction(import_action)
        
        # 添加设置菜单
        settings_menu = menubar.addMenu('设置')
        layout_settings_action = QAction('布局设置', self)
        layout_settings_action.triggered.connect(self.show_layout_settings)
        settings_menu.addAction(layout_settings_action)
        
        # 添加深色模式切换选项
        self.dark_mode_action = QAction('深色模式', self)
        self.dark_mode_action.setCheckable(True)
        self.dark_mode_action.setChecked(self.dark_mode)
        self.dark_mode_action.triggered.connect(self.toggle_dark_mode)
        settings_menu.addAction(self.dark_mode_action)
        
        self.setCentralWidget(central_widget)
        
        # 应用深色模式设置
        if self.dark_mode:
            self.server_output.setStyleSheet('background-color: #1e1e1e; color: #ffffff; border: 1px solid #3d3d3d;')
            self.command_log.setStyleSheet('background-color: #1e1e1e; color: #ffffff; border: 1px solid #3d3d3d;')
        
        # 信号连接
        self.server_list_widget.itemClicked.connect(self.on_server_clicked)
        self.server_list_widget.setContextMenuPolicy(Qt.CustomContextMenu)
        self.server_list_widget.customContextMenuRequested.connect(self.show_server_context_menu)
        
        self.command_tree.itemDoubleClicked.connect(self.on_command_double_clicked)
        self.command_tree.setContextMenuPolicy(Qt.CustomContextMenu)
        self.command_tree.customContextMenuRequested.connect(self.show_command_context_menu)
        
        # 服务器标签切换信号连接
        self.server_tabs.currentChanged.connect(self.on_server_tab_changed)
    
    def refresh_server_list(self):
        self.server_list_widget.clear()
        for server in self.server_manager.servers:
            item = QListWidgetItem(server['name'])
            if self.server_manager.is_connected(server['name']):
                item.setForeground(QColor('green'))
                item.setText(f"{server['name']} (已连接)")
            else:
                item.setForeground(QColor('red'))
                item.setText(f"{server['name']} (断开)")
            self.server_list_widget.addItem(item)
    
    def refresh_command_tree(self):
        # 保存展开状态
        expanded_categories = set()
        for i in range(self.command_tree.topLevelItemCount()):
            item = self.command_tree.topLevelItem(i)
            if item.isExpanded():
                expanded_categories.add(item.text(0))
        
        # 清空并重新创建树
        self.command_tree.clear()
        for category in self.command_manager.commands:
            category_item = QTreeWidgetItem([category['name']])
            for command in category['commands']:
                command_item = QTreeWidgetItem([command['name']])
                category_item.addChild(command_item)
            self.command_tree.addTopLevelItem(category_item)
            # 恢复展开状态
            if category['name'] in expanded_categories:
                category_item.setExpanded(True)
    
    def add_server(self):
        dialog = ServerDialog(parent=self)
        if dialog.exec_():
            server_info = dialog.get_server_info()
            self.server_manager.add_server(server_info)
            self.refresh_server_list()
    
    def delete_server(self):
        current_row = self.server_list_widget.currentRow()
        if current_row >= 0:
            self.server_manager.remove_server(current_row)
            self.refresh_server_list()
            # 移除对应的服务器页签
            for i in range(self.server_tabs.count()):
                if self.server_tabs.tabText(i) == self.server_list_widget.item(current_row).text().split(' ')[0]:
                    self.server_tabs.removeTab(i)
                    break
    
    def show_server_context_menu(self, position):
        item = self.server_list_widget.itemAt(position)
        if item:
            menu = QMenu()
            connect_action = QAction('连接', self)
            disconnect_action = QAction('断开', self)
            edit_action = QAction('编辑', self)
            copy_action = QAction('复制', self)
            rename_action = QAction('重命名', self)
            delete_action = QAction('删除', self)
            
            connect_action.triggered.connect(lambda: self.connect_server(item.text().split(' ')[0]))
            disconnect_action.triggered.connect(lambda: self.disconnect_server(item.text().split(' ')[0]))
            edit_action.triggered.connect(lambda: self.edit_server(self.server_list_widget.row(item)))
            copy_action.triggered.connect(lambda: self.copy_server(self.server_list_widget.row(item)))
            rename_action.triggered.connect(lambda: self.rename_server(self.server_list_widget.row(item)))
            delete_action.triggered.connect(lambda: self.delete_server_by_name(item.text().split(' ')[0]))
            
            menu.addAction(connect_action)
            menu.addAction(disconnect_action)
            menu.addSeparator()
            menu.addAction(edit_action)
            menu.addAction(copy_action)
            menu.addAction(rename_action)
            menu.addSeparator()
            menu.addAction(delete_action)
            
            menu.exec_(self.server_list_widget.mapToGlobal(position))
    
    def connect_server(self, server_name):
        try:
            if self.server_manager.connect_server(server_name):
                # 连接服务器时自动关闭测试模式
                self.test_mode = False
                self.refresh_server_list()
                self.add_server_tab(server_name)
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 已连接到服务器: {server_name}")
                # 清空服务器输出窗口，不显示默认提示符
                self.server_output.clear()
                self.server_output.append('系统就绪，已连接到服务器')
                
                # 初始化当前目录
                client = self.server_manager.get_connection(server_name)
                if client:
                    stdin, stdout, stderr = client.exec_command('pwd')
                    current_dir = stdout.read().decode('utf-8').strip()
                    self.current_dirs[server_name] = current_dir
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 初始化当前目录: {current_dir}")
            else:
                QMessageBox.warning(self, '连接失败', f'无法连接到服务器: {server_name}')
        except Exception as e:
            QMessageBox.warning(self, '连接错误', f'连接服务器时发生错误: {e}')
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 连接服务器时发生错误: {e}")
    
    def disconnect_server(self, server_name):
        self.server_manager.disconnect_server(server_name)
        self.refresh_server_list()
        # 移除对应的服务器页签
        for i in range(self.server_tabs.count()):
            if self.server_tabs.tabText(i) == server_name:
                self.server_tabs.removeTab(i)
                break
        # 从布局字典中移除
        if server_name in self.server_button_layouts:
            del self.server_button_layouts[server_name]
        # 从当前目录字典中移除
        if server_name in self.current_dirs:
            del self.current_dirs[server_name]
        self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 已断开与服务器的连接: {server_name}")
    
    def edit_server(self, index):
        server_info = self.server_manager.servers[index]
        dialog = ServerDialog(server_info, parent=self)
        if dialog.exec_():
            new_server_info = dialog.get_server_info()
            self.server_manager.update_server(index, new_server_info)
            self.refresh_server_list()
    
    def copy_server(self, index):
        new_name = self.server_manager.copy_server(index)
        self.refresh_server_list()
        self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 已复制服务器: {new_name}")
    
    def rename_server(self, index):
        server_info = self.server_manager.servers[index].copy()
        dialog = ServerDialog(server_info, parent=self)
        if dialog.exec_():
            new_server_info = dialog.get_server_info()
            self.server_manager.update_server(index, new_server_info)
            self.refresh_server_list()
    
    def delete_server_by_name(self, server_name):
        for i, server in enumerate(self.server_manager.servers):
            if server['name'] == server_name:
                self.server_manager.remove_server(i)
                self.refresh_server_list()
                # 移除对应的服务器页签
                for j in range(self.server_tabs.count()):
                    if self.server_tabs.tabText(j) == server_name:
                        self.server_tabs.removeTab(j)
                        break
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 已删除服务器: {server_name}")
                break
    
    def refresh_output_from_shell(self):
        # 检查当前是否有选中的服务器页签
        current_tab_index = self.server_tabs.currentIndex()
        if current_tab_index >= 0:
            server_name = self.server_tabs.tabText(current_tab_index)
            shell = self.server_manager.get_shell(server_name)
            if shell:
                # 尝试读取shell中剩余的输出
                output = ""
                try:
                    while shell.recv_ready():
                        output += shell.recv(4096).decode('utf-8')
                    if output:
                        self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 刷新输出，读取到 {len(output)} 字符")
                        highlighted_text = self.highlight_keywords(output)
                        self.append_output(highlighted_text)
                except Exception as e:
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 刷新输出时出错: {e}")
            else:
                QMessageBox.information(self, '提示', '请先连接服务器')
        else:
            QMessageBox.information(self, '提示', '请先选择一个服务器页签')
    
    def add_server_tab(self, server_name):
        # 检查是否已存在该服务器的页签
        for i in range(self.server_tabs.count()):
            if self.server_tabs.tabText(i) == server_name:
                self.server_tabs.setCurrentIndex(i)
                return
        
        # 创建新的服务器页签
        tab_widget = QWidget()
        tab_layout = QVBoxLayout(tab_widget)
        
        # 指令按钮面板
        command_buttons_widget = QWidget()
        command_buttons_layout = QVBoxLayout()
        # 设置顶对齐
        command_buttons_layout.setAlignment(Qt.AlignTop)
        command_buttons_widget.setLayout(command_buttons_layout)
        # 设置大小策略
        command_buttons_widget.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)
        # 添加现代化样式，去除边框
        command_buttons_widget.setStyleSheet('''
            QWidget {
                background-color: white;
                padding: 10px;
            }
            QLabel {
                color: #333333;
                font-weight: bold;
                margin-bottom: 5px;
            }
            QPushButton {
                background-color: #f9f9f9;
                color: #333333;
                border: 1px solid #e0e0e0;
                border-radius: 4px;
                padding: 5px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #f0f0f0;
            }
            QPushButton:pressed {
                background-color: #e0e0e0;
            }
        ''')
        
        # 存储布局到字典
        self.server_button_layouts[server_name] = command_buttons_layout
        
        # 刷新按钮
        self.refresh_command_buttons(server_name)
        
        tab_layout.addWidget(command_buttons_widget)
        self.server_tabs.addTab(tab_widget, server_name)
    
    def refresh_command_buttons(self, server_name):
        # 获取对应服务器的布局
        if server_name not in self.server_button_layouts:
            return
        
        layout = self.server_button_layouts[server_name]
        
        # 清空现有按钮
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()
                else:
                    sub_layout = item.layout()
                    if sub_layout:
                        for j in reversed(range(sub_layout.count())):
                            sub_item = sub_layout.itemAt(j)
                            if sub_item:
                                sub_widget = sub_item.widget()
                                if sub_widget:
                                    sub_widget.deleteLater()
                        layout.removeItem(item)
        
        # 添加指令按钮
        self.add_command_buttons_to_layout(layout, server_name)
    
    def refresh_default_command_buttons(self):
        # 清空现有按钮
        for i in reversed(range(self.default_command_layout.count())):
            item = self.default_command_layout.itemAt(i)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()
                else:
                    sub_layout = item.layout()
                    if sub_layout:
                        for j in reversed(range(sub_layout.count())):
                            sub_item = sub_layout.itemAt(j)
                            if sub_item:
                                sub_widget = sub_item.widget()
                                if sub_widget:
                                    sub_widget.deleteLater()
                        self.default_command_layout.removeItem(item)
        
        # 添加指令按钮
        self.add_command_buttons_to_layout(self.default_command_layout, None)
    
    def add_command_buttons_to_layout(self, layout, server_name):
        # 清空现有内容
        for i in reversed(range(layout.count())):
            item = layout.itemAt(i)
            if item:
                widget = item.widget()
                if widget:
                    widget.deleteLater()
        
        # 创建一个主容器widget来容纳所有按钮
        main_container = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignTop)
        # 设置默认垂直间距为0，后续手动控制所有间距
        main_layout.setSpacing(0)
        # 去除布局的默认边距
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_container.setLayout(main_layout)
        
        # 添加指令按钮
        for i, category in enumerate(self.command_manager.commands):
            # 如果不是第一个分类，添加分类间距
            if i > 0:
                main_layout.addSpacing(self.layout_params['category_spacing'])
            
            category_label = QLabel(category['name'])
            # 使用布局参数中的字号
            category_label.setFont(QFont('Arial', self.layout_params['category_font_size'], QFont.Bold))
            # 设置分类标题的边距，根据行高倍数调整
            line_height = self.layout_params['category_line_height']
            category_label.setContentsMargins(0, 0, 0, 0)
            # 去除QLabel的默认边距
            category_label.setMargin(0)
            # 覆盖样式表中的margin-bottom设置
            category_label.setStyleSheet('margin-bottom: 0px;')
            main_layout.addWidget(category_label)
            
            # 在标题和按钮之间添加间距
            main_layout.addSpacing(self.layout_params['title_button_spacing'])
            
            # 创建网格布局，一行最多6个按钮
            grid_layout = QGridLayout()
            grid_layout.setContentsMargins(0, 0, 0, 0)
            grid_layout.setSpacing(self.layout_params['button_spacing'])
            # 设置左对齐
            grid_layout.setAlignment(Qt.AlignLeft)
            row = 0
            col = 0
            
            for command in category['commands']:
                button = QPushButton(command['name'])
                # 调整按钮大小
                button.setFixedWidth(self.layout_params['button_width'])
                button.setFixedHeight(self.layout_params['button_height'])
                if server_name:
                    button.clicked.connect(lambda checked, cmd=command, srv=server_name: self.execute_command(srv, cmd))
                else:
                    button.clicked.connect(lambda checked, cmd=command: self.execute_default_command(cmd))
                grid_layout.addWidget(button, row, col)
                
                col += 1
                if col >= 6:
                    col = 0
                    row += 1
            
            # 创建一个容器widget来容纳网格布局
            grid_widget = QWidget()
            grid_widget.setLayout(grid_layout)
            main_layout.addWidget(grid_widget)
        
        # 将主容器添加到布局中
        layout.addWidget(main_container)
    
    def execute_command(self, server_name, command_info):
        # 记录执行日志
        command = command_info['command']
        self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 执行命令: {command}")
        
        # 始终使用实际服务器连接
        client = self.server_manager.get_connection(server_name)
        if not client:
            QMessageBox.warning(self, '未连接', f'服务器 {server_name} 未连接')
            self.command_log.append(f"  错误: 服务器 {server_name} 未连接")
            return
        
        params = command_info.get('params', [])
        if params:
            dialog = ParamDialog(command_info['name'], params, parent=self)
            if dialog.exec_():
                param_values = dialog.get_params()
                # 替换命令中的参数占位符
                for i, param in enumerate(params):
                    if i < len(param_values):
                        param_value = param_values[i]
                        if isinstance(param, dict) and 'name' in param:
                            # 新格式，包含参数名称和提示
                            param_name = param['name']
                        else:
                            # 旧格式，只有参数名称
                            param_name = param
                        # 使用用户定义的参数名称作为占位符
                        command = command.replace(f'{{{param_name}}}', param_value)
                        self.command_log.append(f"  {param_name}: {param_value}")
            else:
                self.command_log.append("  用户取消执行")
                return
        
        try:
            if command.startswith('sz '):
                # 处理文件下载
                file_path = command[3:].strip()
                self.command_log.append(f"  开始下载文件: {file_path}")
                # 直接使用原始文件路径，不添加额外的/，保持与普通命令相同的处理方式
                self.download_file(server_name, file_path)
                self.command_log.append("  下载完成")
            elif command.startswith('rz '):
                # 处理文件上传
                self.command_log.append("  开始上传文件")
                self.upload_file(server_name)
                self.command_log.append("  上传完成")
            else:
                # 执行普通命令
                self.command_log.append(f"  连接服务器: {server_name}")
                # 使用线程池执行命令，避免阻塞UI线程
                from PyQt5.QtCore import QThreadPool, QRunnable
                
                from PyQt5.QtCore import pyqtSignal, QObject
                
                class CommandSignals(QObject):
                    result = pyqtSignal(str)
                    partial_result = pyqtSignal(str)
                    finished = pyqtSignal()
                    current_dir_updated = pyqtSignal(str, str)  # (server_name, current_dir)
                
                class CommandRunnable(QRunnable):
                    def __init__(self, client, command, command_log, server_name, server_manager, current_dirs):
                        super().__init__()
                        self.client = client
                        self.command = command
                        self.command_log = command_log
                        self.server_name = server_name
                        self.server_manager = server_manager
                        self.current_dirs = current_dirs
                        self.signals = CommandSignals()
                        self.is_running = True
                        self.shell = None
                        # 保存执行前的目录
                        self.saved_dir = current_dirs.get(server_name, "/")
                    
                    def stop(self):
                        self.is_running = False
                        if self.shell:
                            try:
                                # 发送中断信号
                                self.shell.send('\x03')  # Ctrl+C
                            except:
                                pass
                    
                    def run(self):
                        try:
                            self.command_log.append(f"  线程开始执行命令: {self.command}")
                            
                            # 检查是否是持续运行的命令
                            is_continuous_command = any(cmd in self.command for cmd in ['tailf', 'tail -f', 'top', 'watch'])
                            # 检查是否是以.sh结尾的文件，但不将其视为持续运行的命令
                            # 这样sh脚本会有足够的时间执行完成，同时也会在执行完成后自动停止
                            
                            # 获取持久的shell会话
                            self.shell = self.server_manager.get_shell(self.server_name)
                            
                            if self.shell:
                                self.command_log.append(f"  使用持久shell会话执行命令")
                                
                                # 暂时不获取执行前目录，避免延迟
                                current_dir_before = "/"
                                
                                # 执行命令
                                
                                # 执行命令
                                self.shell.send(self.command + '\n')
                                self.command_log.append(f"  命令发送到shell")
                                
                                if is_continuous_command:
                                    self.command_log.append(f"  检测到持续运行的命令，开始实时读取输出")
                                    # 持续读取输出
                                    output_buffer = ""
                                    start_time = time.time()
                                    
                                    # 发送初始命令信息
                                    self.signals.partial_result.emit(f"$ {self.command}\n")
                                    
                                    while self.is_running and (time.time() - start_time) < 300:  # 最多运行5分钟
                                        if self.shell.recv_ready():
                                            output = self.shell.recv(1024).decode('utf-8')
                                            output_buffer += output
                                            # 当输出包含换行符时，发送部分结果
                                            if '\n' in output_buffer:
                                                self.signals.partial_result.emit(output_buffer)
                                                output_buffer = ""
                                        time.sleep(0.1)  # 避免CPU占用过高
                                    
                                    if not self.is_running:
                                        self.command_log.append(f"  命令执行被用户停止")
                                        self.signals.partial_result.emit("\n命令已停止\n")
                                        # 发送 Ctrl+C 终止远程命令
                                        try:
                                            self.shell.send('\x03')
                                            time.sleep(0.1)
                                            self.command_log.append(f"  已发送 Ctrl+C 终止命令")
                                        except Exception as e:
                                            self.command_log.append(f"  发送终止信号失败：{e}")
                                    else:
                                        self.command_log.append(f"  命令执行超时（5 分钟）")
                                        self.signals.partial_result.emit("\n命令执行超时\n")
                                        # 超时后也要发送 Ctrl+C 终止远程命令
                                        try:
                                            self.shell.send('\x03')
                                            time.sleep(0.1)
                                            self.command_log.append(f"  已发送 Ctrl+C 终止命令")
                                        except Exception as e:
                                            self.command_log.append(f"  发送终止信号失败：{e}")
                                    
                                    # 持续命令执行后，也获取当前目录
                                    current_dir = self.saved_dir  # 默认使用保存的目录
                                    try:
                                        self.shell.send('pwd\n')
                                        # 多次尝试读取，确保获取到输出
                                        pwd_output = ""
                                        max_attempts = 5
                                        attempt = 0
                                        while attempt < max_attempts:
                                            time.sleep(0.05)
                                            if self.shell.recv_ready():
                                                pwd_output += self.shell.recv(4096).decode('utf-8')
                                                attempt = 0
                                            else:
                                                attempt += 1
                                        
                                        # 解析输出，获取目录
                                        lines = pwd_output.split('\n')
                                        found_dir = None
                                        for line in lines:
                                            stripped_line = line.strip()
                                            # 只要是/开头就行
                                            if stripped_line.startswith('/'):
                                                # 检查是否包含提示符，如果包含，截取到提示符之前
                                                prompt_chars = ['$', '#', '%', '>', ']']
                                                has_prompt = any(c in stripped_line for c in prompt_chars)
                                                if has_prompt:
                                                    # 找到第一个提示符的位置
                                                    min_pos = len(stripped_line)
                                                    for c in prompt_chars:
                                                        pos = stripped_line.find(c)
                                                        if pos != -1 and pos < min_pos:
                                                            min_pos = pos
                                                    if min_pos < len(stripped_line):
                                                        found_dir = stripped_line[:min_pos].strip()
                                                        break
                                                else:
                                                    found_dir = stripped_line
                                                    break
                                        
                                        # 只有找到有效目录且不是根目录时才使用新目录，否则使用保存的目录
                                        if found_dir and found_dir != "/":
                                            current_dir = found_dir
                                            self.command_log.append(f"  持续命令执行后当前目录: {current_dir}")
                                        else:
                                            self.command_log.append(f"  使用保存的目录: {current_dir}")
                                    except Exception as e:
                                        self.command_log.append(f"  获取当前目录失败，使用保存的目录: {e}")
                                    
                                    # 发送目录更新信号
                                    self.signals.current_dir_updated.emit(self.server_name, current_dir)
                                else:
                                    # 普通命令，等待执行完成
                                    # 大幅减少等待时间，快速获取输出
                                    output = ""
                                    max_attempts = 3
                                    attempt = 0
                                    
                                    while attempt < max_attempts:
                                        time.sleep(0.05)  # 每次等待0.05秒（比原来减少75%）
                                        new_output = ""
                                        while self.shell.recv_ready():
                                            new_output += self.shell.recv(4096).decode('utf-8')
                                        if new_output:
                                            output += new_output
                                            attempt = 0
                                        else:
                                            attempt += 1
                                    
                                    self.command_log.append(f"  读取shell输出完成，长度: {len(output)}")
                                    
                                    # 快速获取执行后当前目录（用于上传下载功能）
                                    current_dir = self.saved_dir  # 默认使用保存的目录
                                    try:
                                        self.shell.send('pwd\n')
                                        # 多次尝试读取，确保获取到输出
                                        pwd_output = ""
                                        max_attempts = 5
                                        attempt = 0
                                        while attempt < max_attempts:
                                            time.sleep(0.05)
                                            if self.shell.recv_ready():
                                                pwd_output += self.shell.recv(4096).decode('utf-8')
                                                attempt = 0
                                            else:
                                                attempt += 1
                                        
                                        # 解析输出，获取目录
                                        lines = pwd_output.split('\n')
                                        found_dir = None
                                        for line in lines:
                                            stripped_line = line.strip()
                                            # 只要是/开头就行
                                            if stripped_line.startswith('/'):
                                                # 检查是否包含提示符，如果包含，截取到提示符之前
                                                prompt_chars = ['$', '#', '%', '>', ']']
                                                has_prompt = any(c in stripped_line for c in prompt_chars)
                                                if has_prompt:
                                                    # 找到第一个提示符的位置
                                                    min_pos = len(stripped_line)
                                                    for c in prompt_chars:
                                                        pos = stripped_line.find(c)
                                                        if pos != -1 and pos < min_pos:
                                                            min_pos = pos
                                                    if min_pos < len(stripped_line):
                                                        found_dir = stripped_line[:min_pos].strip()
                                                        break
                                                else:
                                                    found_dir = stripped_line
                                                    break
                                        
                                        # 只有找到有效目录且不是根目录时才使用新目录，否则使用保存的目录
                                        if found_dir and found_dir != "/":
                                            current_dir = found_dir
                                            self.command_log.append(f"  执行后当前目录: {current_dir}")
                                        else:
                                            self.command_log.append(f"  使用保存的目录: {current_dir}")
                                    except Exception as e:
                                        self.command_log.append(f"  获取当前目录失败，使用保存的目录: {e}")
                                    
                                    # 发送目录更新信号
                                    self.signals.current_dir_updated.emit(self.server_name, current_dir)
                                    
                                    # 构建完整的输出，只包括命令和输出结果
                                    full_output = f"$ {self.command}\n{output}"
                                    self.command_log.append(f"  构建完整输出完成")
                                    
                                    # 发送信号到主线程
                                    self.signals.result.emit(full_output)
                            else:
                                self.command_log.append(f"  没有持久shell会话，使用普通命令执行")
                                # 执行命令
                                stdin, stdout, stderr = self.client.exec_command(self.command, timeout=10)
                                self.command_log.append(f"  命令执行中...")
                                
                                try:
                                    output = stdout.read().decode('utf-8') + stderr.read().decode('utf-8')
                                    self.command_log.append(f"  命令执行完成，输出长度: {len(output)}")
                                except paramiko.ssh_exception.SSHException as e:
                                    if "timed out" in str(e):
                                        output = "命令执行超时（可能是持续运行的命令，如tailf）"
                                        self.command_log.append(f"  命令执行超时: {e}")
                                    else:
                                        raise
                                
                                # 快速获取新的当前目录（用于上传下载功能）
                                current_dir = self.saved_dir  # 默认使用保存的目录
                                try:
                                    stdin_pwd, stdout_pwd, stderr_pwd = self.client.exec_command('pwd', timeout=2)
                                    found_dir = stdout_pwd.read().decode('utf-8').strip()
                                    # 只有找到有效目录且不是根目录时才使用新目录，否则使用保存的目录
                                    if found_dir and found_dir != "/":
                                        current_dir = found_dir
                                        self.command_log.append(f"  当前目录: {current_dir}")
                                    else:
                                        self.command_log.append(f"  使用保存的目录: {current_dir}")
                                    # 发送目录更新信号
                                    self.signals.current_dir_updated.emit(self.server_name, current_dir)
                                except Exception as e:
                                    self.command_log.append(f"  获取当前目录失败，使用保存的目录: {e}")
                                    # 发送目录更新信号
                                    self.signals.current_dir_updated.emit(self.server_name, current_dir)
                                
                                # 构建完整的输出
                                full_output = f"$ {self.command}\n{output}"
                                self.command_log.append(f"  构建完整输出完成")
                                
                                # 发送信号到主线程
                                self.signals.result.emit(full_output)
                            
                            self.command_log.append(f"  命令执行完成")
                            self.signals.finished.emit()
                        except Exception as e:
                            error_msg = f"错误: {e}"
                            self.command_log.append(f"  执行命令时出错: {e}")
                            self.signals.result.emit(error_msg)
                            self.signals.finished.emit()
                
                # 提交任务到线程池
                self.command_log.append(f"  提交命令到线程池: {command}")
                runnable = CommandRunnable(client, command, self.command_log, server_name, self.server_manager, self.current_dirs)
                
                # 保存当前运行的任务，以便可以停止它
                self.current_runnable = runnable
                
                # 检查是否是持续运行的命令
                is_continuous_command = any(cmd in command for cmd in ['tailf', 'tail -f', 'top', 'watch'])
                
                if is_continuous_command:
                    # 为持续运行的命令添加停止按钮
                    self.stop_button = QPushButton('停止命令')
                    self.stop_button.clicked.connect(lambda: runnable.stop())
                    # 将停止按钮添加到输出框下方的布局中
                    self.stop_button_layout.addWidget(self.stop_button)
                
                # 连接信号
                def on_command_result(result):
                    self.command_log.append(f"  收到命令执行结果")
                    highlighted_text = self.highlight_keywords(result)
                    self.append_output(highlighted_text)
                    self.command_log.append("  执行完成")
                    # 移除停止按钮
                    if is_continuous_command and hasattr(self, 'stop_button'):
                        self.stop_button_layout.removeWidget(self.stop_button)
                        self.stop_button.deleteLater()
                        delattr(self, 'stop_button')
                
                def on_partial_result(partial):
                    highlighted_text = self.highlight_keywords(partial)
                    self.append_output(highlighted_text)
                
                def on_finished():
                    self.command_log.append("  命令执行完成")
                    # 移除停止按钮
                    if is_continuous_command and hasattr(self, 'stop_button'):
                        self.stop_button_layout.removeWidget(self.stop_button)
                        self.stop_button.deleteLater()
                        delattr(self, 'stop_button')
                
                def on_current_dir_updated(server_name, current_dir):
                    # 保存当前目录
                    self.current_dirs[server_name] = current_dir
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 更新当前目录: {current_dir}")
                
                runnable.signals.result.connect(on_command_result)
                runnable.signals.partial_result.connect(on_partial_result)
                runnable.signals.finished.connect(on_finished)
                runnable.signals.current_dir_updated.connect(on_current_dir_updated)
                
                QThreadPool.globalInstance().start(runnable)
                self.command_log.append(f"  线程池任务已启动")
                

        except Exception as e:
            error_msg = f"错误: {e}"
            self.server_output.append(error_msg)
            self.command_log.append(f"  {error_msg}")
    
    def execute_default_command(self, command_info):
        # 获取已连接的服务器列表
        connected_servers = [server['name'] for server in self.server_manager.servers if self.server_manager.is_connected(server['name'])]
        
        if not connected_servers:
            QMessageBox.warning(self, '未连接服务器', '请先连接至少一个服务器')
            return
        
        # 检查当前是否有选中的服务器页签
        current_tab_index = self.server_tabs.currentIndex()
        if current_tab_index >= 0:
            # 获取当前页签的服务器名称
            server_name = self.server_tabs.tabText(current_tab_index)
            # 执行命令
            self.execute_command(server_name, command_info)
        else:
            # 如果没有选中的页签，让用户选择一个服务器
            from PyQt5.QtWidgets import QInputDialog
            server_name, ok = QInputDialog.getItem(self, '选择服务器', '请选择要执行命令的服务器:', connected_servers, 0, False)
            
            if ok and server_name:
                self.execute_command(server_name, command_info)
    
    def download_file(self, server_name, file_path):
        client = self.server_manager.get_connection(server_name)
        if not client:
            self.append_output("无法获取服务器连接<br>")
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 下载文件失败: 无法获取服务器连接")
            return
        
        try:
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 开始下载文件: {file_path}")
            self.append_output(f"开始下载文件: {file_path}<br>")
            
            sftp = client.open_sftp()
            
            try:
                sftp.stat(file_path)
                self.append_output(f"文件存在: {file_path}<br>")
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 文件存在: {file_path}")
            except Exception as stat_error:
                error_msg = f"文件不存在: {file_path} ({stat_error})"
                self.append_output(f"{error_msg}<br>")
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {error_msg}")
                sftp.close()
                return
            
            from PyQt5.QtWidgets import QFileDialog
            file_name = os.path.basename(file_path)
            local_path, _ = QFileDialog.getSaveFileName(
                self, "保存文件", os.path.join(os.getcwd(), file_name), "All Files (*)"
            )
            
            if local_path:
                self.append_output(f"保存到: {local_path}<br>")
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 保存到: {local_path}")
                
                try:
                    sftp.get(file_path, local_path)
                    success_msg = f"文件已保存到: {local_path}"
                    self.append_output(f"{success_msg}<br>")
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {success_msg}")
                except Exception as download_error:
                    error_msg = f"下载失败: {download_error}"
                    self.append_output(f"{error_msg}<br>")
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {error_msg}")
            else:
                cancel_msg = "文件保存已取消"
                self.append_output(f"{cancel_msg}<br>")
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {cancel_msg}")
            sftp.close()
        except Exception as e:
            error_msg = f"下载过程出错: {e}"
            self.append_output(f"{error_msg}<br>")
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {error_msg}")
    
    def download_file_from_button(self):
        # 获取已连接的服务器列表
        connected_servers = [server['name'] for server in self.server_manager.servers if self.server_manager.is_connected(server['name'])]
        
        if not connected_servers:
            QMessageBox.warning(self, '未连接服务器', '请先连接至少一个服务器')
            return
        
        # 检查当前是否有选中的服务器页签
        current_tab_index = self.server_tabs.currentIndex()
        if current_tab_index >= 0:
            # 获取当前页签的服务器名称
            server_name = self.server_tabs.tabText(current_tab_index)
        else:
            # 如果没有选中的页签，让用户选择一个服务器
            from PyQt5.QtWidgets import QInputDialog
            server_name, ok = QInputDialog.getItem(self, '选择服务器', '请选择要下载文件的服务器:', connected_servers, 0, False)
            
            if not (ok and server_name):
                return
        
        # 让用户输入要下载的文件名
        from PyQt5.QtWidgets import QInputDialog
        file_name, ok = QInputDialog.getText(self, '下载文件', '请输入要下载的文件路径（支持绝对路径和相对路径）:')
        
        if ok and file_name:
            # 检查是否是绝对路径
            if file_name.startswith('/'):
                # 如果是绝对路径，直接使用
                file_path = file_name
            else:
                # 如果是相对路径，先尝试使用保存的当前目录
                if server_name in self.current_dirs:
                    current_dir = self.current_dirs[server_name]
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 使用保存的当前目录: {current_dir}")
                else:
                    # 如果没有保存的目录，快速从shell或exec_command获取
                    client = self.server_manager.get_connection(server_name)
                    shell = self.server_manager.get_shell(server_name)
                    current_dir = "/"
                    
                    if shell:
                        try:
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 从shell获取当前目录")
                            shell.send('pwd\n')
                            # 多次尝试读取，确保获取到输出
                            pwd_output = ""
                            max_attempts = 5
                            attempt = 0
                            while attempt < max_attempts:
                                time.sleep(0.05)
                                if shell.recv_ready():
                                    pwd_output += shell.recv(4096).decode('utf-8')
                                    attempt = 0
                                else:
                                    attempt += 1
                            
                            # 解析输出，获取目录
                            lines = pwd_output.split('\n')
                            for line in lines:
                                stripped_line = line.strip()
                                # 只要是/开头就行
                                if stripped_line.startswith('/'):
                                    # 检查是否包含提示符，如果包含，截取到提示符之前
                                    prompt_chars = ['$', '#', '%', '>', ']']
                                    has_prompt = any(c in stripped_line for c in prompt_chars)
                                    if has_prompt:
                                        # 找到第一个提示符的位置
                                        min_pos = len(stripped_line)
                                        for c in prompt_chars:
                                            pos = stripped_line.find(c)
                                            if pos != -1 and pos < min_pos:
                                                min_pos = pos
                                        if min_pos < len(stripped_line):
                                            current_dir = stripped_line[:min_pos].strip()
                                            break
                                    else:
                                        current_dir = stripped_line
                                        break
                            
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 当前目录: {current_dir}")
                        except Exception as e:
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 获取目录失败: {e}")
                            current_dir = "/"
                    else:
                        # 没有shell会话，使用exec_command
                        try:
                            stdin, stdout, stderr = client.exec_command('pwd', timeout=2)
                            current_dir = stdout.read().decode('utf-8').strip()
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 从exec_command获取当前目录: {current_dir}")
                        except Exception as e:
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 获取目录失败: {e}")
                            current_dir = "/"
                
                # 构建完整的文件路径，确保使用正斜杠
                file_path = current_dir.rstrip('/') + '/' + file_name.lstrip('/')
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 构建完整文件路径: {file_path}")
            # 执行下载
            self.download_file(server_name, file_path)
    
    def upload_file(self, server_name):
        client = self.server_manager.get_connection(server_name)
        if not client:
            self.append_output("无法获取服务器连接<br>")
            return
        
        try:
            from PyQt5.QtWidgets import QFileDialog
            local_path, _ = QFileDialog.getOpenFileName(
                self, "选择要上传的文件", os.getcwd(), "All Files (*)"
            )
            
            if local_path:
                sftp = client.open_sftp()
                
                if server_name in self.current_dirs:
                    current_dir = self.current_dirs[server_name]
                    self.append_output(f"当前服务器目录 (保存): {current_dir}<br>")
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 使用保存的当前目录: {current_dir}")
                else:
                    shell = self.server_manager.get_shell(server_name)
                    current_dir = "/"
                    
                    if shell:
                        try:
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 从shell获取当前目录")
                            shell.send('pwd\n')
                            pwd_output = ""
                            max_attempts = 5
                            attempt = 0
                            while attempt < max_attempts:
                                time.sleep(0.05)
                                if shell.recv_ready():
                                    pwd_output += shell.recv(4096).decode('utf-8')
                                    attempt = 0
                                else:
                                    attempt += 1
                            
                            lines = pwd_output.split('\n')
                            for line in lines:
                                stripped_line = line.strip()
                                if stripped_line.startswith('/'):
                                    prompt_chars = ['$', '#', '%', '>', ']']
                                    has_prompt = any(c in stripped_line for c in prompt_chars)
                                    if has_prompt:
                                        min_pos = len(stripped_line)
                                        for c in prompt_chars:
                                            pos = stripped_line.find(c)
                                            if pos != -1 and pos < min_pos:
                                                min_pos = pos
                                        if min_pos < len(stripped_line):
                                            current_dir = stripped_line[:min_pos].strip()
                                            break
                                    else:
                                        current_dir = stripped_line
                                        break
                            
                            self.append_output(f"当前服务器目录 (shell): {current_dir}<br>")
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 当前目录: {current_dir}")
                        except Exception as e:
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 获取目录失败: {e}")
                            current_dir = "/"
                    else:
                        try:
                            stdin, stdout, stderr = client.exec_command('pwd', timeout=2)
                            current_dir = stdout.read().decode('utf-8').strip()
                            self.append_output(f"当前服务器目录 (exec): {current_dir}<br>")
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 从exec_command获取当前目录: {current_dir}")
                        except Exception as e:
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 获取目录失败: {e}")
                            current_dir = "/"
                
                remote_path = current_dir.rstrip('/') + '/' + os.path.basename(local_path)
                self.append_output(f"尝试上传到: {remote_path}<br>")
                
                try:
                    sftp.put(local_path, remote_path)
                    self.append_output(f"文件已上传到: {remote_path}<br>")
                except Exception as upload_error:
                    self.append_output(f"上传失败: {upload_error}<br>")
                finally:
                    sftp.close()
            else:
                self.append_output("文件上传已取消<br>")
        except Exception as e:
            self.append_output(f"上传过程出错: {e}<br>")
    
    def upload_file_from_button(self):
        # 获取已连接的服务器列表
        connected_servers = [server['name'] for server in self.server_manager.servers if self.server_manager.is_connected(server['name'])]
        
        if not connected_servers:
            QMessageBox.warning(self, '未连接服务器', '请先连接至少一个服务器')
            return
        
        # 检查当前是否有选中的服务器页签
        current_tab_index = self.server_tabs.currentIndex()
        if current_tab_index >= 0:
            # 获取当前页签的服务器名称
            server_name = self.server_tabs.tabText(current_tab_index)
            # 执行上传
            self.upload_file(server_name)
        else:
            # 如果没有选中的页签，让用户选择一个服务器
            from PyQt5.QtWidgets import QInputDialog
            server_name, ok = QInputDialog.getItem(self, '选择服务器', '请选择要上传文件的服务器:', connected_servers, 0, False)
            
            if ok and server_name:
                self.upload_file(server_name)
    
    def add_category(self):
        category_name, ok = QInputDialog.getText(self, '添加分类', '分类名称:')
        if ok and category_name:
            self.command_manager.add_category(category_name)
            self.refresh_command_tree()
            # 刷新默认指令按钮面板
            self.refresh_default_command_buttons()
    
    def add_command(self):
        dialog = CommandDialog(command_manager=self.command_manager, parent=self)
        if dialog.exec_():
            category_name = dialog.get_category()
            if category_name:
                command_info = dialog.get_command_info()
                self.command_manager.add_command(category_name, command_info)
                self.refresh_command_tree()
                # 刷新所有服务器页签的指令按钮
                for i in range(self.server_tabs.count()):
                    server_name = self.server_tabs.tabText(i)
                    self.refresh_command_buttons(server_name)
                # 刷新默认指令按钮面板
                self.refresh_default_command_buttons()
            else:
                QMessageBox.warning(self, '选择分类', '请选择一个分类')
    
    def on_command_double_clicked(self, item, column):
        if item.parent():
            # 双击的是指令
            category_item = item.parent()
            category_index = self.command_tree.indexOfTopLevelItem(category_item)
            command_index = category_item.indexOfChild(item)
            command_info = self.command_manager.commands[category_index]['commands'][command_index]
            dialog = CommandDialog(command_info, command_manager=self.command_manager, parent=self)
            # 设置默认分类为原始指令的分类
            category_name = category_item.text(0)
            dialog.category_combo.setCurrentText(category_name)
            if dialog.exec_():
                new_command_info = dialog.get_command_info()
                self.command_manager.update_command(category_index, command_index, new_command_info)
                self.refresh_command_tree()
                # 刷新所有服务器页签的指令按钮
                for i in range(self.server_tabs.count()):
                    server_name = self.server_tabs.tabText(i)
                    self.refresh_command_buttons(server_name)
                # 刷新默认指令按钮面板
                self.refresh_default_command_buttons()
    
    def show_command_context_menu(self, position):
        item = self.command_tree.itemAt(position)
        if item:
            menu = QMenu()
            if item.parent():
                # 指令的右键菜单
                edit_action = QAction('编辑', self)
                delete_action = QAction('删除', self)
                
                edit_action.triggered.connect(lambda: self.edit_command(item))
                delete_action.triggered.connect(lambda: self.delete_command(item))
                
                menu.addAction(edit_action)
                menu.addAction(delete_action)
            else:
                # 分类的右键菜单
                edit_category_action = QAction('编辑分类', self)
                add_command_action = QAction('添加指令', self)
                delete_category_action = QAction('删除分类', self)
                
                edit_category_action.triggered.connect(lambda: self.edit_category(item))
                add_command_action.triggered.connect(lambda: self.add_command_to_category(item))
                delete_category_action.triggered.connect(lambda: self.delete_category(item))
                
                menu.addAction(edit_category_action)
                menu.addAction(add_command_action)
                menu.addAction(delete_category_action)
            
            menu.exec_(self.command_tree.mapToGlobal(position))
    
    def edit_command(self, item):
        category_item = item.parent()
        category_index = self.command_tree.indexOfTopLevelItem(category_item)
        command_index = category_item.indexOfChild(item)
        command_info = self.command_manager.commands[category_index]['commands'][command_index]
        dialog = CommandDialog(command_info, command_manager=self.command_manager, parent=self)
        # 设置默认分类为原始指令的分类
        category_name = category_item.text(0)
        dialog.category_combo.setCurrentText(category_name)
        if dialog.exec_():
            new_command_info = dialog.get_command_info()
            self.command_manager.update_command(category_index, command_index, new_command_info)
            self.refresh_command_tree()
            # 刷新所有服务器页签的指令按钮
            for i in range(self.server_tabs.count()):
                server_name = self.server_tabs.tabText(i)
                self.refresh_command_buttons(server_name)
            # 刷新默认指令按钮面板
            self.refresh_default_command_buttons()
    
    def delete_command(self, item):
        category_item = item.parent()
        category_index = self.command_tree.indexOfTopLevelItem(category_item)
        command_index = category_item.indexOfChild(item)
        self.command_manager.remove_command(category_index, command_index)
        self.refresh_command_tree()
        # 刷新所有服务器页签的指令按钮
        for i in range(self.server_tabs.count()):
            server_name = self.server_tabs.tabText(i)
            self.refresh_command_buttons(server_name)
        # 刷新默认指令按钮面板
        self.refresh_default_command_buttons()
    
    def add_command_to_category(self, category_item):
        category_name = category_item.text(0)
        dialog = CommandDialog(command_manager=self.command_manager, parent=self)
        # 设置默认分类
        dialog.category_combo.setCurrentText(category_name)
        if dialog.exec_():
            command_info = dialog.get_command_info()
            self.command_manager.add_command(category_name, command_info)
            self.refresh_command_tree()
            # 刷新所有服务器页签的指令按钮
            for i in range(self.server_tabs.count()):
                server_name = self.server_tabs.tabText(i)
                self.refresh_command_buttons(server_name)
            # 刷新默认指令按钮面板
            self.refresh_default_command_buttons()
    
    def edit_category(self, category_item):
        category_index = self.command_tree.indexOfTopLevelItem(category_item)
        old_name = category_item.text(0)
        
        # 使用QInputDialog获取新的分类名称
        new_name, ok = QInputDialog.getText(self, '编辑分类', '请输入新的分类名称:', text=old_name)
        if ok and new_name.strip():
            # 确保新名称不与其他分类重复
            for i, category in enumerate(self.command_manager.commands):
                if i != category_index and category['name'] == new_name:
                    QMessageBox.warning(self, '错误', '分类名称已存在!')
                    return
            
            # 更新分类名称
            self.command_manager.commands[category_index]['name'] = new_name
            self.command_manager.save_commands()
            self.refresh_command_tree()
            # 刷新所有服务器页签的指令按钮
            for i in range(self.server_tabs.count()):
                server_name = self.server_tabs.tabText(i)
                self.refresh_command_buttons(server_name)
            # 刷新默认指令按钮面板
            self.refresh_default_command_buttons()
    
    def delete_category(self, category_item):
        category_index = self.command_tree.indexOfTopLevelItem(category_item)
        self.command_manager.remove_category(category_index)
        self.refresh_command_tree()
        # 刷新所有服务器页签的指令按钮
        for i in range(self.server_tabs.count()):
            server_name = self.server_tabs.tabText(i)
            self.refresh_command_buttons(server_name)
        # 刷新默认指令按钮面板
        self.refresh_default_command_buttons()
    
    def export_config(self):
        # 打开文件选择对话框，让用户选择导出位置
        file_path, _ = QFileDialog.getSaveFileName(
            self, "导出配置", os.getcwd(), "JSON文件 (*.json)"
        )
        if not file_path:
            return  # 用户取消选择
        
        # 确保文件扩展名是.json
        if not file_path.endswith('.json'):
            file_path += '.json'
        
        # 导出配置，包括布局设置
        config = {
            'servers': self.server_manager.servers,
            'commands': self.command_manager.commands,
            'layout_params': self.layout_params
        }
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, ensure_ascii=False, indent=2)
        self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 配置已导出到: {file_path}")
    
    def import_config(self):
        # 打开文件选择对话框，让用户选择导入位置
        file_path, _ = QFileDialog.getOpenFileName(
            self, "导入配置", os.getcwd(), "JSON文件 (*.json)"
        )
        if not file_path:
            return  # 用户取消选择
        
        if os.path.exists(file_path):
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                
                # 导入服务器配置
                self.server_manager.servers = config.get('servers', [])
                self.server_manager.save_servers()
                
                # 导入指令配置
                self.command_manager.commands = config.get('commands', [])
                self.command_manager.save_commands()
                
                # 导入布局设置
                if 'layout_params' in config:
                    self.layout_params = config['layout_params']
                
                # 刷新界面
                self.refresh_server_list()
                self.refresh_command_tree()
                self.refresh_default_command_buttons()
                
                # 断开所有连接
                for server_name in list(self.server_manager.connections.keys()):
                    self.server_manager.disconnect_server(server_name)
                
                # 清空服务器页签
                while self.server_tabs.count() > 0:
                    self.server_tabs.removeTab(0)
                
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 配置已从: {file_path} 导入")
            except Exception as e:
                QMessageBox.warning(self, '导入失败', f'导入配置失败: {e}')
        else:
            QMessageBox.warning(self, '导入失败', f'配置文件不存在: {file_path}')
    
    def on_server_clicked(self, item):
        server_name = item.text().split(' ')[0]
        if self.server_manager.is_connected(server_name):
            self.add_server_tab(server_name)
        else:
            # 提示用户连接服务器
            reply = QMessageBox.question(self, '未连接', f'服务器 {server_name} 未连接，是否连接？', QMessageBox.Yes | QMessageBox.No, QMessageBox.Yes)
            if reply == QMessageBox.Yes:
                self.connect_server(server_name)
    
    def show_layout_settings(self):
        dialog = LayoutSettingsDialog(self.layout_params, self)
        if dialog.exec_():
            # 应用新的布局参数
            self.layout_params = dialog.get_layout_params()
            # 更新窗口大小
            self.resize(self.layout_params['window_width'], self.layout_params['window_height'])
            # 刷新指令按钮面板
            self.refresh_default_command_buttons()
            # 刷新所有服务器的指令按钮面板
            for server_name in self.server_button_layouts:
                layout = self.server_button_layouts[server_name]
                self.add_command_buttons_to_layout(layout, server_name)
            # 重新创建右侧分割器，应用新的大小设置
            # 找到主分割器
            splitter = self.findChild(QSplitter)
            if splitter:
                # 找到右侧面板
                right_panel = splitter.widget(1)
                if right_panel:
                    # 找到右侧面板中的垂直分割器
                    for i in range(right_panel.layout().count()):
                        item = right_panel.layout().itemAt(i)
                        if item:
                            widget = item.widget()
                            if isinstance(widget, QSplitter) and widget.orientation() == Qt.Vertical:
                                # 找到右侧分割器，更新大小
                                widget.setSizes([self.layout_params['command_panel_height'], self.layout_params['output_panel_height']])
                                break
            # 保存设置
            self.save_settings()
    
    def on_server_tab_changed(self, index):
        # 当服务器标签切换时更新输出终端
        if index >= 0:
            server_name = self.server_tabs.tabText(index)
            # 清空输出终端
            self.server_output.clear()
            self.server_output.append(f'已切换到服务器: {server_name}')
            
            # 获取服务器信息
            for server in self.server_manager.servers:
                if server['name'] == server_name:
                    self.server_output.append(f'服务器地址: {server["host"]}:{server["port"]}')
                    self.server_output.append(f'登录用户: {server["username"]}')
                    break
            
            # 获取当前目录
            if server_name in self.current_dirs:
                current_dir = self.current_dirs[server_name]
                self.server_output.append(f'当前目录: {current_dir}')
            else:
                # 尝试获取当前目录
                client = self.server_manager.get_connection(server_name)
                if client:
                    try:
                        stdin, stdout, stderr = client.exec_command('pwd')
                        current_dir = stdout.read().decode('utf-8').strip()
                        self.current_dirs[server_name] = current_dir
                        self.server_output.append(f'当前目录: {current_dir}')
                    except Exception as e:
                        self.server_output.append(f'获取当前目录失败: {e}')
        else:
            # 没有选中任何标签
            self.server_output.clear()
            self.server_output.append('系统就绪，等待连接...')

class LayoutSettingsDialog(QDialog):
    def __init__(self, layout_params, parent=None):
        super().__init__(parent)
        self.setWindowTitle('布局设置')
        self.setGeometry(100, 100, 400, 300)
        # 确保对话框在父窗口中央弹出
        if parent:
            self.move(parent.frameGeometry().center() - self.frameGeometry().center())
        
        self.layout_params = layout_params.copy()
        
        layout = QVBoxLayout()
        
        form_layout = QFormLayout()
        
        # 分类间距
        self.category_spacing_edit = QLineEdit(str(layout_params['category_spacing']))
        form_layout.addRow('分类之间的间距:', self.category_spacing_edit)
        
        # 标题与按钮间距
        self.title_button_spacing_edit = QLineEdit(str(layout_params['title_button_spacing']))
        form_layout.addRow('标题与按钮之间的间距:', self.title_button_spacing_edit)
        
        # 按钮间距
        self.button_spacing_edit = QLineEdit(str(layout_params['button_spacing']))
        form_layout.addRow('按钮之间的间距:', self.button_spacing_edit)
        
        # 按钮宽度
        self.button_width_edit = QLineEdit(str(layout_params['button_width']))
        form_layout.addRow('按钮宽度:', self.button_width_edit)
        
        # 按钮高度
        self.button_height_edit = QLineEdit(str(layout_params['button_height']))
        form_layout.addRow('按钮高度:', self.button_height_edit)
        
        # 分类标题字号
        self.category_font_size_edit = QLineEdit(str(layout_params['category_font_size']))
        form_layout.addRow('分类标题字号:', self.category_font_size_edit)
        
        # 分类标题行高
        self.category_line_height_edit = QLineEdit(str(layout_params['category_line_height']))
        form_layout.addRow('分类标题行高倍数:', self.category_line_height_edit)
        
        # 指令面板高度
        self.command_panel_height_edit = QLineEdit(str(layout_params['command_panel_height']))
        form_layout.addRow('指令面板高度:', self.command_panel_height_edit)
        
        # 输出面板高度
        self.output_panel_height_edit = QLineEdit(str(layout_params['output_panel_height']))
        form_layout.addRow('输出面板高度:', self.output_panel_height_edit)
        
        # 程序窗口宽度
        self.window_width_edit = QLineEdit(str(layout_params['window_width']))
        form_layout.addRow('程序窗口宽度:', self.window_width_edit)
        
        # 程序窗口高度
        self.window_height_edit = QLineEdit(str(layout_params['window_height']))
        form_layout.addRow('程序窗口高度:', self.window_height_edit)
        
        layout.addLayout(form_layout)
        
        # 按钮
        button_box = QHBoxLayout()
        save_button = QPushButton('保存')
        cancel_button = QPushButton('取消')
        
        save_button.clicked.connect(self.accept)
        cancel_button.clicked.connect(self.reject)
        
        button_box.addWidget(save_button)
        button_box.addWidget(cancel_button)
        layout.addLayout(button_box)
        
        self.setLayout(layout)
    
    def get_layout_params(self):
        # 验证输入并返回新的布局参数
        try:
            return {
                'category_spacing': int(self.category_spacing_edit.text()),
                'title_button_spacing': int(self.title_button_spacing_edit.text()),
                'button_spacing': int(self.button_spacing_edit.text()),
                'button_width': int(self.button_width_edit.text()),
                'button_height': int(self.button_height_edit.text()),
                'category_font_size': int(self.category_font_size_edit.text()),
                'category_line_height': float(self.category_line_height_edit.text()),
                'command_panel_height': int(self.command_panel_height_edit.text()),
                'output_panel_height': int(self.output_panel_height_edit.text()),
                'window_width': int(self.window_width_edit.text()),
                'window_height': int(self.window_height_edit.text())
            }
        except ValueError:
            # 如果输入无效，返回原始参数
            return self.layout_params

# 导入QInputDialog
from PyQt5.QtWidgets import QInputDialog

if __name__ == '__main__':
    # 设置当前工作目录为程序所在目录（支持PyInstaller打包）
    if hasattr(sys, '_MEIPASS'):
        # 当程序被PyInstaller打包时
        os.chdir(os.path.dirname(os.path.abspath(sys.executable)))
    else:
        # 当程序在开发环境中运行时
        os.chdir(os.path.dirname(os.path.abspath(__file__)))
    app = QApplication(sys.argv)
    window = ServerAssistant()
    window.show()
    sys.exit(app.exec_())
