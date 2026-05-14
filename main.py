#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import re
from PyQt5.QtWidgets import QApplication, QMainWindow, QTabWidget, QVBoxLayout, QWidget, QSplitter, QPushButton, QListWidget, QListWidgetItem, QTreeWidget, QTreeWidgetItem, QDialog, QFormLayout, QLineEdit, QLabel, QComboBox, QMenu, QAction, QTextEdit, QFileDialog, QMessageBox, QGridLayout, QHBoxLayout, QSizePolicy, QCheckBox, QScrollArea, QCompleter, QInputDialog, QSpinBox
from PyQt5.QtCore import Qt, QMutex, QMutexLocker, QTimer, pyqtSignal, QEvent, QThreadPool, QRunnable, QObject, QStringListModel
from PyQt5.QtGui import QFont, QColor, QTextCursor, QIntValidator, QPixmap, QPainter
import paramiko
import json
import os
import posixpath
import time


# ==================== 常量定义 ====================

# 超时时间（秒）
TIMEOUT_COMMAND = 60          # 命令执行超时
TIMEOUT_CONNECTION = 10       # 连接超时
TIMEOUT_BANNER = 20           # SSH banner 超时
TIMEOUT_AUTH = 30             # 认证超时
TIMEOUT_EXEC_SHORT = 2        # 短命令执行超时（如 pwd）
TIMEOUT_EXEC_MEDIUM = 5       # 中等命令执行超时（如 ls）
TIMEOUT_KEEPALIVE = 30        # 连接保活间隔

# 命令解析相关
PROMPT_CHARS = ['$', '#', '%', '>', ']']
RECV_CHUNK_SIZE = 4096        # SSH 接收缓冲区大小
RECV_POLL_INTERVAL = 0.01     # 轮询间隔（秒）
RECV_SHELL_DELAY = 0.05       # shell 命令发送后等待时间
RECV_MAX_ATTEMPTS = 5         # 最大读取尝试次数

# 布局相关
BUTTONS_PER_ROW = 6           # 每行按钮数量

# 全局样式表
LIGHT_QSS = '''
QMainWindow {
    background-color: #f0f2f5;
}
QWidget {
    font-family: "Microsoft YaHei", "Segoe UI", sans-serif;
    font-size: 13px;
}
QTabWidget::pane {
    border: none;
    background-color: transparent;
}
QTabBar::tab {
    padding: 5px 14px;
    margin-right: 2px;
    background-color: transparent;
    color: #666;
    border: none;
}
QTabBar::tab:selected {
    color: #1890ff;
    border-bottom: 2px solid #1890ff;
}
QTabBar::tab:hover:!selected {
    color: #333;
}
QPushButton {
    background-color: #ffffff;
    color: #333333;
    border: 0.5px solid #d9d9d9;
    border-radius: 6px;
    padding: 6px 14px;
}
QPushButton:hover {
    background-color: #f0f5ff;
    border-color: #1890ff;
    color: #1890ff;
}
QPushButton:pressed {
    background-color: #e6f7ff;
}
QLineEdit {
    padding: 8px 10px;
    border: 0.5px solid #d9d9d9;
    border-radius: 6px;
    background-color: #ffffff;
}
QLineEdit:focus {
    border-color: #1890ff;
}
QListWidget {
    border: 0.5px solid #e8e8e8;
    border-radius: 8px;
    background-color: #ffffff;
    outline: none;
    padding: 4px;
}
QListWidget::item {
    padding: 6px 8px;
    border-radius: 4px;
    margin: 2px 0;
}
QListWidget::item:selected {
    background-color: #e6f7ff;
    color: #1890ff;
}
QListWidget::item:hover:!selected {
    background-color: #f5f5f5;
}
QTreeWidget {
    border: 0.5px solid #e8e8e8;
    border-radius: 8px;
    background-color: #ffffff;
    outline: none;
    padding: 4px;
}
QTreeWidget::item {
    padding: 4px 0;
}
QTreeWidget::item:selected {
    background-color: #e6f7ff;
    color: #1890ff;
}
QTreeWidget::item:hover:!selected {
    background-color: #f5f5f5;
}
QScrollBar:vertical {
    width: 6px;
    background: transparent;
}
QScrollBar::handle:vertical {
    background: #c0c0c0;
    border-radius: 3px;
    min-height: 20px;
}
QScrollBar::handle:vertical:hover {
    background: #a0a0a0;
}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    height: 0px;
}
QScrollBar:horizontal {
    height: 6px;
    background: transparent;
}
QScrollBar::handle:horizontal {
    background: #c0c0c0;
    border-radius: 3px;
    min-width: 20px;
}
QScrollBar::handle:horizontal:hover {
    background: #a0a0a0;
}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
    width: 0px;
}
QSplitter::handle {
    background-color: #e0e0e0;
}
QSplitter::handle:horizontal {
    width: 2px;
}
QSplitter::handle:vertical {
    height: 2px;
}
QWidget#commandPanel {
    background-color: #ffffff;
}
'''


# ==================== 工具函数 ====================

def get_base_dir():
    """获取程序所在目录（支持 PyInstaller 打包）"""
    if hasattr(sys, '_MEIPASS'):
        return os.path.dirname(os.path.abspath(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))


def clear_layout(layout):
    """彻底清空布局中的所有控件和子布局"""
    if layout is None:
        return
    while layout.count():
        item = layout.takeAt(0)
        if item is None:
            continue
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()
        else:
            sub_layout = item.layout()
            if sub_layout is not None:
                clear_layout(sub_layout)
                sub_layout.deleteLater()


def create_status_icon(color_hex, size=10):
    """创建状态圆点图标"""
    pixmap = QPixmap(size, size)
    pixmap.fill(Qt.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.Antialiasing)
    painter.setBrush(QColor(color_hex))
    painter.setPen(Qt.NoPen)
    painter.drawEllipse(0, 0, size, size)
    painter.end()
    from PyQt5.QtGui import QIcon
    return QIcon(pixmap)


def parse_pwd_output(pwd_output):
    """从 pwd 命令输出中解析当前目录路径"""
    lines = [l.strip() for l in pwd_output.split('\n') if l.strip()]

    def _trim_prompt(s):
        """从行尾截断连续的提示符字符"""
        i = len(s) - 1
        while i >= 0 and s[i].isspace():
            i -= 1
        prompt_end = i
        while i >= 0 and s[i] in PROMPT_CHARS:
            i -= 1
        if prompt_end > i and i >= 0:
            return s[:i + 1].strip()
        return s

    # 1. 优先找以 / 开头且不包含提示符字符的干净行
    for line in lines:
        if line.startswith('/'):
            if not any(c in line for c in PROMPT_CHARS):
                return line

    # 2. 找以 / 开头的行，截断行尾连续提示符
    for line in lines:
        if line.startswith('/'):
            trimmed = _trim_prompt(line)
            return trimmed if trimmed else line

    # 3. 找包含 / 的行（如 [root@host /var/log]# ），提取路径部分
    for line in lines:
        if '/' in line:
            slash_pos = line.find('/')
            path_part = line[slash_pos:]
            trimmed = _trim_prompt(path_part)
            return trimmed if trimmed else path_part

    return "/"


class CommandSignals(QObject):
    result = pyqtSignal(str)
    partial_result = pyqtSignal(str)
    finished = pyqtSignal()
    current_dir_updated = pyqtSignal(str, str)


