import pygame
import sys
import random
import time
import io
import math
import numpy as np  # Додано для генерації звукових хвиль
from enum import Enum, auto

# ── Константи ──────────────────────────────────────────────────────────────────
CELL = 44          
MARGIN = 10
GRID_COLS = 10
GRID_ROWS = 10
COLS = "ABCDEFGHIJ"

LEFT_BOARD_X = 30
RIGHT_BOARD_X = LEFT_BOARD_X + (GRID_COLS * CELL) + 220 
WINDOW_W = RIGHT_BOARD_X + (GRID_COLS * CELL) + 180
CENTER_BOARD_X = WINDOW_W // 2 - (GRID_COLS * CELL) // 2

BOARD_Y = 130
LOG_X = LEFT_BOARD_X
LOG_Y = BOARD_Y + GRID_ROWS * CELL + 80
WINDOW_H = 850 

TURN_LIMIT = 30 

C_BG           = (15,  20,  40)
C_GRID         = (40,  60,  90)
C_SHIP         = (120, 140, 160)
C_HIT          = (220,  70,  50)
C_MISS         = (60,  120, 180)
C_SUNK         = (80,  80,  80)
C_WHITE        = (240, 240, 250)
C_YELLOW       = (240, 200,  60)
C_GREEN        = ( 60, 200, 100)
C_RED          = (220,  60,  60)
C_PANEL_BG     = (20,  30,  55)
C_NEON_BLUE    = (40, 120, 255)

FLEET = [
    ("Лінкор",   4, 1),
    ("Крейсер",  3, 2),
    ("Есмінець", 2, 3),
    ("Катер",    1, 4),
]

# ── Звукова система (Синтез звуків) ───────────────────────────────────────────
class SoundManager:
    def __init__(self):
        pygame.mixer.pre_init(44100, -16, 2, 512)
        self.sample_rate = 44100

    def generate_sound(self, freq_func, duration=0.2, volume=0.3):
        n_samples = int(self.sample_rate * duration)
        buf = np.zeros((n_samples, 2), dtype=np.int16)
        for i in range(n_samples):
            t = i / self.sample_rate
            freq = freq_func(t)
            val = int(math.sin(2 * math.pi * freq * t) * 32767 * volume)
            buf[i][0] = val # Лівий канал
            buf[i][1] = val # Правий канал
        return pygame.sndarray.make_sound(buf)

    def play_miss(self):
        # Короткий низький звук "бульк"
        f = lambda t: 200 * (1 - t*2)
        self.generate_sound(f, 0.15, 0.2).play()

    def play_hit(self):
        # Високий різкий звук
        f = lambda t: 800 * (1 + t)
        self.generate_sound(f, 0.1, 0.3).play()

    def play_sunk(self):
        # Потужний вибух (генерація шуму через рандом)
        n_samples = int(self.sample_rate * 0.5)
        buf = np.zeros((n_samples, 2), dtype=np.int16)
        for i in range(n_samples):
            val = int(random.uniform(-1, 1) * 32767 * 0.4 * (1 - i/n_samples))
            buf[i][0] = val
            buf[i][1] = val
        pygame.sndarray.make_sound(buf).play()

# ── Допоміжні класи для анімації ──────────────────────────────────────────────
class Particle:
    def __init__(self, x, y):
        self.x = x
        self.y = y
        angle = random.uniform(0, math.pi * 2)
        speed = random.uniform(2, 5)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed
        self.life = 255
        self.color = random.choice([C_HIT, C_YELLOW, (255, 255, 255)])

    def update(self):
        self.x += self.vx
        self.y += self.vy
        self.life -= 8
        return self.life > 0

    def draw(self, screen):
        if self.life > 0:
            s = pygame.Surface((4, 4))
            s.set_alpha(self.life)
            s.fill(self.color)
            screen.blit(s, (int(self.x), int(self.y)))

class Explosion:
    def __init__(self, x, y):
        self.particles = [Particle(x, y) for _ in range(20)]
    
    def update(self):
        self.particles = [p for p in self.particles if p.update()]
        return len(self.particles) > 0

    def draw(self, screen):
        for p in self.particles:
            p.draw(screen)

