import sys
import socket
import threading
import time
import logging
import traceback
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
                             QPushButton, QLabel, QLineEdit, QTextEdit, QListWidget, 
                             QMessageBox, QFrame, QListWidgetItem)
from PyQt5.QtCore import Qt, pyqtSignal, QObject
from PyQt5.QtGui import QPainter, QColor, QFont, QPen, QBrush
import pickle
import struct
import random

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MessageType:
    AUTH = "auth"
    MOVE = "move"
    GAME_STATE = "game_state"
    CHAT = "chat"
    DISCONNECT = "disconnect"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    CREATE_ROOM = "create_room"
    JOIN_ROOM = "join_room"
    LEAVE_ROOM = "leave_room"
    ROOM_LIST = "room_list"
    ROOM_JOINED = "room_joined"
    START_GAME = "start_game"
    GAME_STARTED = "game_started"
    GAME_OVER = "game_over"
    RESTART_GAME = "restart_game"

class NetworkManager(QObject):
    message_received = pyqtSignal(dict)
    connected = pyqtSignal()
    disconnected = pyqtSignal()
    error_occurred = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.socket = None
        self.running = False
        self.host = "localhost"
        self.port = 8888
        self.player_id = None
        self.username = ""
        self.last_move_time = 0
        self.move_cooldown = 0.1

    def connect_to_server(self, host, port, username):
        try:
            if self.socket:
                try:
                    self.socket.close()
                except:
                    pass
                self.socket = None

            self.host = host
            self.port = port
            self.username = username

            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(5.0)
            self.socket.connect((host, port))

            auth_msg = self.create_message(MessageType.AUTH, "client", username)
            if not self.send_message(auth_msg):
                return False

            response = self.receive_message(timeout=10)

            if not response:
                return False

            if response.get('type') == MessageType.AUTH and response.get('data', {}).get('status') == 'success':
                self.player_id = response['data'].get('player_id')
                self.running = True
                self.connected.emit()

                thread = threading.Thread(target=self.listen_loop, daemon=True)
                thread.start()
                return True
            else:
                error_msg = response.get('data', 'Ошибка аутентификации')
                self.error_occurred.emit(str(error_msg))
                return False

        except socket.timeout:
            self.error_occurred.emit("Таймаут подключения к серверу")
            return False
        except ConnectionRefusedError:
            self.error_occurred.emit("Сервер недоступен (соединение отказано)")
            return False
        except Exception as e:
            self.error_occurred.emit(f"Ошибка подключения: {str(e)}")
            logger.error(f"Ошибка подключения: {traceback.format_exc()}")
            return False

    def listen_loop(self):
        while self.running:
            try:
                message = self.receive_message(timeout=1.0)
                if message:
                    self.message_received.emit(message)

                if not self.socket:
                    break

            except Exception as e:
                if self.running:
                    logger.error(f"Критическая ошибка в listen_loop: {traceback.format_exc()}")
                break

        if self.running:
            self.running = False
            self.disconnected.emit()

    def create_message(self, msg_type, from_user, data=None):
        return {
            'type': msg_type,
            'from_user': from_user,
            'data': data,
            'timestamp': time.time()
        }

    def send_message(self, message):
        try:
            if not self.socket:
                logger.warning("Сокет не существует")
                return False

            try:
                self.socket.getpeername()
            except (OSError, socket.error):
                logger.warning("Сокет разорван")
                self.running = False
                self.disconnected.emit()
                return False

            data = pickle.dumps(message)
            length_prefix = struct.pack('!I', len(data))
            self.socket.sendall(length_prefix + data)
            return True

        except Exception as e:
            logger.error(f"Ошибка отправки: {traceback.format_exc()}")
            self.running = False
            self.disconnected.emit()
            return False

    def receive_message(self, timeout=1.0):
        try:
            if not self.socket:
                return None

            self.socket.settimeout(timeout)

            try:
                self.socket.getpeername()
            except (OSError, socket.error):
                logger.warning("Сокет разорван при получении сообщения")
                return None

            length_data = self.socket.recv(4)

            if not length_data:
                logger.info("Соединение разорвано сервером (пустые данные)")
                return None

            length = struct.unpack('!I', length_data)[0]

            if length > 10 * 1024 * 1024:
                logger.error(f"Слишком большое сообщение: {length} байт")
                return None

            received = 0
            chunks = []

            while received < length:
                chunk = self.socket.recv(min(4096, length - received))

                if not chunk:
                    logger.warning("Неполное сообщение от сервера")
                    return None

                chunks.append(chunk)
                received += len(chunk)

            data = b''.join(chunks)
            return pickle.loads(data)

        except socket.timeout:
            return None
        except ConnectionResetError:
            logger.info("Соединение разорвано сервером")
            self.running = False
            self.disconnected.emit()
            return None
        except Exception as e:
            logger.error(f"Ошибка получения сообщения: {traceback.format_exc()}")
            self.running = False
            self.disconnected.emit()
            return None

    def send_chat(self, message):
        msg = self.create_message(MessageType.CHAT, self.player_id, message)
        return self.send_message(msg)

    def send_move(self, direction):
        current_time = time.time()
        if current_time - self.last_move_time < self.move_cooldown:
            return False
        
        self.last_move_time = current_time
        
        try:
            msg = self.create_message(MessageType.MOVE, self.player_id, direction)
            return self.send_message(msg)
        except Exception as e:
            logger.error(f"Ошибка отправки движения: {traceback.format_exc()}")
            return False

    def send_message_type(self, message_type, data=None):
        msg = self.create_message(message_type, self.player_id, data)
        return self.send_message(msg)

    def disconnect(self):
        self.running = False
        self.player_id = None
        self.username = ""

        if self.socket:
            try:
                msg = self.create_message(MessageType.DISCONNECT, self.player_id)
                self.send_message(msg)
            except:
                pass

            try:
                self.socket.shutdown(socket.SHUT_RDWR)
            except:
                pass

            try:
                self.socket.close()
            except:
                pass

            self.socket = None

        self.disconnected.emit()

class GameWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setMinimumSize(600, 450)
        self.cell_size = 15
        self.game_data = None
        self.grid_size = (40, 30)
        self.setFocusPolicy(Qt.StrongFocus)
        self.setMouseTracking(True)

    def mousePressEvent(self, event):
        self.setFocus()
        logger.info("Фокус установлен по клику мыши")

    def enterEvent(self, event):
        self.setStyleSheet("border: 2px solid #4CAF50;")

    def leaveEvent(self, event):
        self.setStyleSheet("border: none;")

    def update_game_data(self, game_data):
        self.game_data = game_data
        if game_data:
            self.grid_size = game_data.get('grid_size', (40, 30))
        self.update()

    def paintEvent(self, event):
        if not self.game_data:
            painter = QPainter(self)
            painter.fillRect(self.rect(), QColor(240, 240, 240))
            painter.setPen(QColor(100, 100, 100))
            painter.setFont(QFont("Arial", 16))
            painter.drawText(self.rect(), Qt.AlignCenter, "Ожидание данных игры...")
            return

        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)
        painter.fillRect(self.rect(), QColor(240, 240, 240))

        if self.hasFocus():
            painter.setPen(QPen(QColor(76, 175, 80), 3))
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))
        else:
            painter.setPen(QPen(QColor(200, 200, 200), 1))
            painter.drawRect(self.rect().adjusted(1, 1, -1, -1))

        grid_width = self.grid_size[0] * self.cell_size
        grid_height = self.grid_size[1] * self.cell_size
        offset_x = (self.width() - grid_width) // 2
        offset_y = (self.height() - grid_height) // 2

        painter.setPen(QPen(QColor(0, 0, 0), 2))
        painter.drawRect(offset_x, offset_y, grid_width, grid_height)

        painter.setPen(QPen(QColor(220, 220, 220), 1))
        for x in range(self.grid_size[0] + 1):
            painter.drawLine(offset_x + x * self.cell_size, offset_y,
                            offset_x + x * self.cell_size, offset_y + grid_height)

        for y in range(self.grid_size[1] + 1):
            painter.drawLine(offset_x, offset_y + y * self.cell_size,
                            offset_x + grid_width, offset_y + y * self.cell_size)

        food_positions = self.game_data.get('food', [])
        painter.setBrush(QBrush(QColor(255, 107, 107)))
        for food in food_positions:
            x, y = food
            painter.drawEllipse(offset_x + x * self.cell_size + 2,
                               offset_y + y * self.cell_size + 2,
                               self.cell_size - 4, self.cell_size - 4)

        snakes = self.game_data.get('snakes', {})
        for snake_data in snakes.values():
            if not snake_data.get('alive', True):
                continue

            color = QColor(snake_data.get('color', '#00FF00'))
            body = snake_data.get('body', [])

            painter.setBrush(QBrush(color))
            painter.setPen(QPen(QColor(0, 0, 0), 1))

            for i, (x, y) in enumerate(body):
                if i == 0:
                    painter.setBrush(QBrush(color.darker(150)))
                else:
                    painter.setBrush(QBrush(color))

                painter.drawRect(offset_x + x * self.cell_size + 1,
                                offset_y + y * self.cell_size + 1,
                                self.cell_size - 2, self.cell_size - 2)

        winner = self.game_data.get('winner')
        if winner and not self.game_data.get('game_active', True):
            painter.fillRect(self.rect(), QColor(0, 0, 0, 180))
            painter.setPen(QPen(QColor(255, 255, 255)))
            painter.setFont(QFont("Arial", 24, QFont.Bold))

            if winner.get('draw'):
                text = "НИЧЬЯ"
                subtext = "Все игроки погибли одновременно"
            elif winner.get('single_player'):
                text = "ИГРА ОКОНЧЕНА"
                subtext = f"Ваш счет: {winner.get('score', 0)}"
            else:
                text = f"ПОБЕДИТЕЛЬ: {winner.get('winner_name', '---')}"
                subtext = f"Счет: {winner.get('score', 0)}"

            text_rect = self.rect()
            text_rect.setHeight(text_rect.height() // 2)
            painter.drawText(text_rect, Qt.AlignCenter, text)

            painter.setFont(QFont("Arial", 16, QFont.Normal))
            subtext_rect = self.rect()
            subtext_rect.setTop(text_rect.bottom())
            painter.drawText(subtext_rect, Qt.AlignCenter, subtext)

            painter.setFont(QFont("Arial", 14, QFont.Normal))
            timer_rect = self.rect()
            timer_rect.setTop(subtext_rect.bottom() + 20)
            painter.drawText(timer_rect, Qt.AlignCenter, "Новая игра через 3 секунды...")

class SnakeClient(QMainWindow):
    def __init__(self):
        super().__init__()
        self.network = NetworkManager()
        self.current_room = None
        self.current_room_info = None
        self.rooms_list = []
        self.is_room_creator = False
        self.init_ui()
        self.connect_signals()

    def init_ui(self):
        self.setWindowTitle("Онлайн Змейка - Клиент")
        self.setGeometry(100, 100, 1200, 700)

        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        left_widget = QWidget()
        left_layout = QVBoxLayout(left_widget)

        self.game_widget = GameWidget(self)
        left_layout.addWidget(self.game_widget)

        info_layout = QHBoxLayout()
        self.status_label = QLabel("Не подключено")
        self.status_label.setStyleSheet("padding: 10px; background: #f0f0f0; border: 1px solid #ccc; font-size: 14px;")
        
        self.room_label = QLabel("Комната: Лобби")
        self.room_label.setStyleSheet("padding: 10px; background: #e0e0ff; border: 1px solid #ccc; font-size: 14px;")

        info_layout.addWidget(self.status_label, 2)
        info_layout.addWidget(self.room_label, 1)
        left_layout.addLayout(info_layout)

        chat_frame = QFrame()
        chat_frame.setFrameStyle(QFrame.Box)
        chat_layout = QVBoxLayout(chat_frame)
        chat_layout.addWidget(QLabel("Чат"))

        self.chat_display = QTextEdit()
        self.chat_display.setMaximumHeight(150)
        self.chat_display.setReadOnly(True)

        chat_input_layout = QHBoxLayout()
        self.chat_input = QLineEdit()
        self.chat_input.setPlaceholderText("Введите сообщение...")
        self.chat_input.returnPressed.connect(self.send_chat)

        self.chat_send_button = QPushButton("➤")
        self.chat_send_button.clicked.connect(self.send_chat)
        self.chat_send_button.setFixedWidth(40)

        chat_input_layout.addWidget(self.chat_input)
        chat_input_layout.addWidget(self.chat_send_button)

        chat_layout.addWidget(self.chat_display)
        chat_layout.addLayout(chat_input_layout)

        left_layout.addWidget(chat_frame)

        right_widget = QWidget()
        right_layout = QVBoxLayout(right_widget)
        right_widget.setMaximumWidth(400)

        connection_frame = QFrame()
        connection_frame.setFrameStyle(QFrame.Box)
        connection_layout = QVBoxLayout(connection_frame)
        connection_layout.addWidget(QLabel("Подключение"))

        self.server_input = QLineEdit("localhost")
        self.port_input = QLineEdit("8888")
        self.username_input = QLineEdit(f"Player_{random.randint(1, 1000)}")

        self.connect_button = QPushButton("Подключиться")
        self.connect_button.clicked.connect(self.connect_to_server)

        self.disconnect_button = QPushButton("Отключиться")
        self.disconnect_button.clicked.connect(self.disconnect_from_server)
        self.disconnect_button.setEnabled(False)

        connection_layout.addWidget(QLabel("Сервер:"))
        connection_layout.addWidget(self.server_input)
        connection_layout.addWidget(QLabel("Порт:"))
        connection_layout.addWidget(self.port_input)
        connection_layout.addWidget(QLabel("Имя игрока:"))
        connection_layout.addWidget(self.username_input)
        connection_layout.addWidget(self.connect_button)
        connection_layout.addWidget(self.disconnect_button)

        control_frame = QFrame()
        control_frame.setFrameStyle(QFrame.Box)
        control_layout = QVBoxLayout(control_frame)
        control_layout.addWidget(QLabel("Управление"))

        self.up_button = QPushButton("Вверх")
        self.down_button = QPushButton("Вниз")
        self.left_button = QPushButton("Влево")
        self.right_button = QPushButton("Вправо")

        self.up_button.clicked.connect(lambda: self.send_move("UP"))
        self.down_button.clicked.connect(lambda: self.send_move("DOWN"))
        self.left_button.clicked.connect(lambda: self.send_move("LEFT"))
        self.right_button.clicked.connect(lambda: self.send_move("RIGHT"))

        control_layout.addWidget(self.up_button)
        control_layout.addWidget(self.down_button)
        control_layout.addWidget(self.left_button)
        control_layout.addWidget(self.right_button)

        self.start_game_button = QPushButton("Начать игру")
        self.start_game_button.clicked.connect(self.start_game)
        self.start_game_button.setStyleSheet("""
            QPushButton {
                background-color: #FF6B6B;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #FF5252;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)

        control_layout.addWidget(self.start_game_button)

        self.restart_game_button = QPushButton("Перезапустить")
        self.restart_game_button.clicked.connect(self.restart_game)
        self.restart_game_button.setStyleSheet("""
            QPushButton {
                background-color: #4CAF50;
                color: white;
                font-weight: bold;
                font-size: 14px;
                padding: 10px;
            }
            QPushButton:hover {
                background-color: #45a049;
            }
            QPushButton:disabled {
                background-color: #cccccc;
            }
        """)

        control_layout.addWidget(self.restart_game_button)

        rooms_frame = QFrame()
        rooms_frame.setFrameStyle(QFrame.Box)
        rooms_layout = QVBoxLayout(rooms_frame)
        rooms_layout.addWidget(QLabel("Комнаты"))

        create_room_layout = QHBoxLayout()
        self.room_name_input = QLineEdit()
        self.room_name_input.setPlaceholderText("Имя комнаты...")
        self.create_room_button = QPushButton("Создать")
        self.create_room_button.clicked.connect(self.create_room)

        create_room_layout.addWidget(self.room_name_input)
        create_room_layout.addWidget(self.create_room_button)
        rooms_layout.addLayout(create_room_layout)

        rooms_layout.addWidget(QLabel("Доступные комнаты:"))

        self.rooms_list_widget = QListWidget()
        self.rooms_list_widget.itemDoubleClicked.connect(self.join_selected_room)

        self.refresh_rooms_button = QPushButton("Обновить список")
        self.refresh_rooms_button.clicked.connect(self.refresh_rooms)

        self.leave_room_button = QPushButton("Покинуть комнату")
        self.leave_room_button.clicked.connect(self.leave_room)

        rooms_layout.addWidget(self.rooms_list_widget)
        rooms_layout.addWidget(self.refresh_rooms_button)
        rooms_layout.addWidget(self.leave_room_button)

        right_layout.addWidget(connection_frame)
        right_layout.addWidget(control_frame)
        right_layout.addWidget(rooms_frame)
        right_layout.addStretch()

        main_layout.addWidget(left_widget, 3)
        main_layout.addWidget(right_widget, 1)

        self.set_controls_enabled(False)
        self.update_start_game_button()

        self.setStyleSheet("""
            QMainWindow { background-color: #f5f5f5; }
            QPushButton {
                background-color: #4CAF50;
                color: white;
                border: none;
                padding: 8px;
                border-radius: 4px;
                margin: 2px;
            }
            QPushButton:hover { background-color: #45a049; }
            QPushButton:disabled { background-color: #cccccc; }
            QFrame {
                background-color: white;
                border-radius: 5px;
                padding: 10px;
                margin: 2px;
            }
            QLineEdit, QTextEdit, QListWidget {
                border: 1px solid #ccc;
                border-radius: 3px;
                padding: 5px;
            }
        """)

    def connect_signals(self):
        self.network.connected.connect(self.on_connected)
        self.network.disconnected.connect(self.on_disconnected)
        self.network.error_occurred.connect(self.on_error)
        self.network.message_received.connect(self.on_message_received)

    def set_controls_enabled(self, enabled):
        controls = [self.up_button, self.down_button, self.left_button, self.right_button,
                   self.chat_input, self.chat_send_button, self.create_room_button,
                   self.refresh_rooms_button, self.leave_room_button, self.room_name_input]

        for control in controls:
            control.setEnabled(enabled)

    def update_start_game_button(self):
        if not self.current_room_info or not self.is_room_creator:
            self.start_game_button.setEnabled(False)
            self.restart_game_button.setEnabled(False)
        else:
            if self.current_room_info.get('game_active', False):
                self.start_game_button.setEnabled(False)
                self.restart_game_button.setEnabled(True)
            else:
                self.start_game_button.setEnabled(True)
                self.restart_game_button.setEnabled(False)

    def connect_to_server(self):
        host = self.server_input.text()

        try:
            port = int(self.port_input.text())
        except ValueError:
            QMessageBox.warning(self, "Ошибка", "Порт должен быть числом")
            return

        username = self.username_input.text().strip()

        if not username:
            QMessageBox.warning(self, "Ошибка", "Введите имя игрока")
            return

        self.current_room = None
        self.is_room_creator = False
        self.current_room_info = None
        self.rooms_list_widget.clear()
        self.game_widget.update_game_data(None)
        self.status_label.setText("Подключение...")
        self.connect_button.setEnabled(False)

        def connect_thread():
            success = self.network.connect_to_server(host, port, username)
            if not success:
                self.connect_button.setEnabled(True)

        threading.Thread(target=connect_thread, daemon=True).start()

    def on_connected(self):
        self.connect_button.setEnabled(False)
        self.disconnect_button.setEnabled(True)
        self.set_controls_enabled(True)
        self.status_label.setText(f"Подключено: {self.network.username}")
        self.room_label.setText("Комната: Лобби")
        self.add_chat_message("Система", "Вы подключились к серверу!")
        self.current_room = "lobby"
        self.is_room_creator = False
        self.current_room_info = None
        self.up_button.setEnabled(False)
        self.down_button.setEnabled(False)
        self.left_button.setEnabled(False)
        self.right_button.setEnabled(False)
        self.start_game_button.setEnabled(False)

    def on_disconnected(self):
        self.connect_button.setEnabled(True)
        self.disconnect_button.setEnabled(False)
        self.set_controls_enabled(False)
        self.up_button.setEnabled(False)
        self.down_button.setEnabled(False)
        self.left_button.setEnabled(False)
        self.right_button.setEnabled(False)
        self.start_game_button.setEnabled(False)
        self.restart_game_button.setEnabled(False)
        self.status_label.setText("Отключено")
        self.room_label.setText("Комната: ---")
        self.add_chat_message("Система", "Соединение разорвано")
        self.current_room = None
        self.is_room_creator = False
        self.current_room_info = None
        self.rooms_list = []
        self.rooms_list_widget.clear()
        self.game_widget.update_game_data(None)
        logger.info("Отключено от сервера")

    def on_error(self, error_msg):
        self.connect_button.setEnabled(True)
        self.status_label.setText(f"Ошибка: {error_msg}")
        QMessageBox.critical(self, "Ошибка подключения", error_msg)

    def disconnect_from_server(self):
        try:
            self.network.disconnect()
            self.on_disconnected()
            self.game_widget.update_game_data(None)
            self.chat_display.clear()
            self.rooms_list_widget.clear()
            logger.info("Отключение от сервера")
        except Exception as e:
            logger.error(f"Ошибка при отключении: {traceback.format_exc()}")

    def on_message_received(self, message):
        if not message:
            return

        msg_type = message.get('type')
        data = message.get('data')

        try:
            if msg_type == MessageType.GAME_OVER:
                self.handle_game_over(data)
            elif msg_type == MessageType.GAME_STATE:
                self.game_widget.update_game_data(data)
            elif msg_type == MessageType.CHAT:
                sender = "Сервер" if message['from_user'] == "SERVER" else message['from_user']
                self.add_chat_message(sender, data)
            elif msg_type == MessageType.PLAYER_JOINED:
                self.add_chat_message("Система", data)
            elif msg_type == MessageType.PLAYER_LEFT:
                self.add_chat_message("Система", data)
            elif msg_type == MessageType.ROOM_LIST:
                self.update_rooms_list(data)
            elif msg_type == MessageType.ROOM_JOINED:
                self.handle_room_joined(data)
            elif msg_type == MessageType.GAME_STARTED:
                self.handle_game_started(data)

        except Exception as e:
            logger.error(f"Ошибка обработки сообщения {msg_type}: {traceback.format_exc()}")

    def handle_room_joined(self, room_data):
        room_name = room_data.get('room_name', 'Неизвестно')
        players = room_data.get('players', [])

        self.current_room = room_data.get('room_id')
        self.is_room_creator = room_data.get('is_creator', False)
        self.current_room_info = room_data

        self.room_label.setText(f"Комната: {room_name}")
        self.add_chat_message("Система", f"Вы присоединились к комнате '{room_name}'")
        self.add_chat_message("Система", f"Игроки в комнате: {', '.join(players)}")

        if self.is_room_creator:
            self.add_chat_message("Система", "Вы создатель комнаты и можете начать игру")

        self.update_start_game_button()

        if self.current_room == "lobby":
            self.up_button.setEnabled(False)
            self.down_button.setEnabled(False)
            self.left_button.setEnabled(False)
            self.right_button.setEnabled(False)
            self.start_game_button.setEnabled(False)
        else:
            self.up_button.setEnabled(True)
            self.down_button.setEnabled(True)
            self.left_button.setEnabled(True)
            self.right_button.setEnabled(True)
            self.start_game_button.setEnabled(self.is_room_creator)

        QApplication.processEvents()
        self.focusOnGame()
        threading.Timer(0.5, self.focusOnGame).start()

    def handle_game_started(self, data):
        msg = data.get("message", "Игра началась!")
        started_by = data.get("started_by", "Неизвестно")
        self.add_chat_message("Система", f"{msg}")
        self.add_chat_message("Система", f"Игра начата игроком {started_by}")

        if self.current_room_info:
            self.current_room_info["game_active"] = True

        # убрать winner с экрана
        if self.game_widget.game_data and "winner" in self.game_widget.game_data:
            self.game_widget.game_data.pop("winner")
            self.game_widget.update()

        self.update_start_game_button()

    def handle_game_over(self, data):
        winner_info = data if isinstance(data, dict) else {'winner_name': str(data)}

        if winner_info.get('draw'):
            self.add_chat_message("Система", "НИЧЬЯ! Все игроки погибли одновременно")
        elif winner_info.get('single_player'):
            self.add_chat_message("Система", f"Игра окончена! Ваш счет: {winner_info.get('score', 0)}")
        else:
            self.add_chat_message("Система",
                                f"ПОБЕДИТЕЛЬ: {winner_info.get('winner_name')}! "
                                f"Счет: {winner_info.get('score', 0)}")

        current_data = self.game_widget.game_data or {'snakes': {}, 'food': [], 'grid_size': (40, 30)}
        current_data['winner'] = winner_info
        current_data['game_active'] = False
        self.game_widget.update_game_data(current_data)

    def restart_game(self):
        if self.current_room and self.current_room != "lobby" and self.is_room_creator:
            self.network.send_message_type(MessageType.RESTART_GAME, None)
            self.add_chat_message("Система", "Запрос на перезапуск игры отправлен...")
        else:
            self.add_chat_message("Система", "Только создатель комнаты может перезапустить игру")

    def update_rooms_list(self, rooms_data):
        self.rooms_list_widget.clear()

        for room in rooms_data:
            if room.get('game_active', False):
                status = "Идёт игра"
            else:
                status = "Ожидание"

            room_info = f"{status} | {room['room_name']} ({room['player_count']}/{room['max_players']}) - {room['creator']}"
            item = QListWidgetItem(room_info)
            item.setData(Qt.UserRole, room['room_id'])
            self.rooms_list_widget.addItem(item)

    def add_chat_message(self, sender, message):
        self.chat_display.append(f"{sender}: {message}")
        scrollbar = self.chat_display.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def send_chat(self):
        message = self.chat_input.text().strip()

        if message:
            if self.network.send_chat(message):
                self.chat_input.clear()

    def send_move(self, direction):
        if self.current_room and self.current_room != "lobby":
            self.network.send_move(direction)

    def start_game(self):
        if self.current_room and self.current_room != "lobby" and self.is_room_creator:
            self.network.send_message_type(MessageType.START_GAME, None)
            self.add_chat_message("Система", "Отправлен запрос на начало игры...")

    def create_room(self):
        if not self.network.running or not self.network.socket:
            self.add_chat_message("Система", "Нет активного подключения к серверу")
            return

        room_name = self.room_name_input.text().strip()

        if not room_name:
            room_name = f"Комната_{random.randint(100, 999)}"

        if self.current_room != "lobby":
            self.add_chat_message("Система", "Для создания комнаты необходимо быть в лобби")
            return

        try:
            self.network.socket.getpeername()
        except (OSError, socket.error):
            self.add_chat_message("Система", "Соединение с сервером разорвано")
            self.on_disconnected()
            return

        self.network.send_message_type(MessageType.CREATE_ROOM, room_name)
        self.room_name_input.clear()
        self.add_chat_message("Система", f"Создаем комнату '{room_name}'...")

    def join_selected_room(self, item):
        room_id = item.data(Qt.UserRole)

        if room_id:
            self.network.send_message_type(MessageType.JOIN_ROOM, room_id)

    def refresh_rooms(self):
        self.network.send_message_type(MessageType.JOIN_ROOM, "refresh")

    def leave_room(self):
        if self.current_room and self.current_room != "lobby":
            self.network.send_message_type(MessageType.LEAVE_ROOM, None)
            self.is_room_creator = False
            self.current_room_info = None
            self.update_start_game_button()

    def keyPressEvent(self, event):
        if not self.network.running or not self.current_room or self.current_room == "lobby":
            super().keyPressEvent(event)
            return

        key = event.key()

        if key in [Qt.Key_W, Qt.Key_Up, Qt.Key_S, Qt.Key_Down,
                  Qt.Key_A, Qt.Key_Left, Qt.Key_D, Qt.Key_Right]:
            event.accept()
            self.focusOnGame()

            if key in [Qt.Key_W, Qt.Key_Up]:
                self.send_move("UP")
            elif key in [Qt.Key_S, Qt.Key_Down]:
                self.send_move("DOWN")
            elif key in [Qt.Key_A, Qt.Key_Left]:
                self.send_move("LEFT")
            elif key in [Qt.Key_D, Qt.Key_Right]:
                self.send_move("RIGHT")

        else:
            super().keyPressEvent(event)

    def focusOnGame(self):
        self.game_widget.setFocus()
        self.game_widget.activateWindow()
        self.game_widget.raise_()

    def closeEvent(self, event):
        self.disconnect_from_server()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    client = SnakeClient()
    client.show()
    sys.exit(app.exec_())