class CommandRunnable(QRunnable):
    def __init__(self, client, command, command_log, server_name, server_manager, current_dirs, is_continuous=False):
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
        self.saved_dir = current_dirs.get(server_name, "/")
        self.command_timeout = TIMEOUT_COMMAND
        self.is_continuous = is_continuous
    
    def stop(self):
        self.is_running = False
        if self.shell:
            try:
                self.shell.send('\x03')
            except Exception:
                pass
    
    def recv_with_timeout(self, timeout=0.1):
        start_time = time.time()
        data = ""
        while self.is_running and (time.time() - start_time) < timeout:
            if self.shell.recv_ready():
                try:
                    data += self.shell.recv(RECV_CHUNK_SIZE).decode('utf-8', errors='replace')
                    if data:
                        return data
                except Exception:
                    break
            time.sleep(RECV_POLL_INTERVAL)
        return data
    
    def run(self):
        try:
            self.command_log.append(f"  线程开始执行命令: {self.command}")
            
            self.shell = self.server_manager.get_shell(self.server_name)
            
            if self.shell:
                self.command_log.append(f"  使用持久shell会话执行命令")
                
                current_dir_before = "/"
                self.shell.send(self.command + '\n')
                self.command_log.append(f"  命令发送到shell")
                
                if self.is_continuous:
                    self.command_log.append(f"  检测到持续运行的命令，开始实时读取输出")
                    output_buffer = ""
                    start_time = time.time()
                    
                    self.signals.partial_result.emit(f"$ {self.command}\n")
                    
                    while self.is_running:
                        output = self.recv_with_timeout(0.1)
                        if output:
                            output_buffer += output
                            if '\n' in output_buffer:
                                self.signals.partial_result.emit(output_buffer)
                                output_buffer = ""
                    
                    if not self.is_running:
                        self.command_log.append(f"  命令执行被用户停止")
                        self.signals.partial_result.emit("\n命令已停止\n")
                        try:
                            self.shell.send('\x03')
                            time.sleep(0.1)
                            self.command_log.append(f"  已发送 Ctrl+C 终止命令")
                        except Exception as e:
                            self.command_log.append(f"  发送终止信号失败：{e}")
                    
                    current_dir = self.saved_dir
                    try:
                        self.shell.send('pwd\n')
                        pwd_output = ""
                        for _ in range(20):
                            time.sleep(RECV_SHELL_DELAY)
                            if self.shell.recv_ready():
                                pwd_output += self.shell.recv(RECV_CHUNK_SIZE).decode('utf-8', errors='replace')
                                if '\n' in pwd_output:
                                    break

                        found_dir = parse_pwd_output(pwd_output)
                        if found_dir and found_dir != "/":
                            current_dir = found_dir
                            self.command_log.append(f"  持续命令执行后当前目录: {current_dir}")
                        else:
                            self.command_log.append(f"  使用保存的目录: {current_dir}")
                    except Exception as e:
                        self.command_log.append(f"  获取当前目录失败，使用保存的目录: {e}")
                    
                    self.signals.current_dir_updated.emit(self.server_name, current_dir)
                else:
                    output = ""
                    start_time = time.time()
                    
                    while self.is_running and (time.time() - start_time) < self.command_timeout:
                        output_chunk = self.recv_with_timeout(0.1)
                        if output_chunk:
                            output += output_chunk
                            start_time = time.time()
                        elif output and (time.time() - start_time) > 0.5:
                            break
                        elif not output and (time.time() - start_time) > 1:
                            break
                    
                    self.command_log.append(f"  读取shell输出完成，长度: {len(output)}")
                    
                    current_dir = self.saved_dir
                    try:
                        self.shell.send('pwd\n')
                        pwd_output = ""
                        for _ in range(20):
                            time.sleep(RECV_SHELL_DELAY)
                            if self.shell.recv_ready():
                                pwd_output += self.shell.recv(RECV_CHUNK_SIZE).decode('utf-8', errors='replace')
                                if '\n' in pwd_output:
                                    break

                        found_dir = parse_pwd_output(pwd_output)
                        if found_dir and found_dir != "/":
                            current_dir = found_dir
                            self.command_log.append(f"  执行后当前目录: {current_dir}")
                        else:
                            self.command_log.append(f"  使用保存的目录: {current_dir}")
                    except Exception as e:
                        self.command_log.append(f"  获取当前目录失败，使用保存的目录: {e}")
                    
                    self.signals.current_dir_updated.emit(self.server_name, current_dir)
                    
                    full_output = f"$ {self.command}\n{output}"
                    self.command_log.append(f"  构建完整输出完成")
                    
                    self.signals.result.emit(full_output)
            else:
                self.command_log.append(f"  没有持久shell会话，使用普通命令执行")
                try:
                    stdin, stdout, stderr = self.client.exec_command(self.command, timeout=self.command_timeout)
                    self.command_log.append(f"  命令执行中...")
                    
                    output = stdout.read().decode('utf-8', errors='replace') + stderr.read().decode('utf-8', errors='replace')
                    self.command_log.append(f"  命令执行完成，输出长度: {len(output)}")
                except Exception as e:
                    output = f"命令执行出错: {e}"
                    self.command_log.append(f"  命令执行出错: {e}")
                
                current_dir = self.saved_dir
                try:
                    stdin_pwd, stdout_pwd, stderr_pwd = self.client.exec_command('pwd', timeout=TIMEOUT_EXEC_MEDIUM)
                    found_dir = stdout_pwd.read().decode('utf-8', errors='replace').strip()
                    if found_dir and found_dir != "/":
                        current_dir = found_dir
                        self.command_log.append(f"  当前目录: {current_dir}")
                    else:
                        self.command_log.append(f"  使用保存的目录: {current_dir}")
                    self.signals.current_dir_updated.emit(self.server_name, current_dir)
                except Exception as e:
                    self.command_log.append(f"  获取当前目录失败，使用保存的目录: {e}")
                    self.signals.current_dir_updated.emit(self.server_name, current_dir)
                
                full_output = f"$ {self.command}\n{output}"
                self.command_log.append(f"  构建完整输出完成")
                
                self.signals.result.emit(full_output)
            
            self.command_log.append(f"  命令执行完成")
            self.signals.finished.emit()
        except Exception as e:
            error_msg = f"错误: {e}"
            self.command_log.append(f"  执行命令时出错: {e}")
            self.signals.result.emit(error_msg)
            self.signals.finished.emit()


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
        event.ignore()

class DraggableTextEdit(QTextEdit):
    files_dropped = pyqtSignal(list)
    
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAcceptDrops(True)
        self._drag_active = False
        self._base_style = ''
    
    def setStyleSheet(self, style):
        if not self._drag_active:
            self._base_style = style
        super().setStyleSheet(style)
    
    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
            self._drag_active = True
            super().setStyleSheet(self._base_style + 'border: 2px solid #1890ff;')
        else:
            super().dragEnterEvent(event)
    
    def dragMoveEvent(self, event):
        if event.mimeData().hasUrls():
            event.acceptProposedAction()
        else:
            super().dragMoveEvent(event)
    
    def dragLeaveEvent(self, event):
        self._drag_active = False
        self._restore_border()
        super().dragLeaveEvent(event)
    
    def dropEvent(self, event):
        self._drag_active = False
        self._restore_border()
        if event.mimeData().hasUrls():
            files = []
            for url in event.mimeData().urls():
                file_path = url.toLocalFile()
                if os.path.isfile(file_path):
                    files.append(file_path)
            if files:
                self.files_dropped.emit(files)
            event.acceptProposedAction()
        else:
            super().dropEvent(event)
    
    def _restore_border(self):
        super().setStyleSheet(self._base_style)

