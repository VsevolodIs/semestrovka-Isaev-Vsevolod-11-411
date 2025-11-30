import pickle
import struct
import logging
import traceback
from enum import Enum
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MessageType(Enum):
    AUTH = "auth"
    MOVE = "move"
    GAME_STATE = "game_state"
    CHAT = "chat"
    ADMIN_BAN = "admin_ban"
    SAVE_REQUEST = "save_request"
    DISCONNECT = "disconnect"
    PLAYER_JOINED = "player_joined"
    PLAYER_LEFT = "player_left"
    GAME_OVER = "game_over"
    RESTART_GAME = "restart_game"
    CREATE_ROOM = "create_room"
    JOIN_ROOM = "join_room"
    LEAVE_ROOM = "leave_room"
    ROOM_LIST = "room_list"
    ROOM_JOINED = "room_joined"
    START_GAME = "start_game"
    GAME_STARTED = "game_started"

class GameProtocol:
    @staticmethod
    def create_message(msg_type, from_user, data=None):
        message = {
            'type': msg_type.value if isinstance(msg_type, Enum) else msg_type,
            'from_user': from_user,
            'data': data,
            'timestamp': GameProtocol.get_timestamp()
        }
        return message

    @staticmethod
    def serialize_message(message):
        try:
            if not isinstance(message, dict):
                logger.error(f"Ошибка: сообщение не является словарем: {type(message)}")
                return None
            return pickle.dumps(message)
        except Exception as e:
            logger.error(f"Ошибка сериализации: {traceback.format_exc()}")
            return None

    @staticmethod
    def deserialize_message(data):
        try:
            if not data:
                logger.warning("Получены пустые данные для десериализации")
                return None
            return pickle.loads(data)
        except (pickle.UnpicklingError, EOFError, AttributeError, KeyError) as e:
            logger.error(f"Ошибка десериализации: {traceback.format_exc()}")
            return None

    @staticmethod
    def get_timestamp():
        return datetime.now().isoformat()

    @staticmethod
    def send_message(sock, message):
        try:
            data = GameProtocol.serialize_message(message)
            
            if data is None:
                logger.error("Не удалось сериализовать сообщение")
                return False
            
            if len(data) > 10 * 1024 * 1024:  # 10 MB limit
                logger.error(f"Сообщение слишком большое: {len(data)} байт")
                return False
            
            length_prefix = struct.pack('!I', len(data))
            sock.sendall(length_prefix + data)
            return True
        except Exception as e:
            logger.error(f"Ошибка отправки сообщения: {traceback.format_exc()}")
            return False

    @staticmethod
    def receive_message(sock):
        try:
            length_data = sock.recv(4)
            
            if not length_data:
                logger.warning("Получены пустые данные при чтении длины")
                return None

            length = struct.unpack('!I', length_data)[0]
            
            if length > 10 * 1024 * 1024:  # 10 MB limit
                logger.error(f"Сообщение слишком большое: {length} байт")
                return None
            
            if length == 0:
                logger.warning("Получено сообщение нулевой длины")
                return None

            data = b''
            while len(data) < length:
                chunk = sock.recv(min(4096, length - len(data)))
                
                if not chunk:
                    logger.warning("Неполное сообщение от клиента")
                    return None
                
                data += chunk

            result = GameProtocol.deserialize_message(data)
            
            if result is None:
                logger.warning("Не удалось десериализовать сообщение")
                return None
            
            return result

        except Exception as e:
            logger.error(f"Ошибка получения сообщения: {traceback.format_exc()}")
            return None