# ── SVG Графіка (залишено без змін) ──────────────────────────────────────────
def load_svg(svg_str, size):
    return pygame.transform.smoothscale(pygame.image.load(io.BytesIO(svg_str.encode()), "image.svg").convert_alpha(), size)

SVG_SEA_1 = f'<svg width="{CELL}" height="{CELL}" viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg"><rect width="44" height="44" fill="#14325a"/><path d="M0 20 Q11 10 22 20 T44 20" stroke="#1e467d" fill="none" stroke-width="2"/></svg>'
SVG_SEA_2 = f'<svg width="{CELL}" height="{CELL}" viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg"><rect width="44" height="44" fill="#193c69"/><path d="M0 25 Q11 15 22 25 T44 25" stroke="#23508c" fill="none" stroke-width="2"/></svg>'

SHIP_SVGS = {
    4: f'<svg viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg"><rect x="4" y="10" width="36" height="24" rx="4" fill="#788ca0"/><rect x="10" y="14" width="24" height="16" fill="#5a6e82"/><circle cx="22" cy="22" r="5" fill="#465a6e"/></svg>',
    3: f'<svg viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg"><path d="M4 14 L40 14 L36 30 L8 30 Z" fill="#8c96a0"/><rect x="12" y="18" width="20" height="8" fill="#5a646e"/></svg>',
    2: f'<svg viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg"><rect x="6" y="12" width="32" height="20" rx="10" fill="#64788c"/><circle cx="15" cy="22" r="3" fill="#ffffff"/><circle cx="29" cy="22" r="3" fill="#ffffff"/></svg>',
    1: f'<svg viewBox="0 0 44 44" xmlns="http://www.w3.org/2000/svg"><circle cx="22" cy="22" r="14" fill="#506478"/><circle cx="22" cy="22" r="7" fill="#32465a"/></svg>'
}

SVG_DECO_LEFT = '''<svg width="200" height="200" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
    <path d="M10 70 L90 70 L80 85 L20 85 Z" fill="#405070"/>
    <rect x="30" y="50" width="40" height="20" fill="#5a6a8a"/>
    <rect x="40" y="35" width="20" height="15" fill="#7a8aba"/>
    <line x1="50" y1="35" x2="50" y2="20" stroke="#90a0d0" stroke-width="2"/>
    <rect x="45" y="15" width="15" height="10" fill="#d04040"/>
</svg>'''

SVG_DECO_RIGHT = '''<svg width="200" height="200" viewBox="0 0 100 100" xmlns="http://www.w3.org/2000/svg">
    <path d="M10 70 L90 70 L80 85 L20 85 Z" fill="#405070" transform="scale(-1, 1) translate(-100, 0)"/>
    <rect x="30" y="55" width="40" height="15" fill="#5a6a8a"/>
    <circle cx="40" cy="50" r="8" fill="#7a8aba"/>
    <circle cx="60" cy="50" r="8" fill="#7a8aba"/>
    <path d="M45 40 L55 40 L50 25 Z" fill="#3cd264"/>
</svg>'''

SVG_CHECK = '''<svg width="20" height="20" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M9 16.17L4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z" fill="#3cd264"/>
</svg>'''

SVG_CROSS = '''<svg width="20" height="20" viewBox="0 0 24 24" xmlns="http://www.w3.org/2000/svg">
    <path d="M19 6.41L17.59 5 12 10.59 6.41 5 5 6.41 10.59 12 5 17.59 6.41 19 12 13.41 17.59 19 19 17.59 13.41 12z" fill="#dc3c3c"/>
</svg>'''

class Phase(Enum):
    MAIN_MENU     = auto()
    P1_PLACE      = auto()
    P2_PLACE      = auto()
    PLAYER_TURN   = auto()
    P2_TURN       = auto()
    AI_TURN       = auto()
    GAME_OVER     = auto()