class ServerManager:
    def __init__(self):
        self.servers = []
        self.connections = {}
        self.shells = {}  # 存储持久的shell会话
        self.base_dir = get_base_dir()
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
                        password=server['password'],
                        timeout=TIMEOUT_CONNECTION,
                        banner_timeout=TIMEOUT_BANNER,
                        auth_timeout=TIMEOUT_AUTH
                    )
                    client.get_transport().set_keepalive(TIMEOUT_KEEPALIVE)
                    self.connections[server_name] = client
                    try:
                        shell = client.invoke_shell()
                        self.shells[server_name] = shell
                    except Exception as shell_error:
                        # shell 创建失败，保留 exec 连接但记录错误
                        print(f"创建 shell 会话失败: {shell_error}")
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
            except Exception:
                pass
        if server_name in self.shells:
            try:
                self.shells[server_name].close()
                del self.shells[server_name]
            except Exception:
                pass
    
    def get_shell(self, server_name):
        return self.shells.get(server_name)
    
    def is_connected(self, server_name):
        return server_name in self.connections
    
    def is_connection_alive(self, server_name):
        if server_name not in self.connections:
            return False
        try:
            transport = self.connections[server_name].get_transport()
            if transport is None or not transport.is_active():
                return False
            return True
        except Exception:
            return False
    
    def ensure_connection(self, server_name):
        if not self.is_connection_alive(server_name):
            self.disconnect_server(server_name)
            return self.connect_server(server_name)
        return True
    
    def get_connection(self, server_name):
        return self.connections.get(server_name)

class CommandManager:
    def __init__(self):
        self.commands = []
        self.base_dir = get_base_dir()
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
        self.port_edit.setValidator(QIntValidator(1, 65535))
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
        try:
            port = int(self.port_edit.text())
        except ValueError:
            port = 22
        return {
            'name': self.name_edit.text(),
            'host': self.host_edit.text(),
            'port': port,
            'username': self.username_edit.text(),
            'password': self.password_edit.text()
        }

