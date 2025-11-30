import socket
import threading
import time
import random
from datetime import datetime
from game_protocol import GameProtocol


class MessageType:
    AUTH = "auth"
    MOVE = "move"
    GAME_STATE = "game_state"
    CHAT = "chat"
    ADMIN_BAN = "admin_ban"
    SAVE_REQUEST = "save_request"
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


class Snake:
    def __init__(self, player_id, start_pos, color=None):
        self.player_id = player_id
        self.body = [start_pos]
        self.direction = "RIGHT"
        self.next_direction = "RIGHT"
        self.alive = True
        self.score = 0
        self.color = color or self._generate_color()
        self.last_move_time = datetime.now()
        self.prev_head = start_pos

    def _generate_color(self):
        colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4",
                  "#FFEAA7", "#DDA0DD", "#98D8C8"]
        return random.choice(colors)

    def set_direction(self, new_direction):
        opposite = {"UP": "DOWN", "DOWN": "UP",
                    "LEFT": "RIGHT", "RIGHT": "LEFT"}
        if new_direction != opposite.get(self.direction):
            self.next_direction = new_direction

    def move(self, grid_size, food_positions=None):
        if not self.alive:
            return False

        self.prev_head = self.body[0]
        self.direction = self.next_direction
        head_x, head_y = self.body[0]
        deltas = {"UP": (0, -1), "DOWN": (0, 1),
                  "LEFT": (-1, 0), "RIGHT": (1, 0)}
        dx, dy = deltas.get(self.direction, (0, 0))
        new_head = (head_x + dx, head_y + dy)

        if (new_head[0] < 0 or new_head[0] >= grid_size[0] or
                new_head[1] < 0 or new_head[1] >= grid_size[1]):
            self.alive = False
            return False

        if new_head in self.body:
            self.alive = False
            return False

        self.body.insert(0, new_head)

        ate_food = False
        if food_positions and new_head in food_positions:
            self.score += 10
            ate_food = True
        else:
            if len(self.body) > 1:
                self.body.pop()

        return ate_food

    def check_collision_with_other(self, other_snake):
        if not self.alive or not other_snake.alive:
            return False

        our_head = self.body[0]
        their_head = other_snake.body[0]
        their_body = other_snake.body

        if our_head == their_head:
            self.alive = False
            other_snake.alive = False
            return True

        if (hasattr(self, "prev_head") and hasattr(other_snake, "prev_head") and
                self.prev_head == their_head and
                other_snake.prev_head == our_head):
            self.alive = False
            other_snake.alive = False
            return True

        if our_head in their_body:
            self.alive = False
            return True

        return False

    def to_dict(self):
        return {
            'player_id': self.player_id,
            'body': self.body,
            'direction': self.direction,
            'alive': self.alive,
            'score': self.score,
            'color': self.color
        }


class GameState:
    def __init__(self, grid_size=(40, 30)):
        self.grid_size = grid_size
        self.snakes = {}
        self.food_positions = []
        self.game_active = False
        self.lock = threading.Lock()
        self._generate_food(5)

    def _generate_food(self, count):
        for _ in range(count):
            attempts = 0
            while attempts < 50:
                pos = (random.randint(0, self.grid_size[0] - 1),
                       random.randint(0, self.grid_size[1] - 1))
                collision = False
                for snake in self.snakes.values():
                    if pos in snake.body:
                        collision = True
                        break
                if not collision and pos not in self.food_positions:
                    self.food_positions.append(pos)
                    break
                attempts += 1

    def add_player(self, player_id, username):
        with self.lock:
            if player_id in self.snakes:
                return True

            max_attempts = 100
            for _ in range(max_attempts):
                start_x = random.randint(3, self.grid_size[0] - 4)
                start_y = random.randint(3, self.grid_size[1] - 4)
                if all((start_x, start_y) not in s.body
                       for s in self.snakes.values()):
                    self.snakes[player_id] = Snake(player_id, (start_x, start_y))
                    return True

            start_x = random.randint(5, self.grid_size[0] - 6)
            start_y = random.randint(5, self.grid_size[1] - 6)
            self.snakes[player_id] = Snake(player_id, (start_x, start_y))
            return True

    def remove_player(self, player_id):
        with self.lock:
            if player_id in self.snakes:
                del self.snakes[player_id]

    def update_player_direction(self, player_id, direction):
        with self.lock:
            if player_id in self.snakes and self.game_active:
                if direction in ["UP", "DOWN", "LEFT", "RIGHT"]:
                    self.snakes[player_id].set_direction(direction)
                    return True
            return False

    def update_movement(self):
        with self.lock:
            if not self.game_active:
                return

            food_set = set(self.food_positions)
            snakes_ate_food = []

            for snake in self.snakes.values():
                if snake.move(self.grid_size, food_set):
                    snakes_ate_food.append(snake)

            for snake in snakes_ate_food:
                head_pos = snake.body[0]
                if head_pos in self.food_positions:
                    self.food_positions.remove(head_pos)
                    self._generate_food(1)

            snake_list = list(self.snakes.values())
            for i in range(len(snake_list)):
                for j in range(i + 1, len(snake_list)):
                    snake_list[i].check_collision_with_other(snake_list[j])
                    snake_list[j].check_collision_with_other(snake_list[i])

    def get_game_data(self):
        with self.lock:
            return {
                'snakes': {pid: s.to_dict() for pid, s in self.snakes.items()},
                'food': self.food_positions,
                'game_active': self.game_active,
                'grid_size': self.grid_size
            }