class CellState(Enum):
    EMPTY, SHIP, HIT, MISS, SUNK = range(5)

class Board:
    def __init__(self):
        self.grid = [[CellState.EMPTY] * GRID_COLS for _ in range(GRID_ROWS)]
        self.ships = []

    def in_bounds(self, r, c):
        return 0 <= r < GRID_ROWS and 0 <= c < GRID_COLS

    def can_place(self, cells):
        for (r, c) in cells:
            if not self.in_bounds(r, c): return False
            if self.grid[r][c] != CellState.EMPTY: return False
            for dr in range(-1, 2):
                for dc in range(-1, 2):
                    nr, nc = r + dr, c + dc
                    if self.in_bounds(nr, nc) and self.grid[nr][nc] == CellState.SHIP:
                        return False
        return True

    def place_ship(self, cells):
        if not self.can_place(cells): return False
        for (r, c) in cells:
            self.grid[r][c] = CellState.SHIP
        self.ships.append(list(cells))
        return True

    def auto_place(self):
        self.grid = [[CellState.EMPTY] * GRID_COLS for _ in range(GRID_ROWS)]
        self.ships = []
        for name, length, count in FLEET:
            for _ in range(count):
                placed = False
                while not placed:
                    h = random.choice([True, False])
                    r, c = (random.randint(0, 9), random.randint(0, 10-length)) if h else (random.randint(0, 10-length), random.randint(0, 9))
                    cells = [(r, c + i) if h else (r + i, c) for i in range(length)]
                    placed = self.place_ship(cells)

    def shoot(self, r, c):
        st = self.grid[r][c]
        if st == CellState.EMPTY:
            self.grid[r][c] = CellState.MISS
            return "miss", None
        if st == CellState.SHIP:
            self.grid[r][c] = CellState.HIT
            for ship in self.ships:
                if (r, c) in ship:
                    if all(self.grid[sr][sc] in (CellState.HIT, CellState.SUNK) for (sr, sc) in ship):
                        for (sr, sc) in ship: self.grid[sr][sc] = CellState.SUNK
                        return "sunk", ship
                    return "hit", None
        return None, None

    def all_sunk(self):
        return all(self.grid[r][c] != CellState.SHIP for r in range(10) for c in range(10))

    def get_fleet_stats(self):
        stats = {}
        for name, length, total in FLEET:
            alive = 0
            for ship in self.ships:
                if len(ship) == length:
                    if any(self.grid[sr][sc] == CellState.SHIP for sr, sc in ship):
                        alive += 1
            stats[length] = (alive, total - alive)
        return stats

class AI:
    def __init__(self, board):
        self.board = board
        self.untried = [(r, c) for r in range(10) for c in range(10)]
        random.shuffle(self.untried)
        self.hunt_queue = []

    def choose(self):
        if self.hunt_queue: return self.hunt_queue.pop(0)
        return self.untried.pop(0) if self.untried else None

    def register(self, r, c, res):
        if res in ("hit", "sunk"):
            for dr, dc in [(-1,0),(1,0),(0,-1),(0,1)]:
                nr, nc = r+dr, c+dc
                if 0 <= nr < 10 and 0 <= nc < 10:
                    for i, (tr, tc) in enumerate(self.untried):
                        if tr == nr and tc == nc:
                            self.hunt_queue.append(self.untried.pop(i))
                            break

class PlacementUI:
    def __init__(self, board):
        self.board = board
        self.ship_index = 0
        self.horiz = True
        self.queue = []
        for name, length, count in FLEET:
            for _ in range(count): self.queue.append((name, length))

    def current_ship(self):
        return self.queue[self.ship_index] if self.ship_index < len(self.queue) else None

    def is_finished(self):
        return self.ship_index >= len(self.queue)

    def preview_cells(self, r, c):
        ship = self.current_ship()
        if not ship: return []
        _, length = ship
        return [(r, c + i) if self.horiz else (r + i, c) for i in range(length)]

