import random
import threading
import logging
import traceback
from enum import Enum
import json
from datetime import datetime

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class Direction(Enum):
    UP = "UP"
    DOWN = "DOWN"
    LEFT = "LEFT"
    RIGHT = "RIGHT"

class Snake:
    def __init__(self, player_id, start_pos, color=None):
        self.player_id = player_id
        self.body = [start_pos]
        self.direction = Direction.RIGHT
        self.next_direction = Direction.RIGHT
        self.alive = True
        self.score = 0
        self.color = color or self._generate_color()
        self.last_move_time = datetime.now()

    def _generate_color(self):
        colors = ["#FF6B6B", "#4ECDC4", "#45B7D1", "#96CEB4", "#FFEAA7", "#DDA0DD", "#98D8C8"]
        return random.choice(colors)

    def set_direction(self, new_direction):
        opposite_directions = {
            Direction.UP: Direction.DOWN,
            Direction.DOWN: Direction.UP,
            Direction.LEFT: Direction.RIGHT,
            Direction.RIGHT: Direction.LEFT
        }

        if new_direction != opposite_directions.get(self.direction):
            self.next_direction = new_direction

    def move(self, grid_size, food_positions=None):
        if not self.alive:
            return False

        self.direction = self.next_direction
        self.last_move_time = datetime.now()

        head_x, head_y = self.body[0]

        if self.direction == Direction.UP:
            new_head = (head_x, head_y - 1)
        elif self.direction == Direction.DOWN:
            new_head = (head_x, head_y + 1)
        elif self.direction == Direction.LEFT:
            new_head = (head_x - 1, head_y)
        elif self.direction == Direction.RIGHT:
            new_head = (head_x + 1, head_y)

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

        if our_head in other_snake.body[1:]:
            self.alive = False
            return True

        if our_head == other_snake.body[0]:
            self.alive = False
            other_snake.alive = False
            return True

        return False

    def to_dict(self):
        return {
            'player_id': self.player_id,
            'body': self.body,
            'direction': self.direction.value,
            'alive': self.alive,
            'score': self.score,
            'color': self.color
        }

    @classmethod
    def from_dict(cls, data):
        snake = cls(data['player_id'], data['body'][0])
        snake.body = data['body']
        snake.direction = Direction(data['direction'])
        snake.next_direction = Direction(data['direction'])
        snake.alive = data['alive']
        snake.score = data['score']
        snake.color = data['color']
        return snake

class GameState:
    def __init__(self, grid_size=(40, 30)):
        self.grid_size = grid_size
        self.snakes = {}
        self.food_positions = []
        self.game_active = False
        self.max_players = 4
        self.admin_players = set()
        self.lock = threading.Lock()

        self._generate_food(5)

    def _generate_food(self, count):
        for _ in range(count):
            attempts = 0
            max_attempts = 50

            while attempts < max_attempts:
                pos = (random.randint(0, self.grid_size[0] - 1),
                       random.randint(0, self.grid_size[1] - 1))

                if (not any(pos in snake.body for snake in self.snakes.values()) and
                    pos not in self.food_positions):
                    self.food_positions.append(pos)
                    break

                attempts += 1

            if attempts == max_attempts:
                logger.warning(f"Не удалось разместить еду после {max_attempts} попыток")

    def add_player(self, player_id, username):
        with self.lock:
            if len(self.snakes) >= self.max_players:
                return False

            max_attempts = 100
            for attempt in range(max_attempts):
                start_x = random.randint(3, self.grid_size[0] - 4)
                start_y = random.randint(3, self.grid_size[1] - 4)
                position_occupied = False

                for snake in self.snakes.values():
                    if (start_x, start_y) in snake.body:
                        position_occupied = True
                        break

                if not position_occupied:
                    snake = Snake(player_id, (start_x, start_y))
                    self.snakes[player_id] = snake
                    
                    if len(self.snakes) == 1:
                        self.admin_players.add(player_id)
                    
                    return True

            start_x = random.randint(5, self.grid_size[0] - 6)
            start_y = random.randint(5, self.grid_size[1] - 6)
            snake = Snake(player_id, (start_x, start_y))
            self.snakes[player_id] = snake
            
            if len(self.snakes) == 1:
                self.admin_players.add(player_id)
            
            return True

    def remove_player(self, player_id):
        with self.lock:
            if player_id in self.snakes:
                del self.snakes[player_id]

            if player_id in self.admin_players:
                self.admin_players.remove(player_id)

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

    def ban_player(self, admin_id, target_username, players_info):
        with self.lock:
            if admin_id not in self.admin_players:
                return False, "Нет прав администратора"

            target_id = None

            for pid, info in players_info.items():
                if info['username'] == target_username:
                    target_id = pid
                    break

            if not target_id:
                return False, "Игрок не найден"

            if target_id == admin_id:
                return False, "Нельзя заблокировать себя"

            self.remove_player(target_id)

            return True, f"Игрок {target_username} заблокирован"

    def get_game_data(self):
        with self.lock:
            return {
                'snakes': {pid: snake.to_dict() for pid, snake in self.snakes.items()},
                'food': self.food_positions,
                'game_active': self.game_active,
                'grid_size': self.grid_size
            }

    def save_game_state(self, players_info, filename=None):
        if not filename:
            filename = f"game_save_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"

        try:
            with self.lock:
                save_data = {
                    'timestamp': datetime.now().isoformat(),
                    'game_active': self.game_active,
                    'grid_size': self.grid_size,
                    'players': [],
                    'food_positions': self.food_positions
                }

                for player_id, snake in self.snakes.items():
                    player_data = {
                        'player_id': player_id,
                        'username': players_info.get(player_id, {}).get('username', 'Unknown'),
                        'snake': snake.to_dict(),
                        'is_admin': player_id in self.admin_players
                    }

                    save_data['players'].append(player_data)

            with open(filename, 'w', encoding='utf-8') as f:
                json.dump(save_data, f, indent=2, ensure_ascii=False)

            logger.info(f"Игра сохранена в {filename}")
            return True, f"Игра сохранена в {filename}"

        except Exception as e:
            logger.error(f"Ошибка сохранения: {traceback.format_exc()}")
            return False, f"Ошибка сохранения: {e}"