class CommandDialog(QDialog):
    def __init__(self, command_info=None, command_manager=None, server_manager=None, parent=None):
        super().__init__(parent)
        self.setWindowTitle('编辑指令' if command_info else '添加指令')
        self.setGeometry(100, 100, 500, 400)
        if parent:
            self.move(parent.frameGeometry().center() - self.frameGeometry().center())
        
        self.command_manager = command_manager
        self.server_manager = server_manager
        
        layout = QVBoxLayout()
        
        form_layout = QFormLayout()
        
        self.category_combo = QComboBox()
        self.load_categories()
        
        self.name_edit = QLineEdit()
        self.command_edit = QLineEdit()
        self.continuous_output_checkbox = QCheckBox('持续输出模式（命令会持续返回信息，如 tailf、top 等）')
        
        form_layout.addRow('分类:', self.category_combo)
        form_layout.addRow('指令名称:', self.name_edit)
        form_layout.addRow('指令内容:', self.command_edit)
        form_layout.addRow('', self.continuous_output_checkbox)
        
        # 前置关联指令配置
        self.enable_linked_checkbox = QCheckBox('启用前置关联指令')
        self.enable_linked_checkbox.stateChanged.connect(self.toggle_linked_controls)
        form_layout.addRow('', self.enable_linked_checkbox)
        
        self.linked_command_combo = QComboBox()
        self.linked_command_combo.setEnabled(False)
        self.load_linked_commands()
        form_layout.addRow('关联指令:', self.linked_command_combo)
        
        self.linked_delay_spinbox = QSpinBox()
        self.linked_delay_spinbox.setRange(0, 60000)
        self.linked_delay_spinbox.setSingleStep(100)
        self.linked_delay_spinbox.setSuffix(' 毫秒')
        self.linked_delay_spinbox.setEnabled(False)
        form_layout.addRow('延迟时长:', self.linked_delay_spinbox)
        
        # 目标服务器配置
        self.target_server_combo = QComboBox()
        self.load_target_servers()
        form_layout.addRow('目标服务器:', self.target_server_combo)
        
        layout.addLayout(form_layout)
        
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
            if command_info.get('continuous'):
                self.continuous_output_checkbox.setChecked(True)
            if 'params' in command_info:
                params = command_info['params']
                if isinstance(params, list):
                    for param in params:
                        if isinstance(param, dict) and 'name' in param:
                            self.add_param(param['name'], param.get('hint', ''))
                        elif isinstance(param, str):
                            self.add_param(param, '')
            # 恢复目标服务器配置
            target_server = command_info.get('target_server')
            if target_server:
                for i in range(self.target_server_combo.count()):
                    data = self.target_server_combo.itemData(i)
                    if data == target_server:
                        self.target_server_combo.setCurrentIndex(i)
                        break
            
            # 恢复关联指令配置
            if command_info.get('linked_enabled'):
                self.enable_linked_checkbox.setChecked(True)
                linked = command_info.get('linked_command')
                if linked and isinstance(linked, dict):
                    for i in range(self.linked_command_combo.count()):
                        data = self.linked_command_combo.itemData(i)
                        if data and data.get('category') == linked.get('category') and data.get('name') == linked.get('name'):
                            self.linked_command_combo.setCurrentIndex(i)
                            break
                self.linked_delay_spinbox.setValue(command_info.get('linked_delay', 0))
            else:
                self.linked_delay_spinbox.setValue(command_info.get('linked_delay', 0))
    
    def load_categories(self):
        # 加载分类列表
        if self.command_manager:
            for category in self.command_manager.commands:
                self.category_combo.addItem(category['name'])
    
    def load_target_servers(self):
        # 加载服务器列表供目标服务器选择
        self.target_server_combo.clear()
        self.target_server_combo.addItem('当前服务器（默认）', None)
        if self.server_manager:
            for server in self.server_manager.servers:
                self.target_server_combo.addItem(server['name'], server['name'])
    
    def load_linked_commands(self):
        # 加载所有指令供关联选择
        if not self.command_manager:
            return
        self.linked_command_combo.clear()
        self.linked_command_combo.addItem('请选择...', None)
        for category in self.command_manager.commands:
            for command in category.get('commands', []):
                display = f"{category['name']} / {command['name']}"
                data = {'category': category['name'], 'name': command['name']}
                self.linked_command_combo.addItem(display, data)
    
    def toggle_linked_controls(self, state):
        enabled = state == Qt.Checked
        self.linked_command_combo.setEnabled(enabled)
        self.linked_delay_spinbox.setEnabled(enabled)
    
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
        delete_button.clicked.connect(lambda checked, pw=param_widget: self.delete_param(pw))
        
        param_hlayout.addWidget(param_edit)
        param_hlayout.addWidget(hint_edit)
        param_hlayout.addWidget(delete_button)
        param_widget.setLayout(param_hlayout)
        
        self.params_layout.addWidget(param_widget)
        # 存储param_widget引用以便删除时匹配
        self.params.append((param_edit, hint_edit, param_widget))
    
    def delete_param(self, param_widget):
        index = self.params_layout.indexOf(param_widget)
        if index >= 0:
            widget = self.params_layout.takeAt(index).widget()
            if widget:
                widget.deleteLater()
            # 从params列表中移除
            for i, (param_edit, hint_edit, pw) in enumerate(self.params):
                if pw == param_widget:
                    self.params.pop(i)
                    break
    
    def get_command_info(self):
        params = []
        for param_edit, hint_edit, _ in self.params:
            param_name = param_edit.text()
            if param_name:
                params.append({
                    'name': param_name,
                    'hint': hint_edit.text()
                })
        linked_command = None
        if self.enable_linked_checkbox.isChecked():
            data = self.linked_command_combo.currentData()
            if data:
                linked_command = data
        target_server = self.target_server_combo.currentData()
        return {
            'name': self.name_edit.text(),
            'command': self.command_edit.text(),
            'params': params,
            'continuous': self.continuous_output_checkbox.isChecked(),
            'linked_enabled': self.enable_linked_checkbox.isChecked(),
            'linked_command': linked_command,
            'linked_delay': self.linked_delay_spinbox.value(),
            'target_server': target_server
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


class CommandLineEdit(QLineEdit):
    """自定义命令输入框，拦截Tab键用于自动补全"""
    tabPressed = pyqtSignal()
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Tab:
            event.accept()
            self.tabPressed.emit()
            return
        super().keyPressEvent(event)
    
    def focusNextPrevChild(self, next_child):
        return False


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
        
        self.last_local_dir = ''  # 上次使用的本地目录
        
        # 输出锁，确保多线程环境下输出顺序正确
        self.output_mutex = QMutex()
        
        # 加载保存的设置
        self.load_settings()
        
        # 调整窗口默认大小，确保能显示完整的6个指令按钮
        self.setGeometry(100, 100, self.layout_params['window_width'], self.layout_params['window_height'])
        
        self.init_ui()
        
        self.connection_check_timer = QTimer()
        self.connection_check_timer.timeout.connect(self.check_connections_status)
        self.connection_check_timer.start(60000)
    
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
    
    def remove_stop_button(self):
        if hasattr(self, 'stop_button') and self.stop_button:
            try:
                self.stop_button_layout.removeWidget(self.stop_button)
                self.stop_button.deleteLater()
            except Exception:
                pass
            self.stop_button = None
    
    def on_tab_pressed(self):
        """处理Tab键按下事件"""
        current_text = self.command_input.text()
        
        # 检查是否是 cd 命令
        if current_text.startswith('cd '):
            path_prefix = current_text[3:].strip()
            
            server_name = None
            if self.server_tabs.count() > 0:
                server_name = self.server_tabs.tabText(self.server_tabs.currentIndex())
            
            if server_name and self.server_manager.is_connected(server_name):
                current_dir = self.current_dirs.get(server_name, "/")
                client = self.server_manager.get_connection(server_name)
                
                if client:
                    try:
                        if path_prefix:
                            # 处理相对路径和绝对路径（远程服务器使用 POSIX 路径语义）
                            if path_prefix.startswith('/'):
                                # 绝对路径
                                parent_dir = posixpath.dirname(path_prefix)
                                if not parent_dir:
                                    parent_dir = '/'
                                search_prefix = posixpath.basename(path_prefix)
                            else:
                                # 相对路径
                                parent_dir = current_dir
                                search_prefix = path_prefix
                            
                            safe_dir = parent_dir.replace('"', '\\"')
                            stdin, stdout, stderr = client.exec_command(f'ls -la "{safe_dir}"', timeout=TIMEOUT_EXEC_MEDIUM)
                        else:
                            safe_dir = current_dir.replace('"', '\\"')
                            stdin, stdout, stderr = client.exec_command(f'ls -la "{safe_dir}"', timeout=TIMEOUT_EXEC_MEDIUM)
                            search_prefix = ''
                        
                        output = stdout.read().decode('utf-8', errors='replace')
                        
                        files = []
                        for line in output.split('\n')[1:]:
                            if not line.strip():
                                continue
                            parts = line.split()
                            if len(parts) >= 9:
                                filename = parts[-1]
                                if filename not in ['.', '..']:
                                    is_dir = parts[0].startswith('d')
                                    if search_prefix:
                                        if filename.startswith(search_prefix):
                                            if is_dir:
                                                filename += '/'
                                            files.append(filename)
                                    else:
                                        if is_dir:
                                            filename += '/'
                                        files.append(filename)
                        
                        if files:
                            files.sort()
                            completer = self.command_input.completer()
                            if completer:
                                completer.setModel(None)
                                model = QStringListModel(files)
                                completer.setModel(model)
                                completer.complete()
                        else:
                            # 没有匹配的文件，显示提示
                            self.command_log.append(f"  没有找到匹配 '{search_prefix}' 的目录")
                    except Exception as e:
                        self.command_log.append(f"  补全错误: {e}")
            else:
                self.command_log.append("  请先连接服务器")
        
        # 默认触发补全
        completer = self.command_input.completer()
        if completer:
            completer.complete()
    
    def check_connections_status(self):
        disconnected_servers = []
        for server_name in list(self.server_manager.connections.keys()):
            if not self.server_manager.is_connection_alive(server_name):
                disconnected_servers.append(server_name)
                self.server_manager.disconnect_server(server_name)
        
        if disconnected_servers:
            self.remove_stop_button()
            self.refresh_server_list()
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 检测到以下服务器连接已断开: {', '.join(disconnected_servers)}")
            for server_name in disconnected_servers:
                for i in range(self.server_tabs.count()):
                    if self.server_tabs.tabText(i) == server_name:
                        self.server_tabs.removeTab(i)
                        break
                if server_name in self.server_button_layouts:
                    del self.server_button_layouts[server_name]
                if server_name in self.current_dirs:
                    del self.current_dirs[server_name]
    
    # 预编译正则表达式
    _ip_pattern = re.compile(r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b')
    _dark_keywords = {
        'ERROR': '#ff5252', 'error': '#ff5252', 'Error': '#ff5252',
        'WARN': '#ff9800', 'warn': '#ff9800', 'Warn': '#ff9800',
        'OK': '#4caf50', 'ok': '#4caf50', 'Ok': '#4caf50',
        'SUCCESS': '#4caf50', 'success': '#4caf50', 'Success': '#4caf50',
        'FAILED': '#ff5252', 'failed': '#ff5252', 'Failed': '#ff5252',
    }
    _light_keywords = {
        'ERROR': '#e74c3c', 'error': '#e74c3c', 'Error': '#e74c3c',
        'WARN': '#f39c12', 'warn': '#f39c12', 'Warn': '#f39c12',
        'OK': '#27ae60', 'ok': '#27ae60', 'Ok': '#27ae60',
        'SUCCESS': '#27ae60', 'success': '#27ae60', 'Success': '#27ae60',
        'FAILED': '#e74c3c', 'failed': '#e74c3c', 'Failed': '#e74c3c',
    }
    # 预编译关键词高亮正则（避免每次调用重复编译）
    _dark_keyword_patterns = {k: re.compile(r'\b' + re.escape(k) + r'\b') for k in _dark_keywords}
    _light_keyword_patterns = {k: re.compile(r'\b' + re.escape(k) + r'\b') for k in _light_keywords}

    def highlight_keywords(self, text):
        # 输出面板始终深色，固定使用深色主题配色
        keywords = self._dark_keywords
        patterns = self._dark_keyword_patterns
        ip_color = '#2196f3'

        replacement = f'<span style="color: {ip_color}">\\g<0></span>'
        text = self._ip_pattern.sub(replacement, text)

        for keyword, color in keywords.items():
            text = patterns[keyword].sub(f'<span style="color: {color}">{keyword}</span>', text)

        text = text.replace('\n', '<br>')
        return text
    
    def load_settings(self):
        if os.path.exists(self.settings_file):
            try:
                with open(self.settings_file, 'r', encoding='utf-8') as f:
                    settings = json.load(f)
                    if 'layout_params' in settings:
                        self.layout_params.update(settings['layout_params'])
                    if 'last_local_dir' in settings:
                        self.last_local_dir = settings['last_local_dir']
            except Exception as e:
                print(f"加载设置失败: {e}")
    
    def save_settings(self):
        try:
            settings = {
                'layout_params': self.layout_params,
                'last_local_dir': self.last_local_dir
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
        
        # 指令按钮面板（默认显示，不需要连接服务器）- 使用滚动区域
        self.command_scroll_area = QScrollArea()
        self.command_scroll_area.setWidgetResizable(True)
        self.command_scroll_area.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.command_scroll_area.setMinimumHeight(100)
        
        self.default_command_panel = QWidget()
        self.default_command_layout = QVBoxLayout()
        # 设置顶对齐
        self.default_command_layout.setAlignment(Qt.AlignTop)
        self.default_command_panel.setObjectName('commandPanel')
        self.default_command_panel.setLayout(self.default_command_layout)
        # 背景色由全局 QSS 通过 #commandPanel 接管
        self.default_command_panel.setStyleSheet('')
        
        self.command_scroll_area.setWidget(self.default_command_panel)
        
        # 刷新默认指令按钮
        self.refresh_default_command_buttons()
        
        # 输出面板 - 改为TabWidget
        self.output_tabs = QTabWidget()
        
        # 服务器返回信息页签 - 使用可拖拽的文本编辑器
        self.server_output = DraggableTextEdit()
        self.server_output.setReadOnly(True)
        self.server_output.setText('系统就绪，等待连接...\n\n提示：可将文件拖拽到此区域上传到服务器当前目录')
        self.server_output.setStyleSheet('background-color: #1e1e1e; color: #ffffff; border: 1px solid #3d3d3d;')
        self.server_output.setAcceptRichText(True)
        self.server_output.setLineWrapMode(QTextEdit.WidgetWidth)
        self.server_output.files_dropped.connect(self.on_files_dropped)
        
        # 指令执行日志页签
        self.command_log = QTextEdit()
        self.command_log.setReadOnly(True)
        self.command_log.setText('指令执行日志:\n')
        self.command_log.setStyleSheet('background-color: #1e1e1e; color: #ffffff; border: 1px solid #3d3d3d;')
        
        # 添加页签
        self.output_tabs.addTab(self.server_output, '服务器返回')
        self.output_tabs.addTab(self.command_log, '执行日志')
        
        # 命令输入框
        self.command_input = CommandLineEdit()
        self.command_input.setPlaceholderText('输入命令后按回车执行 (Tab键自动补全)')
        self.command_input.returnPressed.connect(self.on_command_input_return)
        
        # 禁用Tab键切换焦点，用于自动补全
        self.command_input.setFocusPolicy(Qt.ClickFocus)
        
        # 设置自动补全
        self.setup_command_completer()
        
        # 连接Tab键信号
        self.command_input.tabPressed.connect(self.on_tab_pressed)
        
        # 命令输入框容器
        command_input_widget = QWidget()
        command_input_layout = QVBoxLayout(command_input_widget)
        command_input_layout.setContentsMargins(5, 5, 5, 5)
        command_input_label = QLabel('命令输入:')
        command_input_layout.addWidget(command_input_label)
        command_input_layout.addWidget(self.command_input)
        command_input_widget.setMinimumHeight(70)
        
        # 使用QSplitter分割输出面板和命令输入框
        bottom_splitter = QSplitter(Qt.Vertical)
        bottom_splitter.setFocusPolicy(Qt.NoFocus)
        bottom_splitter.addWidget(self.output_tabs)
        bottom_splitter.addWidget(command_input_widget)
        bottom_splitter.setSizes([self.layout_params['output_panel_height'] - 60, 60])
        
        # 使用QSplitter分割指令面板和输出面板
        right_splitter = QSplitter(Qt.Vertical)
        right_splitter.setFocusPolicy(Qt.NoFocus)
        right_splitter.addWidget(self.command_scroll_area)
        right_splitter.addWidget(bottom_splitter)
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
        
        self.setCentralWidget(central_widget)
        
        # 应用全局浅色样式表
        self.setStyleSheet(LIGHT_QSS)
        
        # 输出面板始终深色（终端风格）
        self.server_output.setStyleSheet('background-color: #1e1e1e; color: #ffffff; border: 1px solid #3d3d3d; border-radius: 0px;')
        self.command_log.setStyleSheet('background-color: #1e1e1e; color: #ffffff; border: 1px solid #3d3d3d; border-radius: 0px;')
        
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
                item.setIcon(create_status_icon('#4caf50'))
            else:
                item.setIcon(create_status_icon('#ff5252'))
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
            server_name = self.server_list_widget.item(current_row).text()
            self.server_manager.remove_server(current_row)
            self.refresh_server_list()
            # 移除对应的服务器页签
            for i in range(self.server_tabs.count()):
                if self.server_tabs.tabText(i) == server_name:
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
            
            connect_action.triggered.connect(lambda: self.connect_server(item.text()))
            disconnect_action.triggered.connect(lambda: self.disconnect_server(item.text()))
            edit_action.triggered.connect(lambda: self.edit_server(self.server_list_widget.row(item)))
            copy_action.triggered.connect(lambda: self.copy_server(self.server_list_widget.row(item)))
            rename_action.triggered.connect(lambda: self.rename_server(self.server_list_widget.row(item)))
            delete_action.triggered.connect(lambda: self.delete_server_by_name(item.text()))
            
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
                    stdin, stdout, stderr = client.exec_command('pwd', timeout=TIMEOUT_EXEC_SHORT)
                    current_dir = stdout.read().decode('utf-8', errors='replace').strip()
                    self.current_dirs[server_name] = current_dir
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 初始化当前目录: {current_dir}")
            else:
                QMessageBox.warning(self, '连接失败', f'无法连接到服务器: {server_name}')
        except Exception as e:
            QMessageBox.warning(self, '连接错误', f'连接服务器时发生错误: {e}')
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 连接服务器时发生错误: {e}")
    
    def disconnect_server(self, server_name):
        self.remove_stop_button()
        self.server_manager.disconnect_server(server_name)
        self.refresh_server_list()
        for i in range(self.server_tabs.count()):
            if self.server_tabs.tabText(i) == server_name:
                self.server_tabs.removeTab(i)
                break
        if server_name in self.server_button_layouts:
            del self.server_button_layouts[server_name]
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
                        output += shell.recv(RECV_CHUNK_SIZE).decode('utf-8', errors='replace')
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
    
    def add_server_tab(self, server_name, switch=True):
        # 检查是否已存在该服务器的页签
        for i in range(self.server_tabs.count()):
            if self.server_tabs.tabText(i) == server_name:
                if switch:
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
        # 背景色由全局 QSS 通过 #commandPanel 接管
        command_buttons_widget.setObjectName('commandPanel')
        command_buttons_widget.setStyleSheet('')
        
        # 存储布局到字典
        self.server_button_layouts[server_name] = command_buttons_layout
        
        # 刷新按钮
        self.refresh_command_buttons(server_name)
        
        tab_layout.addWidget(command_buttons_widget)
        index = self.server_tabs.addTab(tab_widget, server_name)
        if switch:
            self.server_tabs.setCurrentIndex(index)
        
        # 连接服务器后更新文件补全
        self.update_command_completer_with_files()
    
    def _ensure_server_ui_ready(self, server_name):
        """确保服务器在 UI 中已就绪：刷新列表、创建页签（不切换）、初始化当前目录"""
        self.refresh_server_list()
        self.add_server_tab(server_name, switch=False)
        if server_name not in self.current_dirs:
            try:
                client = self.server_manager.get_connection(server_name)
                if client:
                    stdin, stdout, stderr = client.exec_command('pwd', timeout=TIMEOUT_EXEC_SHORT)
                    current_dir = stdout.read().decode('utf-8', errors='replace').strip()
                    self.current_dirs[server_name] = current_dir
            except Exception:
                self.current_dirs[server_name] = '/'
    
    def refresh_command_buttons(self, server_name):
        # 获取对应服务器的布局
        if server_name not in self.server_button_layouts:
            return
        
        layout = self.server_button_layouts[server_name]
        
        # 清空现有按钮
        clear_layout(layout)
        
        # 添加指令按钮
        self.add_command_buttons_to_layout(layout, server_name)
    
    def on_command_input_return(self):
        command = self.command_input.text().strip()
        if not command:
            return
        
        # 获取当前选中的服务器（从server_tabs获取）
        server_name = None
        if self.server_tabs.count() > 0:
            server_name = self.server_tabs.tabText(self.server_tabs.currentIndex())
        
        if not server_name:
            # 尝试从左侧服务器列表获取选中的服务器
            selected_items = self.server_list_widget.selectedItems()
            if selected_items:
                server_name = selected_items[0].text()
        
        if not server_name:
            QMessageBox.warning(self, '未选择服务器', '请先连接或选择一个服务器')
            return
        
        # 检查服务器是否已连接
        if not self.server_manager.is_connected(server_name):
            QMessageBox.warning(self, '未连接', f'服务器 {server_name} 未连接')
            return
        
        # 清空输入框
        self.command_input.clear()
        
        # 构造命令信息
        command_info = {
            'name': command,
            'command': command,
            'params': [],
            'continuous': False
        }
        
        # 执行命令
        self._execute_command_continue(command_info, server_name)
    
    def setup_command_completer(self):
        # 常用 Linux 命令
        common_commands = [
            'ls', 'ls -la', 'ls -l', 'cd', 'pwd', 'mkdir', 'rm', 'rm -rf',
            'cp', 'mv', 'cat', 'tail', 'tail -f', 'tailf', 'head',
            'grep', 'find', 'chmod', 'chown', 'ps', 'ps aux', 'top',
            'kill', 'kill -9', 'df', 'df -h', 'du', 'du -sh',
            'tar', 'tar -czvf', 'tar -xzvf', 'zip', 'unzip',
            'wget', 'curl', 'ping', 'netstat', 'netstat -tlnp',
            'ifconfig', 'ip addr', 'systemctl', 'systemctl status',
            'journalctl', 'journalctl -f', 'docker', 'docker ps',
            'docker logs', 'docker exec', 'kubectl', 'kubectl get',
            'kubectl logs', 'kubectl exec', 'vim', 'nano', 'less',
            'more', 'echo', 'touch', 'ln', 'scp', 'rsync',
            'apt-get', 'apt-get update', 'apt-get install', 'apt-get upgrade',
            'yum', 'yum install', 'yum update', 'yum upgrade',
            'service', 'chkconfig', 'crontab', 'at', 'nohup',
            'screen', 'tmux', 'htop', 'iotop', 'nethogs', 'strace',
            'lsof', 'ss', 'nc', 'telnet', 'ssh', 'sftp', 'ftp',
            'mysql', 'psql', 'redis-cli', 'mongo', 'nginx', 'apache2'
        ]
        
        # 创建自动补全器
        completer = QCompleter(common_commands)
        completer.setCaseSensitivity(Qt.CaseInsensitive)
        completer.setFilterMode(Qt.MatchContains)
        self.command_input.setCompleter(completer)
        self.command_completer = completer
        self.command_completer_model = common_commands
    
    def update_command_completer_with_files(self):
        """获取当前服务器的文件列表并更新补全器"""
        # 获取当前选中的服务器
        server_name = None
        if self.server_tabs.count() > 0:
            server_name = self.server_tabs.tabText(self.server_tabs.currentIndex())
        
        if not server_name or not self.server_manager.is_connected(server_name):
            return
        
        # 获取当前目录
        current_dir = self.current_dirs.get(server_name, "/")
        
        # 执行 ls 命令获取文件列表
        client = self.server_manager.get_connection(server_name)
        if not client:
            return
        
        try:
            safe_dir = current_dir.replace('"', '\\"')
            stdin, stdout, stderr = client.exec_command(f'ls -la "{safe_dir}"', timeout=TIMEOUT_EXEC_MEDIUM)
            output = stdout.read().decode('utf-8', errors='replace')
            
            # 解析文件列表
            files = []
            for line in output.split('\n')[1:]:  # 跳过第一行（total）
                if not line.strip():
                    continue
                parts = line.split()
                if len(parts) >= 9:
                    filename = parts[-1]
                    # 排除 . 和 ..
                    if filename not in ['.', '..']:
                        # 如果是目录，添加 /
                        if parts[0].startswith('d'):
                            filename += '/'
                        files.append(filename)
            
            # 更新补全器
            if files:
                all_commands = list(set(self.command_completer_model + files))
                all_commands.sort()
                self.command_completer.setModel(None)
                self.command_completer_model = all_commands
                self.command_completer.setModel(QStringListModel(all_commands))
        except Exception:
            pass
    
    def refresh_default_command_buttons(self):
        # 清空现有按钮
        clear_layout(self.default_command_layout)
        
        # 添加指令按钮
        self.add_command_buttons_to_layout(self.default_command_layout, None)
    
    def add_command_buttons_to_layout(self, layout, server_name):
        # 清空现有内容
        clear_layout(layout)
        
        # 创建一个主容器widget来容纳所有按钮
        main_container = QWidget()
        main_layout = QVBoxLayout()
        main_layout.setAlignment(Qt.AlignTop)
        main_layout.setSpacing(0)
        main_layout.setContentsMargins(12, 12, 12, 12)
        main_container.setLayout(main_layout)
        
        # 指令按钮面板样式
        main_container.setStyleSheet('''
            QLabel {
                color: #1a1a1a;
                font-weight: bold;
                font-size: 14px;
                padding-left: 8px;
                border-left: 3px solid #1890ff;
                margin-top: 16px;
                margin-bottom: 10px;
            }
            QPushButton {
                background-color: #f8f9fa;
                color: #333333;
                border: 0.5px solid #e0e0e0;
                border-radius: 8px;
                padding: 5px 10px;
                font-size: 12px;
            }
            QPushButton:hover {
                background-color: #e6f7ff;
                border-color: #1890ff;
                color: #1890ff;
            }
            QPushButton:pressed {
                background-color: #bae0ff;
            }
        ''')
        
        # 添加指令按钮
        for i, category in enumerate(self.command_manager.commands):
            category_label = QLabel(category['name'])
            category_label.setFont(QFont('Arial', self.layout_params['category_font_size'], QFont.Bold))
            main_layout.addWidget(category_label)
            
            # 创建网格布局，一行最多6个按钮
            grid_layout = QGridLayout()
            grid_layout.setContentsMargins(0, 0, 0, 0)
            grid_layout.setSpacing(self.layout_params['button_spacing'])
            grid_layout.setAlignment(Qt.AlignLeft)
            row = 0
            col = 0
            
            for command in category['commands']:
                button = QPushButton(command['name'])
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
    
    def find_linked_command(self, linked_spec):
        """根据关联指令配置查找对应的指令信息"""
        if not linked_spec or not isinstance(linked_spec, dict):
            return None
        target_category = linked_spec.get('category')
        target_name = linked_spec.get('name')
        if not target_category or not target_name:
            return None
        for category in self.command_manager.commands:
            if category.get('name') == target_category:
                for command in category.get('commands', []):
                    if command.get('name') == target_name:
                        return command
        return None

    def execute_command(self, server_name, command_info, from_linked=False):
        # 仅主指令可切换目标服务器，关联指令继承主指令解析后的服务器
        if not from_linked:
            target = command_info.get('target_server')
            if target:
                server_name = target
                if not self.server_manager.ensure_connection(server_name):
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 错误: 无法连接到目标服务器 {server_name}")
                    return
                self._ensure_server_ui_ready(server_name)
        
        # 处理前置关联指令（仅主指令触发，避免递归）
        if not from_linked and command_info.get('linked_enabled'):
            linked_spec = command_info.get('linked_command')
            linked_cmd = self.find_linked_command(linked_spec) if linked_spec else None
            if linked_cmd:
                delay = command_info.get('linked_delay', 0)
                # 先执行关联指令（标记为 from_linked=True，防止递归触发关联）
                self.execute_command(server_name, linked_cmd, from_linked=True)
                # 延迟后执行自身指令
                QTimer.singleShot(delay, lambda: self._execute_command_main(server_name, command_info))
                return
            else:
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 警告: 未找到关联指令，继续执行当前指令")
        
        self._execute_command_main(server_name, command_info)
    
    def _execute_command_main(self, server_name, command_info):
        """执行指令的主体逻辑（连接检查、持续运行冲突检查等）"""
        command = command_info['command']
        self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 执行命令: {command}")
        
        if not self.server_manager.is_connection_alive(server_name):
            self.remove_stop_button()
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 检测到连接已断开，尝试重新连接...")
            self.refresh_server_list()
            if not self.server_manager.ensure_connection(server_name):
                QMessageBox.warning(self, '连接失败', f'服务器 {server_name} 连接已断开且无法重新连接')
                self.command_log.append(f"  错误: 无法重新连接到服务器 {server_name}")
                return
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 重新连接成功")
            self.refresh_server_list()
        
        client = self.server_manager.get_connection(server_name)
        if not client:
            QMessageBox.warning(self, '未连接', f'服务器 {server_name} 未连接')
            self.command_log.append(f"  错误: 服务器 {server_name} 未连接")
            return
        
        # 检查是否有持续运行的指令（只对持续输出指令弹窗）
        is_current_continuous = hasattr(self, 'current_runnable') and self.current_runnable and self.current_runnable.is_running and getattr(self.current_runnable, 'is_continuous', False)
        if is_current_continuous:
            reply = QMessageBox.question(
                self,
                '指令正在运行',
                '当前有指令正在运行中，是否立即停止当前指令并执行新指令？',
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No
            )
            if reply == QMessageBox.Yes:
                self.current_runnable.stop()
                self.remove_stop_button()
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 用户停止当前指令，准备执行新指令")
                # 使用QTimer延迟执行新指令，避免阻塞GUI
                QTimer.singleShot(200, lambda: self._execute_command_continue(command_info, server_name))
                return
            else:
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 用户取消执行新指令")
                return
        
        self._execute_command_continue(command_info, server_name)
    
    def _execute_command_continue(self, command_info, server_name):
        client = self.server_manager.get_connection(server_name)
        if not client:
            QMessageBox.warning(self, '未连接', f'服务器 {server_name} 未连接')
            self.command_log.append(f"  错误: 服务器 {server_name} 未连接")
            return
        
        command = command_info['command']
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
                
                # 提交任务到线程池
                is_continuous = command_info.get('continuous', False)
                
                self.command_log.append(f"  提交命令到线程池: {command}")
                runnable = CommandRunnable(client, command, self.command_log, server_name, self.server_manager, self.current_dirs, is_continuous)
                
                self.current_runnable = runnable
                
                if is_continuous:
                    self.remove_stop_button()
                    self.stop_button = QPushButton(f'停止命令 ({server_name})')
                    self.stop_button.clicked.connect(lambda checked, r=runnable: r.stop())
                    self.stop_button_layout.addWidget(self.stop_button)
                
                def on_command_result(result):
                    self.command_log.append(f"  收到命令执行结果")
                    highlighted_text = self.highlight_keywords(result)
                    self.append_output(highlighted_text)
                    self.command_log.append("  执行完成")
                    self.remove_stop_button()
                
                def on_partial_result(partial):
                    highlighted_text = self.highlight_keywords(partial)
                    self.append_output(highlighted_text)
                
                def on_finished():
                    self.command_log.append("  命令执行完成")
                    self.remove_stop_button()
                
                def on_current_dir_updated(server_name, current_dir):
                    self.current_dirs[server_name] = current_dir
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 更新当前目录: {current_dir}")
                    # 更新文件补全
                    self.update_command_completer_with_files()
                
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
        # 如果指令配置了目标服务器，优先定向执行
        target = command_info.get('target_server')
        if target:
            if not self.server_manager.ensure_connection(target):
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 错误: 无法连接到目标服务器 {target}")
                return
            self.execute_command(target, command_info)
            return
        
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
        if not self.server_manager.is_connection_alive(server_name):
            self.remove_stop_button()
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 检测到连接已断开，尝试重新连接...")
            self.refresh_server_list()
            if not self.server_manager.ensure_connection(server_name):
                self.append_output("无法重新连接服务器<br>")
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 下载文件失败: 无法重新连接服务器")
                return
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 重新连接成功")
            self.refresh_server_list()
        
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
                try:
                    sftp.stat(file_path)
                    self.append_output(f"文件存在: {file_path}<br>")
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 文件存在: {file_path}")
                except Exception as stat_error:
                    error_msg = f"文件不存在: {file_path} ({stat_error})"
                    self.append_output(f"{error_msg}<br>")
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {error_msg}")
                    return

                from PyQt5.QtWidgets import QFileDialog
                file_name = posixpath.basename(file_path)
                default_dir = self.last_local_dir if self.last_local_dir and os.path.exists(self.last_local_dir) else os.getcwd()
                local_path, _ = QFileDialog.getSaveFileName(
                    self, "保存文件", os.path.join(default_dir, file_name), "All Files (*)"
                )

                if local_path:
                    self.last_local_dir = os.path.dirname(local_path)
                    self.save_settings()
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
            finally:
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
                            pwd_output = ""
                            attempt = 0
                            while attempt < RECV_MAX_ATTEMPTS:
                                time.sleep(RECV_SHELL_DELAY)
                                if shell.recv_ready():
                                    pwd_output += shell.recv(RECV_CHUNK_SIZE).decode('utf-8', errors='replace')
                                    attempt = 0
                                else:
                                    attempt += 1

                            current_dir = parse_pwd_output(pwd_output)
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 当前目录: {current_dir}")
                        except Exception as e:
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 获取目录失败: {e}")
                            current_dir = "/"
                    else:
                        # 没有shell会话，使用exec_command
                        try:
                            stdin, stdout, stderr = client.exec_command('pwd', timeout=TIMEOUT_EXEC_SHORT)
                            current_dir = stdout.read().decode('utf-8', errors='replace').strip()
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 从exec_command获取当前目录: {current_dir}")
                        except Exception as e:
                            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 获取目录失败: {e}")
                            current_dir = "/"
                
                # 构建完整的文件路径，确保使用正斜杠
                file_path = current_dir.rstrip('/') + '/' + file_name.lstrip('/')
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 构建完整文件路径: {file_path}")
            # 执行下载
            self.download_file(server_name, file_path)
    
    def get_current_directory(self, server_name, client):
        if server_name in self.current_dirs:
            return self.current_dirs[server_name]

        shell = self.server_manager.get_shell(server_name)
        current_dir = "/"

        if shell:
            try:
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 从shell获取当前目录")
                shell.send('pwd\n')
                pwd_output = ""
                attempt = 0
                while attempt < RECV_MAX_ATTEMPTS:
                    time.sleep(RECV_SHELL_DELAY)
                    if shell.recv_ready():
                        pwd_output += shell.recv(RECV_CHUNK_SIZE).decode('utf-8', errors='replace')
                        attempt = 0
                    else:
                        attempt += 1

                current_dir = parse_pwd_output(pwd_output)
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 当前目录: {current_dir}")
            except Exception as e:
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 获取目录失败: {e}")
                current_dir = "/"
        else:
            try:
                stdin, stdout, stderr = client.exec_command('pwd', timeout=TIMEOUT_EXEC_SHORT)
                current_dir = stdout.read().decode('utf-8', errors='replace').strip()
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 从exec_command获取当前目录: {current_dir}")
            except Exception as e:
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 获取目录失败: {e}")
                current_dir = "/"

        return current_dir

    def upload_file(self, server_name):
        if not self.server_manager.is_connection_alive(server_name):
            self.remove_stop_button()
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 检测到连接已断开，尝试重新连接...")
            self.refresh_server_list()
            if not self.server_manager.ensure_connection(server_name):
                self.append_output("无法重新连接服务器<br>")
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 上传文件失败: 无法重新连接服务器")
                return
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 重新连接成功")
            self.refresh_server_list()
        
        client = self.server_manager.get_connection(server_name)
        if not client:
            self.append_output("无法获取服务器连接<br>")
            return
        
        try:
            from PyQt5.QtWidgets import QFileDialog
            default_dir = self.last_local_dir if self.last_local_dir and os.path.exists(self.last_local_dir) else os.getcwd()
            local_path, _ = QFileDialog.getOpenFileName(
                self, "选择要上传的文件", default_dir, "All Files (*)"
            )
            
            if local_path:
                self.last_local_dir = os.path.dirname(local_path)
                self.save_settings()
                sftp = client.open_sftp()
                try:
                    current_dir = self.get_current_directory(server_name, client)
                    self.append_output(f"当前服务器目录: {current_dir}<br>")
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 使用当前目录: {current_dir}")

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
    
    def on_files_dropped(self, files):
        connected_servers = [server['name'] for server in self.server_manager.servers if self.server_manager.is_connected(server['name'])]
        
        if not connected_servers:
            QMessageBox.warning(self, '未连接服务器', '请先连接至少一个服务器')
            return
        
        current_tab_index = self.server_tabs.currentIndex()
        if current_tab_index >= 0:
            server_name = self.server_tabs.tabText(current_tab_index)
        else:
            from PyQt5.QtWidgets import QInputDialog
            server_name, ok = QInputDialog.getItem(self, '选择服务器', '请选择要上传文件的服务器:', connected_servers, 0, False)
            if not (ok and server_name):
                return
        
        if not self.server_manager.is_connection_alive(server_name):
            self.remove_stop_button()
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 检测到连接已断开，尝试重新连接...")
            self.refresh_server_list()
            if not self.server_manager.ensure_connection(server_name):
                self.append_output("无法重新连接服务器<br>")
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 上传文件失败: 无法重新连接服务器")
                return
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 重新连接成功")
            self.refresh_server_list()
        
        client = self.server_manager.get_connection(server_name)
        if not client:
            self.append_output("无法获取服务器连接<br>")
            return
        
        current_dir = self.get_current_directory(server_name, client)
        
        try:
            sftp = client.open_sftp()
            try:
                success_count = 0
                fail_count = 0

                for local_path in files:
                    file_name = os.path.basename(local_path)
                    remote_path = current_dir.rstrip('/') + '/' + file_name

                    self.append_output(f"正在上传: {file_name} -> {remote_path}<br>")
                    self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 拖拽上传: {local_path} -> {remote_path}")

                    try:
                        sftp.put(local_path, remote_path)
                        self.append_output(f"上传成功: {file_name}<br>")
                        self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 上传成功: {file_name}")
                        success_count += 1
                    except Exception as e:
                        self.append_output(f"上传失败: {file_name} - {e}<br>")
                        self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 上传失败: {file_name} - {e}")
                        fail_count += 1

                self.append_output(f"<br>上传完成: 成功 {success_count} 个，失败 {fail_count} 个<br>")
                self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 批量上传完成: 成功 {success_count}，失败 {fail_count}")
            finally:
                sftp.close()
            
        except Exception as e:
            self.append_output(f"上传过程出错: {e}<br>")
            self.command_log.append(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] 上传过程出错: {e}")
    
    def add_category(self):
        category_name, ok = QInputDialog.getText(self, '添加分类', '分类名称:')
        if ok and category_name:
            self.command_manager.add_category(category_name)
            self.refresh_command_tree()
            # 刷新默认指令按钮面板
            self.refresh_default_command_buttons()
    
    def add_command(self):
        dialog = CommandDialog(command_manager=self.command_manager, server_manager=self.server_manager, parent=self)
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
            dialog = CommandDialog(command_info, command_manager=self.command_manager, server_manager=self.server_manager, parent=self)
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
        dialog = CommandDialog(command_info, command_manager=self.command_manager, server_manager=self.server_manager, parent=self)
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
        dialog = CommandDialog(command_manager=self.command_manager, server_manager=self.server_manager, parent=self)
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
        server_name = item.text()
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
        self.remove_stop_button()
        if index >= 0:
            server_name = self.server_tabs.tabText(index)
            self.server_output.clear()
            self.server_output.append(f'已切换到服务器: {server_name}')
            
            # 更新文件补全
            self.update_command_completer_with_files()
            
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
                        stdin, stdout, stderr = client.exec_command('pwd', timeout=TIMEOUT_EXEC_SHORT)
                        current_dir = stdout.read().decode('utf-8', errors='replace').strip()
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