class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WINDOW_W, WINDOW_H))
        pygame.display.set_caption("Морський бій 2026")
        self.clock = pygame.time.Clock()
        self.sounds = SoundManager() # Ініціалізація звуків
        self.fonts = {
            "title": pygame.font.SysFont("Impact", 48),
            "med": pygame.font.SysFont("Arial", 22, True),
            "small": pygame.font.SysFont("Arial", 16, True),
            "tiny": pygame.font.SysFont("Arial", 14, True)
        }
        
        self.tex_sea = [load_svg(SVG_SEA_1, (CELL, CELL)), load_svg(SVG_SEA_2, (CELL, CELL))]
        self.tex_ships = {l: load_svg(svg, (CELL, CELL)) for l, svg in SHIP_SVGS.items()}
        self.icon_check = load_svg(SVG_CHECK, (20, 20))
        self.icon_cross = load_svg(SVG_CROSS, (20, 20))
        
        self.deco_left = load_svg(SVG_DECO_LEFT, (180, 180))
        self.deco_right = load_svg(SVG_DECO_RIGHT, (180, 180))

        self.phase = Phase.MAIN_MENU
        self.auto_btn_rect = pygame.Rect(CENTER_BOARD_X + (GRID_COLS * CELL)//2 - 50, BOARD_Y + GRID_ROWS * CELL + 20, 100, 40)
        self.confirm_btn_rect = pygame.Rect(CENTER_BOARD_X + (GRID_COLS * CELL) + 20, BOARD_Y + GRID_ROWS * CELL + 20, 150, 40)
        self.ai_delay = 0
        self.turn_start_time = 0
        self.explosions = []

    def reset(self, multiplayer):
        self.multiplayer = multiplayer
        self.p1_board, self.p2_board = Board(), Board()
        self.ai = AI(self.p1_board)
        self.placement = PlacementUI(self.p1_board)
        self.log = [("Гравець 1: Розставте кораблі", C_YELLOW)]
        self.phase = Phase.P1_PLACE
        self.turn_start_time = time.time()
        self.ai_delay = 0
        self.explosions = []

    def add_log(self, msg, color=C_WHITE):
        self.log.append((msg, color))
        if len(self.log) > 10: self.log.pop(0)

    def get_ship_name(self, length):
        for name, l, c in FLEET:
            if l == length: return name
        return "Корабель"

    def trigger_explosion(self, cells, ox, oy):
        self.sounds.play_sunk() # Граємо звук вибуху корабля
        for r, c in cells:
            ex = Explosion(ox + c * CELL + CELL // 2, oy + r * CELL + CELL // 2)
            self.explosions.append(ex)

    def handle_events(self):
        for event in pygame.event.get():
            if event.type == pygame.QUIT: pygame.quit(); sys.exit()
            
            if self.phase == Phase.GAME_OVER:
                if event.type == pygame.MOUSEBUTTONDOWN or event.type == pygame.KEYDOWN:
                    self.phase = Phase.MAIN_MENU
                continue

            if self.phase == Phase.MAIN_MENU:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    mx, my = event.pos
                    for i in range(2):
                        rect = pygame.Rect(WINDOW_W//2 - 160, 270 + i*90, 320, 65)
                        if rect.collidepoint(mx, my):
                            if i == 0: self.reset(False)
                            else: self.reset(True)

            elif self.phase in (Phase.P1_PLACE, Phase.P2_PLACE):
                active_board = self.p1_board if self.phase == Phase.P1_PLACE else self.p2_board
                if event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_SPACE: self.placement.horiz = not self.placement.horiz
                    if event.key == pygame.K_a:
                        active_board.auto_place()
                        self.placement.ship_index = len(self.placement.queue)
                
                if event.type == pygame.MOUSEBUTTONDOWN:
                    if self.auto_btn_rect.collidepoint(event.pos):
                        active_board.auto_place()
                        self.placement.ship_index = len(self.placement.queue)
                    elif self.confirm_btn_rect.collidepoint(event.pos) and self.placement.is_finished():
                        self.next_placement_step()
                    else:
                        res = self.get_board_cell(event.pos, CENTER_BOARD_X)
                        if res and not self.placement.is_finished():
                            r, c = res
                            cells = self.placement.preview_cells(r, c)
                            if active_board.place_ship(cells):
                                self.placement.ship_index += 1
                                self.sounds.play_hit() # Звук при встановленні
                            else:
                                self.add_log("Тут не можна ставити!", C_RED)

            elif self.phase == Phase.PLAYER_TURN:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    res = self.get_board_cell(event.pos, RIGHT_BOARD_X)
                    if res:
                        r, c = res
                        status, data = self.p2_board.shoot(r, c)
                        if status:
                            if status == "miss":
                                self.sounds.play_miss() # Звук промаху
                                self.add_log(f"Гравець 1: {COLS[c]}{r+1} - Мимо", C_MISS)
                                self.phase = Phase.AI_TURN if not self.multiplayer else Phase.P2_TURN
                                self.ai_delay = pygame.time.get_ticks() + 600
                            else:
                                if status == "hit": self.sounds.play_hit() # Звук влучання
                                self.add_log(f"Гравець 1: {COLS[c]}{r+1} - Попав!", C_HIT)
                                if status == "sunk": 
                                    self.add_log(f"УБИТО: {self.get_ship_name(len(data))}!", C_GREEN)
                                    self.trigger_explosion(data, RIGHT_BOARD_X, BOARD_Y)
                                if self.p2_board.all_sunk(): self.end_game("Гравець 1")
                            self.turn_start_time = time.time()

            elif self.phase == Phase.P2_TURN:
                if event.type == pygame.MOUSEBUTTONDOWN:
                    res = self.get_board_cell(event.pos, LEFT_BOARD_X) 
                    if res:
                        r, c = res
                        status, data = self.p1_board.shoot(r, c)
                        if status:
                            if status == "miss":
                                self.sounds.play_miss() # Звук промаху
                                self.add_log(f"Гравець 2: {COLS[c]}{r+1} - Мимо", C_MISS)
                                self.phase = Phase.PLAYER_TURN
                            else:
                                if status == "hit": self.sounds.play_hit() # Звук влучання
                                self.add_log(f"Гравець 2: {COLS[c]}{r+1} - Попав!", C_HIT)
                                if status == "sunk": 
                                    self.add_log(f"УБИТО: {self.get_ship_name(len(data))}!", C_GREEN)
                                    self.trigger_explosion(data, LEFT_BOARD_X, BOARD_Y)
                                if self.p1_board.all_sunk(): self.end_game("Гравець 2")
                            self.turn_start_time = time.time()

    def next_placement_step(self):
        if self.phase == Phase.P1_PLACE:
            if self.multiplayer:
                self.phase = Phase.P2_PLACE
                self.placement = PlacementUI(self.p2_board)
                self.add_log("Гравець 2: Розставте кораблі", C_YELLOW)
            else:
                self.p2_board.auto_place()
                self.start_game()
        else:
            self.start_game()

    def start_game(self):
        self.phase = Phase.PLAYER_TURN
        self.add_log("Гра почалася!", C_YELLOW)
        self.turn_start_time = time.time()
        self.ai_delay = 0

    def get_board_cell(self, pos, ox):
        x, y = pos
        c, r = (x - ox)//CELL, (y - BOARD_Y)//CELL
        return (r, c) if 0 <= r < 10 and 0 <= c < 10 else None

    def end_game(self, winner):
        self.winner = winner
        self.phase = Phase.GAME_OVER

    def update(self):
        self.explosions = [ex for ex in self.explosions if ex.update()]
        
        if self.phase in (Phase.PLAYER_TURN, Phase.P2_TURN):
            if time.time() - self.turn_start_time > TURN_LIMIT:
                self.add_log("Час вийшов!", C_RED)
                self.sounds.play_miss()
                if self.phase == Phase.PLAYER_TURN:
                    self.phase = Phase.AI_TURN if not self.multiplayer else Phase.P2_TURN
                    self.ai_delay = pygame.time.get_ticks() + 600
                else:
                    self.phase = Phase.PLAYER_TURN
                self.turn_start_time = time.time()

        if self.phase == Phase.AI_TURN and pygame.time.get_ticks() > self.ai_delay:
            r, c = self.ai.choose()
            if r is not None:
                res, data = self.p1_board.shoot(r, c)
                self.ai.register(r, c, res)
                if res == "miss":
                    self.sounds.play_miss() # Звук промаху ШІ
                    self.add_log(f"ІІ: {COLS[c]}{r+1} - Мимо", C_MISS)
                    self.phase = Phase.PLAYER_TURN
                    self.turn_start_time = time.time()
                else:
                    if res == "hit": self.sounds.play_hit() # Звук влучання ШІ
                    self.add_log(f"ІІ: {COLS[c]}{r+1} - Попав!", C_HIT)
                    if res == "sunk": 
                        self.add_log(f"ІІ УБИВ: {self.get_ship_name(len(data))}!", C_RED)
                        self.trigger_explosion(data, LEFT_BOARD_X, BOARD_Y)
                    if self.p1_board.all_sunk(): self.end_game("ІІ")
                    else: self.ai_delay = pygame.time.get_ticks() + 500

    def draw_board_base(self, board, ox, oy, reveal=True):
        pygame.draw.rect(self.screen, C_PANEL_BG, (ox - 5, oy - 5, GRID_COLS*CELL + 10, GRID_ROWS*CELL + 10), border_radius=6)
        for r in range(10):
            for c in range(10):
                x, y = ox + c * CELL, oy + r * CELL
                st = board.grid[r][c]
                self.screen.blit(self.tex_sea[(r + c) % 2], (x, y))
                
                if (st == CellState.SHIP and reveal) or st in (CellState.HIT, CellState.SUNK):
                    ship_len = 1
                    for s in board.ships:
                        if (r, c) in s:
                            ship_len = len(s)
                            break
                    self.screen.blit(self.tex_ships[ship_len], (x, y))

                if st == CellState.HIT:
                    pygame.draw.circle(self.screen, C_HIT, (x + CELL//2, y + CELL//2), 8)
                elif st == CellState.MISS:
                    pygame.draw.circle(self.screen, C_WHITE, (x + CELL//2, y + CELL//2), 3)
                elif st == CellState.SUNK:
                    overlay = pygame.Surface((CELL, CELL), pygame.SRCALPHA)
                    overlay.fill((255, 0, 0, 60))
                    self.screen.blit(overlay, (x, y))
                    pygame.draw.line(self.screen, C_WHITE, (x+10, y+10), (x+CELL-10, y+CELL-10), 3)
                    pygame.draw.line(self.screen, C_WHITE, (x+CELL-10, y+10), (x+10, y+CELL-10), 3)

    def draw_coordinates(self, ox, oy):
        for i in range(10):
            letter = self.fonts["small"].render(COLS[i], True, C_WHITE)
            self.screen.blit(letter, (ox + i * CELL + (CELL // 2 - letter.get_width() // 2), oy - 25))
            number = self.fonts["small"].render(str(i + 1), True, C_WHITE)
            self.screen.blit(number, (ox - 25, oy + i * CELL + (CELL // 2 - number.get_height() // 2)))

    def draw_timer(self):
        if self.phase in (Phase.PLAYER_TURN, Phase.P2_TURN):
            elapsed = time.time() - self.turn_start_time
            ratio = max(0, (TURN_LIMIT - elapsed) / TURN_LIMIT)
            color = C_GREEN if ratio > 0.3 else C_RED
            bar_x = RIGHT_BOARD_X if self.phase == Phase.PLAYER_TURN else LEFT_BOARD_X
            bar_w = GRID_COLS * CELL
            pygame.draw.rect(self.screen, C_PANEL_BG, (bar_x, BOARD_Y - 45, bar_w, 8))
            pygame.draw.rect(self.screen, color, (bar_x, BOARD_Y - 45, int(bar_w * ratio), 8))
            t_txt = self.fonts["tiny"].render(f"Залишилось: {int(TURN_LIMIT - elapsed)}с", True, C_WHITE)
            self.screen.blit(t_txt, (bar_x, BOARD_Y - 65))

    def draw_neon_box(self, rect, color, width=2, glow=True):
        pygame.draw.rect(self.screen, (10, 15, 30), rect, border_radius=10)
        if glow:
            for i in range(1, 5):
                alpha = 150 // (i * 2)
                s = pygame.Surface((rect.width + i*2, rect.height + i*2), pygame.SRCALPHA)
                pygame.draw.rect(s, (*color, alpha), s.get_rect(), border_radius=10+i, width=i)
                self.screen.blit(s, (rect.x - i, rect.y - i))
        pygame.draw.rect(self.screen, color, rect, border_radius=10, width=width)

    def draw(self):
        self.screen.fill(C_BG)
        
        if self.phase == Phase.MAIN_MENU:
            bobbing = int(10 * (1 + (pygame.time.get_ticks() // 500) % 2)) 
            self.screen.blit(self.deco_left, (80, 420 + bobbing))
            self.screen.blit(self.deco_right, (WINDOW_W - 260, 420 - bobbing))

            pulse = abs(127 - (pygame.time.get_ticks() // 6) % 255)
            title_color = (240, 200 + pulse // 4, 60)
            shadow_color = (40, 120, 255)
            
            title_text = "МОРСЬКИЙ БІЙ 2026"
            t_surf = self.fonts["title"].render(title_text, True, title_color)
            t_shadow = self.fonts["title"].render(title_text, True, shadow_color)
            
            self.screen.blit(t_shadow, (WINDOW_W//2 - t_surf.get_width()//2 + 3, 103))
            self.screen.blit(t_surf, (WINDOW_W//2 - t_surf.get_width()//2, 100))

            menu_box = pygame.Rect(WINDOW_W//2 - 200, 240, 400, 200)
            self.draw_neon_box(menu_box, C_NEON_BLUE, width=1)

            for i, txt in enumerate(["ГРАТИ ПРОТИ ШІ", "ГРА НА ДВОХ (PVP)"]):
                btn_rect = pygame.Rect(WINDOW_W//2 - 160, 270 + i*90, 320, 65)
                self.draw_neon_box(btn_rect, C_NEON_BLUE, width=2)
                btn_label = self.fonts["med"].render(txt, True, C_WHITE)
                self.screen.blit(btn_label, (btn_rect.centerx - btn_label.get_width()//2, btn_rect.centery - btn_label.get_height()//2))
        
        elif self.phase in (Phase.P1_PLACE, Phase.P2_PLACE):
            title = "ГРАВЕЦЬ 1: РОЗСТАНОВКА" if self.phase == Phase.P1_PLACE else "ГРАВЕЦЬ 2: РОЗСТАНОВКА"
            txt = self.fonts["med"].render(title, True, C_YELLOW)
            self.screen.blit(txt, (CENTER_BOARD_X, 50))
            
            hint = self.fonts["small"].render("Пробіл - повернути корабль | Клавіша A - авто", True, C_WHITE)
            self.screen.blit(hint, (CENTER_BOARD_X, BOARD_Y + GRID_ROWS * CELL + 70))

            pygame.draw.rect(self.screen, C_PANEL_BG, self.auto_btn_rect, border_radius=5)
            pygame.draw.rect(self.screen, C_GRID, self.auto_btn_rect, width=1, border_radius=5)
            auto_txt = self.fonts["small"].render("АВТО", True, C_GREEN)
            self.screen.blit(auto_txt, (self.auto_btn_rect.centerx - auto_txt.get_width()//2, self.auto_btn_rect.centery - auto_txt.get_height()//2))

            if self.placement.is_finished():
                pygame.draw.rect(self.screen, (40, 70, 40), self.confirm_btn_rect, border_radius=5)
                pygame.draw.rect(self.screen, C_GREEN, self.confirm_btn_rect, width=2, border_radius=5)
                label = "ПОЧАТИ ГРУ" if (not self.multiplayer or self.phase == Phase.P2_PLACE) else "ДАЛІ"
                conf_txt = self.fonts["small"].render(label, True, C_WHITE)
                self.screen.blit(conf_txt, (self.confirm_btn_rect.centerx - conf_txt.get_width()//2, self.confirm_btn_rect.centery - conf_txt.get_height()//2))

            self.draw_coordinates(CENTER_BOARD_X, BOARD_Y)
            active_board = self.p1_board if self.phase == Phase.P1_PLACE else self.p2_board
            self.draw_board_base(active_board, CENTER_BOARD_X, BOARD_Y, reveal=True)
            
            if not self.placement.is_finished():
                m_pos = pygame.mouse.get_pos()
                cell = self.get_board_cell(m_pos, CENTER_BOARD_X)
                if cell:
                    r, c = cell
                    cells = self.placement.preview_cells(r, c)
                    possible = active_board.can_place(cells)
                    for (pr, pc) in cells:
                        if 0 <= pr < 10 and 0 <= pc < 10:
                            s_color = (60, 200, 100, 150) if possible else (220, 60, 60, 150)
                            s = pygame.Surface((CELL-2, CELL-2), pygame.SRCALPHA)
                            s.fill(s_color)
                            self.screen.blit(s, (CENTER_BOARD_X + pc*CELL + 1, BOARD_Y + pr*CELL + 1))
        
        else:
            self.draw_coordinates(LEFT_BOARD_X, BOARD_Y)
            self.draw_coordinates(RIGHT_BOARD_X, BOARD_Y)
            
            p1_reveal = True if not self.multiplayer else (self.phase == Phase.GAME_OVER)
            p2_reveal = (self.phase == Phase.GAME_OVER)

            self.draw_board_base(self.p1_board, LEFT_BOARD_X, BOARD_Y, reveal=p1_reveal)
            self.draw_board_base(self.p2_board, RIGHT_BOARD_X, BOARD_Y, reveal=p2_reveal)
            self.draw_timer()
            
            self.draw_fleet_stats(LEFT_BOARD_X + (GRID_COLS * CELL) + 20, BOARD_Y, self.p1_board, "Флот Гравця 1")
            self.draw_fleet_stats(RIGHT_BOARD_X + (GRID_COLS * CELL) + 20, BOARD_Y, self.p2_board, "Флот Гравця 2")
            
            ly = LOG_Y
            for m, c in self.log:
                self.screen.blit(self.fonts["small"].render(m, True, c), (LOG_X, ly))
                ly += 20
            
            if self.phase == Phase.GAME_OVER:
                res = self.fonts["title"].render(f"ПЕРЕМІГ: {self.winner}", True, C_GREEN)
                self.screen.blit(res, (WINDOW_W//2 - res.get_width()//2, WINDOW_H//2))

        for ex in self.explosions:
            ex.draw(self.screen)

        pygame.display.flip()

    def draw_fleet_stats(self, x, y, board, title):
        stats = board.get_fleet_stats()
        box_rect = pygame.Rect(x - 5, y - 30, 185, 135)
        self.draw_neon_box(box_rect, C_NEON_BLUE, width=1, glow=False)
        
        title_surf = self.fonts["tiny"].render(title, True, C_YELLOW)
        self.screen.blit(title_surf, (box_rect.centerx - title_surf.get_width()//2, y - 25))
        
        curr_y = y + 5
        for name, length, _ in FLEET:
            alive, killed = stats[length]
            status_icon = self.icon_check if alive > 0 else self.icon_cross
            color = C_WHITE if alive > 0 else C_SUNK
            
            self.screen.blit(status_icon, (x + 5, curr_y))
            
            txt_str = f"{name}: {alive}/{alive+killed}"
            txt = self.fonts["tiny"].render(txt_str, True, color)
            self.screen.blit(txt, (x + 30, curr_y + 2))
            
            curr_y += 24

    def run(self):
        while True:
            self.handle_events()
            self.update()
            self.clock.tick(60)
            self.draw()

if __name__ == "__main__":
    Game().run()