class GameRoom:
    def __init__(self, room_id, room_name, max_players=4):
        self.room_id = room_id
        self.room_name = room_name
        self.max_players = max_players
        self.game_state = GameState()
        self.players = {}
        self.creator_id = None
        self.game_active = False
        self.lock = threading.Lock()

    def add_player(self, player_id, player_info):
        with self.lock:
            if len(self.players) >= self.max_players:
                return False, "Комната заполнена"
            if player_id in self.players:
                return False, "Игрок уже в комнате"

            self.players[player_id] = player_info
            if self.creator_id is None:
                self.creator_id = player_id

            if self.game_state.add_player(player_id, player_info['username']):
                return True, "Успешно присоединился к комнате"
            else:
                del self.players[player_id]
                return False, "Ошибка добавления в игру"

    def remove_player(self, player_id):
        with self.lock:
            if player_id in self.players:
                del self.players[player_id]
                self.game_state.remove_player(player_id)

                if player_id == self.creator_id:
                    if self.players:
                        self.creator_id = random.choice(list(self.players.keys()))
                    else:
                        self.creator_id = None
                        self.game_active = False
                elif not self.players:
                    self.creator_id = None
                    self.game_active = False

                has_players = len(self.players) > 0

        if has_players:
            self.notify_creator_change()

        return not has_players

    def notify_creator_change(self):
        with self.lock:
            creator_id = self.creator_id
            room_id = self.room_id
            room_name = self.room_name
            players_snapshot = dict(self.players)

        for pid, info in players_snapshot.items():
            is_creator = (pid == creator_id)
            msg = GameProtocol.create_message(
                MessageType.ROOM_JOINED,
                "SERVER",
                {
                    'room_id': room_id,
                    'room_name': room_name,
                    'players': [p['username'] for p in players_snapshot.values()],
                    'is_creator': is_creator,
                }
            )
            GameProtocol.send_message(info['socket'], msg)

    def start_game(self, player_id):
        with self.lock:
            if player_id != self.creator_id:
                return False, "Только создатель комнаты может начать игру"
            if len(self.players) < 1:
                return False, "Нужен хотя бы один игрок"
            if self.game_active:
                return False, "Игра уже запущена"

            self.game_active = True
            self.game_state.game_active = True
            return True, "Игра началась"

    def restart_game(self, player_id):
        with self.lock:
            if player_id != self.creator_id:
                return False, "Только создатель комнаты может перезапустить игру"
            if not self.players:
                return False, "В комнате нет игроков"

            old_grid_size = self.game_state.grid_size
            new_state = GameState(old_grid_size)
            for pid, info in self.players.items():
                new_state.add_player(pid, info['username'])

            self.game_state = new_state
            self.game_active = True
            self.game_state.game_active = True
            return True, "Игра перезапущена"

    def get_room_info(self):
        with self.lock:
            return {
                'room_id': self.room_id,
                'room_name': self.room_name,
                'player_count': len(self.players),
                'max_players': self.max_players,
                'creator': self.players.get(self.creator_id, {}).get('username', 'Unknown'),
                'game_active': self.game_active
            }

    def broadcast_message(self, message, exclude_player=None):
        with self.lock:
            recipients = [(pid, info['socket'])
                          for pid, info in self.players.items()
                          if pid != exclude_player]

        for pid, sock in recipients:
            GameProtocol.send_message(sock, message)

    def update_game(self):
        with self.lock:
            if not self.game_active:
                return
            self.game_state.update_movement()
            snakes = self.game_state.snakes

            alive = [(pid, s) for pid, s in snakes.items() if s.alive]
            total = len(snakes)

            game_over_payload = None

            if len(alive) == 1 and total > 1:
                pid, s = alive[0]
                game_over_payload = {
                    'winner_id': pid,
                    'winner_name': self.players[pid]['username'],
                    'score': s.score
                }
            elif len(alive) == 0 and total > 1:
                game_over_payload = {
                    'winner_id': None,
                    'winner_name': None,
                    'draw': True
                }
            elif total == 1 and len(alive) == 0:
                pid = next(iter(snakes.keys()))
                s = snakes[pid]
                game_over_payload = {
                    'winner_id': None,
                    'winner_name': None,
                    'score': s.score,
                    'single_player': True
                }

            if game_over_payload is not None:
                self.game_active = False
                self.game_state.game_active = False

        if game_over_payload is not None:
            game_over_msg = GameProtocol.create_message(
                MessageType.GAME_OVER, "SERVER", game_over_payload)
            self.broadcast_message(game_over_msg)

        game_data = self.game_state.get_game_data()
        game_data['game_active'] = self.game_active
        game_state_msg = GameProtocol.create_message(
            MessageType.GAME_STATE, "SERVER", game_data)
        self.broadcast_message(game_state_msg)


class GameServer:
    def __init__(self, host="localhost", port=8888):
        self.host = host
        self.port = port
        self.server_socket = None
        self.running = False
        self.players = {}
        self.rooms = {}
        self.lobby_room = None
        self.players_lock = threading.Lock()
        self.rooms_lock = threading.Lock()
        self.player_counter = 0
        self.room_counter = 0
        self._create_lobby()

    def _create_lobby(self):
        lobby = GameRoom("lobby", "Лобби", max_players=50)
        self.lobby_room = lobby
        self.rooms["lobby"] = lobby

    def generate_player_id(self):
        self.player_counter += 1
        return f"player_{self.player_counter}"

    def generate_room_id(self):
        self.room_counter += 1
        return f"room_{self.room_counter}"

    def start_server(self):
        try:
            self.server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.server_socket.bind((self.host, self.port))
            self.server_socket.listen(5)
            self.server_socket.settimeout(1.0)
            self.running = True
            print(f"Сервер запущен на {self.host}:{self.port}")

            threading.Thread(target=self.game_loop, daemon=True).start()

            while self.running:
                try:
                    client_socket, client_address = self.server_socket.accept()
                    print(f"Новое подключение: {client_address}")
                    threading.Thread(
                        target=self.handle_client,
                        args=(client_socket, client_address),
                        daemon=True
                    ).start()
                except socket.timeout:
                    continue
        finally:
            self.stop_server()

    def handle_client(self, client_socket, client_address):
        player_id = None
        try:
            client_socket.settimeout(30.0)
            auth_message = GameProtocol.receive_message(client_socket)
            if not auth_message or auth_message.get('type') != MessageType.AUTH:
                return

            username = auth_message.get('data')
            if not username:
                return

            with self.players_lock:
                if any(info['username'] == username
                       for info in self.players.values()):
                    return
                player_id = self.generate_player_id()
                self.players[player_id] = {
                    'username': username,
                    'socket': client_socket,
                    'room_id': None
                }

            ok, _ = self.lobby_room.add_player(
                player_id, {'username': username, 'socket': client_socket})
            if not ok:
                with self.players_lock:
                    del self.players[player_id]
                return

            with self.players_lock:
                self.players[player_id]['room_id'] = "lobby"

            auth_success = GameProtocol.create_message(
                MessageType.AUTH, "SERVER",
                {"player_id": player_id, "status": "success", "room_id": "lobby"}
            )
            GameProtocol.send_message(client_socket, auth_success)
            self.send_room_list_to_player(player_id)

            join_msg = GameProtocol.create_message(
                MessageType.PLAYER_JOINED, "SERVER",
                f"Игрок {username} присоединился к лобби")
            self.lobby_room.broadcast_message(join_msg, exclude_player=player_id)
            self.broadcast_room_list_to_lobby()

            client_socket.settimeout(5.0)

            while self.running:
                message = GameProtocol.receive_message(client_socket)
                if message is None:
                    continue
                if not message:
                    break

                result = self.process_client_message(player_id, message)
                if result == "disconnect":
                    break

        finally:
            if player_id:
                self.remove_player(player_id)
            try:
                client_socket.close()
            except:
                pass

    def process_client_message(self, player_id, message):
        msg_type = message.get('type')

        if msg_type == MessageType.MOVE:
            self.handle_player_move(player_id, message)
        elif msg_type == MessageType.CHAT:
            self.handle_chat_message(player_id, message)
        elif msg_type == MessageType.CREATE_ROOM:
            self.handle_create_room(player_id, message)
        elif msg_type == MessageType.JOIN_ROOM:
            self.handle_join_room(player_id, message)
        elif msg_type == MessageType.LEAVE_ROOM:
            self.handle_leave_room(player_id)
        elif msg_type == MessageType.START_GAME:
            self.handle_start_game(player_id)
        elif msg_type == MessageType.RESTART_GAME:
            self.handle_restart_game(player_id)
        elif msg_type == MessageType.DISCONNECT:
            return "disconnect"

    def handle_create_room(self, player_id, message):
        with self.players_lock:
            if player_id not in self.players:
                return
            if self.players[player_id].get('room_id') != "lobby":
                return

        room_name = message.get('data') or f"Комната_{random.randint(100, 999)}"
        room_id = self.generate_room_id()
        room = GameRoom(room_id, room_name, 4)

        with self.rooms_lock:
            self.rooms[room_id] = room

        self.move_player_to_room(player_id, room_id, room_name)
        self.broadcast_room_list_to_lobby()

    def handle_join_room(self, player_id, message):
        target_room_id = message.get('data')
        if target_room_id == "refresh":
            self.send_room_list_to_player(player_id)
            return

        with self.rooms_lock:
            room = self.rooms.get(target_room_id)
        if not room:
            return

        self.move_player_to_room(player_id, target_room_id, room.room_name)
        self.broadcast_room_list_to_lobby()

    def handle_leave_room(self, player_id):
        self.move_player_to_room(player_id, "lobby", "Лобби")
        self.broadcast_room_list_to_lobby()

    def handle_chat_message(self, player_id, message):
        chat_text = message.get('data')
        with self.players_lock:
            if player_id not in self.players:
                return
            username = self.players[player_id]['username']
            room_id = self.players[player_id].get('room_id')

        if not room_id:
            return

        with self.rooms_lock:
            room = self.rooms.get(room_id)
        if room:
            chat_msg = GameProtocol.create_message(
                MessageType.CHAT, username, chat_text)
            room.broadcast_message(chat_msg)

    def handle_start_game(self, player_id):
        with self.players_lock:
            if player_id not in self.players:
                return
            room_id = self.players[player_id].get('room_id')
            username = self.players[player_id]['username']

        if not room_id or room_id == "lobby":
            return

        with self.rooms_lock:
            room = self.rooms.get(room_id)
        if not room:
            return

        ok, msg = room.start_game(player_id)
        if ok:
            started = GameProtocol.create_message(
                MessageType.GAME_STARTED, "SERVER",
                {'message': msg, 'started_by': username, 'room_id': room_id})
            room.broadcast_message(started)

            game_data = room.game_state.get_game_data()
            game_state_msg = GameProtocol.create_message(
                MessageType.GAME_STATE, "SERVER", game_data)
            room.broadcast_message(game_state_msg)

    def handle_restart_game(self, player_id):
        with self.players_lock:
            if player_id not in self.players:
                return
            room_id = self.players[player_id].get('room_id')
            username = self.players[player_id]['username']

        if not room_id or room_id == "lobby":
            return

        with self.rooms_lock:
            room = self.rooms.get(room_id)
        if not room:
            return

        ok, msg = room.restart_game(player_id)
        if ok:
            started = GameProtocol.create_message(
                MessageType.GAME_STARTED, "SERVER",
                {'message': msg, 'started_by': username, 'room_id': room_id})
            room.broadcast_message(started)

            game_data = room.game_state.get_game_data()
            game_state_msg = GameProtocol.create_message(
                MessageType.GAME_STATE, "SERVER", game_data)
            room.broadcast_message(game_state_msg)

    def handle_player_move(self, player_id, message):
        direction = message.get('data')
        with self.players_lock:
            if player_id not in self.players:
                return
            room_id = self.players[player_id].get('room_id')

        if not room_id or room_id == "lobby":
            return

        with self.rooms_lock:
            room = self.rooms.get(room_id)
        if room and room.game_active:
            room.game_state.update_player_direction(player_id, direction)
            room.update_game()

    def move_player_to_room(self, player_id, new_room_id, room_name):
        with self.players_lock:
            old_room_id = self.players[player_id].get('room_id')
            player_info = {
                'username': self.players[player_id]['username'],
                'socket': self.players[player_id]['socket']
            }
            username = player_info['username']

        if old_room_id and old_room_id != new_room_id:
            with self.rooms_lock:
                old_room = self.rooms.get(old_room_id)
            if old_room:
                empty = old_room.remove_player(player_id)
                leave_msg = GameProtocol.create_message(
                    MessageType.PLAYER_LEFT, "SERVER",
                    f"Игрок {username} покинул комнату")
                old_room.broadcast_message(leave_msg)
                if empty and old_room_id != "lobby":
                    with self.rooms_lock:
                        self.rooms.pop(old_room_id, None)

        with self.rooms_lock:
            new_room = self.rooms.get(new_room_id)
        if not new_room:
            return

        ok, _ = new_room.add_player(player_id, player_info)
        if not ok:
            return

        with self.players_lock:
            self.players[player_id]['room_id'] = new_room_id

        is_creator = (new_room.creator_id == player_id)
        room_joined = GameProtocol.create_message(
            MessageType.ROOM_JOINED, "SERVER",
            {
                'room_id': new_room_id,
                'room_name': room_name,
                'players': [info['username'] for info in new_room.players.values()],
                'is_creator': is_creator
            }
        )
        self.send_message_to_player(player_id, room_joined)

        join_msg = GameProtocol.create_message(
            MessageType.PLAYER_JOINED, "SERVER",
            f"Игрок {username} присоединился к комнате")
        new_room.broadcast_message(join_msg, exclude_player=player_id)

        if new_room_id != "lobby":
            game_data = new_room.game_state.get_game_data()
            game_state_msg = GameProtocol.create_message(
                MessageType.GAME_STATE, "SERVER", game_data)
            self.send_message_to_player(player_id, game_state_msg)

    def broadcast_room_list_to_lobby(self):
        msg = self.get_room_list_message()
        self.lobby_room.broadcast_message(msg)

    def get_room_list_message(self):
        with self.rooms_lock:
            rooms = [room.get_room_info()
                     for rid, room in self.rooms.items()
                     if rid != "lobby"]
        return GameProtocol.create_message(
            MessageType.ROOM_LIST, "SERVER", rooms)

    def send_room_list_to_player(self, player_id):
        msg = self.get_room_list_message()
        self.send_message_to_player(player_id, msg)

    def remove_player(self, player_id):
        with self.players_lock:
            if player_id not in self.players:
                return
            username = self.players[player_id]['username']
            room_id = self.players[player_id].get('room_id')
            del self.players[player_id]

        if room_id:
            with self.rooms_lock:
                room = self.rooms.get(room_id)
            if room:
                empty = room.remove_player(player_id)
                leave_msg = GameProtocol.create_message(
                    MessageType.PLAYER_LEFT, "SERVER",
                    f"Игрок {username} покинул игру")
                room.broadcast_message(leave_msg)
                if empty and room_id != "lobby":
                    with self.rooms_lock:
                        self.rooms.pop(room_id, None)

        self.broadcast_room_list_to_lobby()
        print(f"Игрок {username} ({player_id}) отключился")

    def game_loop(self):
        last_update = time.time()
        interval = 0.1
        while self.running:
            now = time.time()
            if now - last_update >= interval:
                with self.rooms_lock:
                    rooms = list(self.rooms.items())
                for rid, room in rooms:
                    if rid != "lobby" and room.game_active:
                        room.update_game()
                last_update = now
            time.sleep(0.01)

    def send_message_to_player(self, player_id, message):
        with self.players_lock:
            if player_id not in self.players:
                return
            sock = self.players[player_id]['socket']
        GameProtocol.send_message(sock, message)

    def stop_server(self):
        self.running = False
        with self.players_lock:
            for info in self.players.values():
                try:
                    info['socket'].close()
                except:
                    pass
            self.players.clear()
        with self.rooms_lock:
            self.rooms.clear()
        if self.server_socket:
            try:
                self.server_socket.close()
            except:
                pass
        print("Сервер остановлен")


if __name__ == "__main__":
    server = GameServer()
    try:
        server.start_server()
    except KeyboardInterrupt:
        server.stop_server()