from __future__ import annotations

from abc import ABC, abstractmethod
import random
import sys
from dataclasses import dataclass, field

try:
    import pygame
except KeyboardInterrupt:
    raise SystemExit(0)


WINDOW_WIDTH = 960
WINDOW_HEIGHT = 600
FPS = 60
GRID_SIZE = 10
CELL_SIZE = 36
GRID_ORIGIN_X = 180
GRID_ORIGIN_Y = 130
BATTLE_LEFT_GRID_X = 60
BATTLE_RIGHT_GRID_X = 520
BATTLE_GRID_Y = 130
SHIP_START_X = 610
SHIP_START_Y = 160

BG_COLOR = (20, 30, 45)
PANEL_COLOR = (33, 49, 70)
TEXT_COLOR = (238, 244, 250)
SUBTEXT_COLOR = (173, 188, 205)
BUTTON_COLOR = (58, 127, 186)
BUTTON_HOVER_COLOR = (74, 147, 211)
BUTTON_TEXT_COLOR = (250, 250, 250)
OUTLINE_COLOR = (16, 22, 32)
GRID_COLOR = (76, 108, 141)
SHIP_AREA_COLOR = (40, 58, 82)
LABEL_COLOR = (208, 220, 233)
SHIP_COLOR = (130, 150, 173)
SHIP_DRAG_COLOR = (154, 176, 201)
HIT_COLOR = (219, 94, 77)
MISS_COLOR = (201, 214, 230)
SUNK_COLOR = (120, 48, 40)
REVEALED_ADJACENT_COLOR = (92, 108, 126)


@dataclass
class Button:
    rect: pygame.Rect
    label: str

    def draw(self, screen: pygame.Surface, font: pygame.font.Font, mouse_pos: tuple[int, int]) -> None:
        color = BUTTON_HOVER_COLOR if self.rect.collidepoint(mouse_pos) else BUTTON_COLOR
        pygame.draw.rect(screen, color, self.rect, border_radius=10)
        pygame.draw.rect(screen, OUTLINE_COLOR, self.rect, width=2, border_radius=10)

        text_surface = font.render(self.label, True, BUTTON_TEXT_COLOR)
        text_rect = text_surface.get_rect(center=self.rect.center)
        screen.blit(text_surface, text_rect)

    def clicked(self, pos: tuple[int, int]) -> bool:
        return self.rect.collidepoint(pos)


@dataclass(frozen=True)
class ModeOption:
    mode_id: str
    label: str


@dataclass
class ShipPlacement:
    ship_id: int
    length: int
    side_position: tuple[int, int]
    x: int
    y: int
    placed_cells: tuple[tuple[int, int], ...] | None = None
    is_dragging: bool = False
    drag_offset: tuple[int, int] = (0, 0)
    is_vertical: bool = False

    def rect(self) -> pygame.Rect:
        width = CELL_SIZE if self.is_vertical else self.length * CELL_SIZE
        height = self.length * CELL_SIZE if self.is_vertical else CELL_SIZE
        return pygame.Rect(self.x, self.y, width, height)

    def reset_to_side(self) -> None:
        self.x, self.y = self.side_position
        self.placed_cells = None
        self.is_dragging = False
        self.is_vertical = False


@dataclass
class PlayerSetupState:
    ships: list[ShipPlacement]
    occupied_cells: set[tuple[int, int]] = field(default_factory=set)


@dataclass
class BattlePlayerState:
    ships: list[set[tuple[int, int]]]
    hits: set[tuple[int, int]] = field(default_factory=set)
    misses: set[tuple[int, int]] = field(default_factory=set)


@dataclass
class BattleState:
    players: dict[int, BattlePlayerState]
    current_player_index: int = 1
    winner_index: int | None = None
    message: str = "Player 1 turn. Fire at Player 2 field"


@dataclass(frozen=True)
class MenuOption:
    option_id: str
    label: str


def create_player_setup_state() -> PlayerSetupState:
    lengths = [4, 3, 3, 2, 2, 2, 1, 1, 1, 1]
    side_positions = [
        (SHIP_START_X, SHIP_START_Y),
        (SHIP_START_X, SHIP_START_Y + 60),
        (SHIP_START_X, SHIP_START_Y + 100),
        (SHIP_START_X, SHIP_START_Y + 150),
        (SHIP_START_X, SHIP_START_Y + 190),
        (SHIP_START_X, SHIP_START_Y + 230),
        (SHIP_START_X + 150, SHIP_START_Y + 60),
        (SHIP_START_X + 150, SHIP_START_Y + 100),
        (SHIP_START_X + 150, SHIP_START_Y + 140),
        (SHIP_START_X + 150, SHIP_START_Y + 180),
    ]
    ships: list[ShipPlacement] = []
    for index, (length, side_pos) in enumerate(zip(lengths, side_positions)):
        ships.append(
            ShipPlacement(
                ship_id=index,
                length=length,
                side_position=side_pos,
                x=side_pos[0],
                y=side_pos[1],
            )
        )
    return PlayerSetupState(ships=ships)


class BaseGameMode(ABC):
    mode_id: str = ""
    label: str = ""

    @abstractmethod
    def on_selected(self, app: "BattleshipMenuApp") -> None:
        """Called when user picks this mode from dropdown."""


class LocalPlayMode(BaseGameMode):
    mode_id = "local"
    label = "Play Local"

    def on_selected(self, app: "BattleshipMenuApp") -> None:
        app.selected_mode_id = self.mode_id
        app.start_local_setup()


@dataclass
class GameModeRegistry:
    _mode_classes: dict[str, type[BaseGameMode]] = field(default_factory=dict)

    def register(self, mode_cls: type[BaseGameMode]) -> None:
        if not mode_cls.mode_id:
            raise ValueError("mode_id must be non-empty")
        if not mode_cls.label:
            raise ValueError("label must be non-empty")
        self._mode_classes[mode_cls.mode_id] = mode_cls

    def options(self) -> list[ModeOption]:
        return [ModeOption(mode_id=mode.mode_id, label=mode.label) for mode in self._mode_classes.values()]

    def create(self, mode_id: str) -> BaseGameMode | None:
        mode_cls = self._mode_classes.get(mode_id)
        if mode_cls is None:
            return None
        return mode_cls()

    def menu_options(self) -> list[MenuOption]:
        return [MenuOption(option_id=mode.mode_id, label=mode.label) for mode in self._mode_classes.values()]


class Screen(ABC):
    @abstractmethod
    def handle_event(self, app: "BattleshipMenuApp", event: pygame.event.Event) -> None:
        pass

    @abstractmethod
    def draw(self, app: "BattleshipMenuApp") -> None:
        pass


@dataclass
class MainMenuScreen(Screen):
    start_button: Button = field(default_factory=lambda: Button(pygame.Rect(340, 250, 280, 68), "Start Game"))
    settings_button: Button = field(default_factory=lambda: Button(pygame.Rect(340, 340, 280, 68), "Settings"))

    def handle_event(self, app: "BattleshipMenuApp", event: pygame.event.Event) -> None:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return
        if self.start_button.clicked(event.pos):
            app.show_mode_selection()
        elif self.settings_button.clicked(event.pos):
            app.dropdown_open = False

    def draw(self, app: "BattleshipMenuApp") -> None:
        app.draw_frame("Main Menu", title_text="Battleship")
        mouse_pos = pygame.mouse.get_pos()
        self.start_button.draw(app.screen, app.button_font, mouse_pos)
        self.settings_button.draw(app.screen, app.button_font, mouse_pos)


@dataclass
class ModeSelectionScreen(Screen):
    select_button: Button = field(default_factory=lambda: Button(pygame.Rect(340, 280, 280, 68), "Select"))
    back_button: Button = field(default_factory=lambda: Button(pygame.Rect(340, 370, 280, 68), "Back"))

    def handle_event(self, app: "BattleshipMenuApp", event: pygame.event.Event) -> None:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        if self.select_button.clicked(event.pos):
            app.dropdown_open = not app.dropdown_open
            return

        if self.back_button.clicked(event.pos):
            app.show_main_menu()
            return

        if not app.dropdown_open:
            return

        option_buttons = self._build_option_buttons(app.mode_registry.options())
        for mode_id, button in option_buttons:
            if button.clicked(event.pos):
                mode = app.mode_registry.create(mode_id)
                if mode is not None:
                    mode.on_selected(app)
                app.dropdown_open = False
                return

        app.dropdown_open = False

    def draw(self, app: "BattleshipMenuApp") -> None:
        app.draw_frame("Mode Selection")
        mouse_pos = pygame.mouse.get_pos()

        self.select_button.draw(app.screen, app.button_font, mouse_pos)
        self.back_button.draw(app.screen, app.button_font, mouse_pos)

        if not app.dropdown_open:
            return

        option_buttons = self._build_option_buttons(app.mode_registry.options())
        popup_height = 16 + len(option_buttons) * 64
        popup_rect = pygame.Rect(330, 238, 300, popup_height)
        pygame.draw.rect(app.screen, PANEL_COLOR, popup_rect, border_radius=10)
        pygame.draw.rect(app.screen, OUTLINE_COLOR, popup_rect, width=2, border_radius=10)

        for _, button in option_buttons:
            button.draw(app.screen, app.dropdown_font, mouse_pos)

    def _build_option_buttons(self, options: list[ModeOption]) -> list[tuple[str, Button]]:
        buttons: list[tuple[str, Button]] = []
        start_y = 246
        for index, option in enumerate(options):
            button_rect = pygame.Rect(340, start_y + index * 64, 280, 56)
            buttons.append((option.mode_id, Button(button_rect, option.label)))
        return buttons


@dataclass
class LocalSetupScreen(Screen):
    auto_place_button: Button = field(default_factory=lambda: Button(pygame.Rect(120, 535, 220, 50), "Auto Place"))
    next_button: Button = field(default_factory=lambda: Button(pygame.Rect(360, 535, 240, 50), "Next"))

    def handle_event(self, app: "BattleshipMenuApp", event: pygame.event.Event) -> None:
        state = app.get_active_setup_state()

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.auto_place_button.clicked(event.pos):
                self._auto_place_ships(state)
                return
            if self.next_button.clicked(event.pos):
                if self._all_ships_placed(state):
                    self._finish_player_setup(app)
                return
            self._start_drag(state, event.pos)
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 3:
            self._rotate_ship_at(state, event.pos)
            return

        if event.type == pygame.MOUSEMOTION:
            self._update_drag(state, event.pos)
            return

        if event.type == pygame.MOUSEBUTTONUP and event.button == 1:
            self._drop_drag(state)

    def draw(self, app: "BattleshipMenuApp") -> None:
        state = app.get_active_setup_state()
        app.screen.fill(BG_COLOR)

        subtitle = app.subtitle_font.render(f"Player {app.setup_player_index} Setup", True, SUBTEXT_COLOR)
        app.screen.blit(subtitle, (WINDOW_WIDTH // 2 - subtitle.get_width() // 2, 24))

        board_panel = pygame.Rect(140, 110, 430, 390)
        ships_panel = pygame.Rect(590, 110, 230, 390)
        pygame.draw.rect(app.screen, PANEL_COLOR, board_panel, border_radius=12)
        pygame.draw.rect(app.screen, OUTLINE_COLOR, board_panel, width=2, border_radius=12)
        pygame.draw.rect(app.screen, SHIP_AREA_COLOR, ships_panel, border_radius=12)
        pygame.draw.rect(app.screen, OUTLINE_COLOR, ships_panel, width=2, border_radius=12)

        ships_title = app.small_font.render("Ships Area", True, LABEL_COLOR)
        app.screen.blit(ships_title, (ships_panel.centerx - ships_title.get_width() // 2, 126))

        self._draw_grid(app, state)
        self._draw_ships(app, state)

        rotate_hint = app.hint_font.render("Right-click a ship to rotate it", True, LABEL_COLOR)
        app.screen.blit(rotate_hint, (GRID_ORIGIN_X, 505))

        mouse_pos = pygame.mouse.get_pos()
        self.auto_place_button.draw(app.screen, app.dropdown_font, mouse_pos)
        self.next_button.draw(app.screen, app.button_font, mouse_pos)

    def _draw_grid(self, app: "BattleshipMenuApp", state: PlayerSetupState) -> None:
        for col in range(GRID_SIZE):
            label = chr(ord("A") + col)
            label_surface = app.small_font.render(label, True, LABEL_COLOR)
            x = GRID_ORIGIN_X + col * CELL_SIZE + CELL_SIZE // 2
            app.screen.blit(label_surface, (x - label_surface.get_width() // 2, GRID_ORIGIN_Y - 28))

        for row in range(GRID_SIZE):
            label_surface = app.small_font.render(str(row + 1), True, LABEL_COLOR)
            y = GRID_ORIGIN_Y + row * CELL_SIZE + CELL_SIZE // 2
            app.screen.blit(label_surface, (GRID_ORIGIN_X - 28, y - label_surface.get_height() // 2))

        for row in range(GRID_SIZE):
            for col in range(GRID_SIZE):
                rect = pygame.Rect(
                    GRID_ORIGIN_X + col * CELL_SIZE,
                    GRID_ORIGIN_Y + row * CELL_SIZE,
                    CELL_SIZE,
                    CELL_SIZE,
                )
                pygame.draw.rect(app.screen, GRID_COLOR, rect)
                pygame.draw.rect(app.screen, OUTLINE_COLOR, rect, width=1)

        for row, col in state.occupied_cells:
            rect = pygame.Rect(
                GRID_ORIGIN_X + col * CELL_SIZE,
                GRID_ORIGIN_Y + row * CELL_SIZE,
                CELL_SIZE,
                CELL_SIZE,
            )
            pygame.draw.rect(app.screen, SHIP_COLOR, rect)
            pygame.draw.rect(app.screen, OUTLINE_COLOR, rect, width=1)

    def _draw_ships(self, app: "BattleshipMenuApp", state: PlayerSetupState) -> None:
        for ship in state.ships:
            if ship.placed_cells is not None and not ship.is_dragging:
                continue

            ship_rect = ship.rect()
            color = SHIP_DRAG_COLOR if ship.is_dragging else SHIP_COLOR
            pygame.draw.rect(app.screen, color, ship_rect, border_radius=8)
            pygame.draw.rect(app.screen, OUTLINE_COLOR, ship_rect, width=2, border_radius=8)

    def _start_drag(self, state: PlayerSetupState, mouse_pos: tuple[int, int]) -> None:
        for ship in reversed(state.ships):
            if not ship.rect().collidepoint(mouse_pos):
                continue

            if ship.placed_cells is not None:
                for cell in ship.placed_cells:
                    state.occupied_cells.discard(cell)
                ship.placed_cells = None

            ship.is_dragging = True
            ship.drag_offset = (mouse_pos[0] - ship.x, mouse_pos[1] - ship.y)

            state.ships.remove(ship)
            state.ships.append(ship)
            return

    def _update_drag(self, state: PlayerSetupState, mouse_pos: tuple[int, int]) -> None:
        for ship in state.ships:
            if not ship.is_dragging:
                continue
            ship.x = mouse_pos[0] - ship.drag_offset[0]
            ship.y = mouse_pos[1] - ship.drag_offset[1]
            return

    def _drop_drag(self, state: PlayerSetupState) -> None:
        for ship in state.ships:
            if not ship.is_dragging:
                continue

            ship.is_dragging = False
            candidate = self._candidate_cells(ship)
            if candidate is None:
                ship.reset_to_side()
                return

            if self._touches_or_overlaps_other_ship(state, ship, candidate):
                ship.reset_to_side()
                return

            ship.placed_cells = candidate
            for cell in candidate:
                state.occupied_cells.add(cell)

            head_row, head_col = candidate[0]
            ship.x = GRID_ORIGIN_X + head_col * CELL_SIZE
            ship.y = GRID_ORIGIN_Y + head_row * CELL_SIZE
            return

    def _candidate_cells(self, ship: ShipPlacement) -> tuple[tuple[int, int], ...] | None:
        head_col = round((ship.x - GRID_ORIGIN_X) / CELL_SIZE)
        head_row = round((ship.y - GRID_ORIGIN_Y) / CELL_SIZE)

        if head_row < 0 or head_col < 0:
            return None

        if ship.is_vertical:
            if head_row + ship.length > GRID_SIZE or head_col >= GRID_SIZE:
                return None
            return tuple((head_row + offset, head_col) for offset in range(ship.length))

        if head_row >= GRID_SIZE or head_col + ship.length > GRID_SIZE:
            return None
        return tuple((head_row, head_col + offset) for offset in range(ship.length))

    def _touches_or_overlaps_other_ship(
        self,
        state: PlayerSetupState,
        active_ship: ShipPlacement,
        candidate_cells: tuple[tuple[int, int], ...],
    ) -> bool:
        blocked: set[tuple[int, int]] = set()
        for ship in state.ships:
            if ship is active_ship or ship.placed_cells is None:
                continue
            for row, col in ship.placed_cells:
                for d_row in (-1, 0, 1):
                    for d_col in (-1, 0, 1):
                        n_row = row + d_row
                        n_col = col + d_col
                        if 0 <= n_row < GRID_SIZE and 0 <= n_col < GRID_SIZE:
                            blocked.add((n_row, n_col))

        return any(cell in blocked for cell in candidate_cells)

    def _rotate_ship_at(self, state: PlayerSetupState, mouse_pos: tuple[int, int]) -> None:
        for ship in reversed(state.ships):
            if not ship.rect().collidepoint(mouse_pos):
                continue

            if ship.placed_cells is not None:
                for cell in ship.placed_cells:
                    state.occupied_cells.discard(cell)
                ship.placed_cells = None

            ship.is_vertical = not ship.is_vertical
            return

    def _all_ships_placed(self, state: PlayerSetupState) -> bool:
        return all(ship.placed_cells is not None for ship in state.ships)

    def _auto_place_ships(self, state: PlayerSetupState) -> None:
        max_layout_attempts = 500

        for _ in range(max_layout_attempts):
            self._reset_all_ships(state)
            ships_to_place = sorted(state.ships, key=lambda ship: ship.length, reverse=True)
            if self._place_all_randomly(state, ships_to_place):
                return

        self._reset_all_ships(state)

    def _reset_all_ships(self, state: PlayerSetupState) -> None:
        state.occupied_cells.clear()
        for ship in state.ships:
            ship.reset_to_side()

    def _place_all_randomly(self, state: PlayerSetupState, ships: list[ShipPlacement]) -> bool:
        for ship in ships:
            if not self._place_single_random_ship(state, ship):
                return False
        return True

    def _place_single_random_ship(self, state: PlayerSetupState, ship: ShipPlacement) -> bool:
        max_ship_attempts = 250
        for _ in range(max_ship_attempts):
            ship.is_vertical = bool(random.randint(0, 1))
            row, col = self._random_head_cell(ship)
            candidate = self._cells_from_head(ship, row, col)
            if candidate is None:
                continue
            if self._touches_or_overlaps_other_ship(state, ship, candidate):
                continue

            ship.placed_cells = candidate
            for cell in candidate:
                state.occupied_cells.add(cell)

            head_row, head_col = candidate[0]
            ship.x = GRID_ORIGIN_X + head_col * CELL_SIZE
            ship.y = GRID_ORIGIN_Y + head_row * CELL_SIZE
            return True

        return False

    def _random_head_cell(self, ship: ShipPlacement) -> tuple[int, int]:
        if ship.is_vertical:
            return random.randint(0, GRID_SIZE - ship.length), random.randint(0, GRID_SIZE - 1)
        return random.randint(0, GRID_SIZE - 1), random.randint(0, GRID_SIZE - ship.length)

    def _cells_from_head(self, ship: ShipPlacement, row: int, col: int) -> tuple[tuple[int, int], ...] | None:
        if ship.is_vertical:
            if row + ship.length > GRID_SIZE or col >= GRID_SIZE:
                return None
            return tuple((row + offset, col) for offset in range(ship.length))
        if row >= GRID_SIZE or col + ship.length > GRID_SIZE:
            return None
        return tuple((row, col + offset) for offset in range(ship.length))

    def _finish_player_setup(self, app: "BattleshipMenuApp") -> None:
        if app.setup_player_index == 1:
            app.setup_player_index = 2
        else:
            app.start_local_battle()


@dataclass
class LocalBattleScreen(Screen):
    back_button: Button = field(default_factory=lambda: Button(pygame.Rect(760, 535, 150, 50), "Menu"))

    def handle_event(self, app: "BattleshipMenuApp", event: pygame.event.Event) -> None:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        if self.back_button.clicked(event.pos):
            app.show_main_menu()
            return

        battle = app.battle_state
        if battle is None or battle.winner_index is not None:
            return

        shooter_index = battle.current_player_index
        target_index = 2 if shooter_index == 1 else 1
        shooter_name = f"Player {shooter_index}"
        target_name = f"Player {target_index}"

        target_origin_x = BATTLE_RIGHT_GRID_X if target_index == 2 else BATTLE_LEFT_GRID_X
        target_origin_y = BATTLE_GRID_Y
        cell = self._pixel_to_grid_cell(event.pos, target_origin_x, target_origin_y)
        if cell is None:
            battle.message = f"{shooter_name}: click {target_name} field"
            return

        target = battle.players[target_index]
        if cell in target.hits or cell in target.misses:
            battle.message = "Cell already targeted"
            return

        if cell in self._adjacent_cells_around_sunk_ships(target):
            battle.message = "Cell blocked"
            return

        if self._is_ship_cell(target, cell):
            target.hits.add(cell)
            if self._is_sunk(target, cell):
                battle.message = f"{shooter_name}: Sunk! Extra turn"
            else:
                battle.message = f"{shooter_name}: Hit! Extra turn"

            if self._all_ships_sunk(target):
                battle.winner_index = shooter_index
                app.show_winner_menu(shooter_index)
                battle.message = f"{shooter_name} wins"
            return

        target.misses.add(cell)
        battle.current_player_index = target_index
        next_target = 2 if battle.current_player_index == 1 else 1
        battle.message = f"{shooter_name}: Miss. Player {battle.current_player_index} turn. Fire at Player {next_target} field"

    def draw(self, app: "BattleshipMenuApp") -> None:
        battle = app.battle_state
        if battle is None:
            app.show_main_menu()
            return

        app.screen.fill(BG_COLOR)

        turn_text = (
            f"Player {battle.current_player_index} turn"
            if battle.winner_index is None
            else f"Winner: Player {battle.winner_index}"
        )
        turn_surface = app.title_font.render(turn_text, True, TEXT_COLOR)
        message = app.hint_font.render(battle.message, True, LABEL_COLOR)
        app.screen.blit(turn_surface, (WINDOW_WIDTH // 2 - turn_surface.get_width() // 2, 24))
        app.screen.blit(message, (WINDOW_WIDTH // 2 - message.get_width() // 2, 84))

        player_1 = battle.players[1]
        player_2 = battle.players[2]

        left_panel = pygame.Rect(35, 110, 405, 390)
        right_panel = pygame.Rect(495, 110, 405, 390)
        pygame.draw.rect(app.screen, PANEL_COLOR, left_panel, border_radius=12)
        pygame.draw.rect(app.screen, OUTLINE_COLOR, left_panel, width=2, border_radius=12)
        pygame.draw.rect(app.screen, PANEL_COLOR, right_panel, border_radius=12)
        pygame.draw.rect(app.screen, OUTLINE_COLOR, right_panel, width=2, border_radius=12)

        left_label = app.hint_font.render("Player 1 Field", True, LABEL_COLOR)
        right_label = app.hint_font.render("Player 2 Field", True, LABEL_COLOR)
        app.screen.blit(left_label, (BATTLE_LEFT_GRID_X, 505))
        app.screen.blit(right_label, (BATTLE_RIGHT_GRID_X, 505))

        self._draw_battle_grid(app, player_1, BATTLE_LEFT_GRID_X, BATTLE_GRID_Y, reveal_ships=False)
        self._draw_battle_grid(app, player_2, BATTLE_RIGHT_GRID_X, BATTLE_GRID_Y, reveal_ships=False)

        mouse_pos = pygame.mouse.get_pos()
        self.back_button.draw(app.screen, app.hint_font, mouse_pos)

    def _draw_battle_grid(
        self,
        app: "BattleshipMenuApp",
        player: BattlePlayerState,
        origin_x: int,
        origin_y: int,
        reveal_ships: bool,
    ) -> None:
        for col in range(GRID_SIZE):
            label = chr(ord("A") + col)
            label_surface = app.hint_font.render(label, True, LABEL_COLOR)
            x = origin_x + col * CELL_SIZE + CELL_SIZE // 2
            app.screen.blit(label_surface, (x - label_surface.get_width() // 2, origin_y - 31))

        for row in range(GRID_SIZE):
            label_surface = app.hint_font.render(str(row + 1), True, LABEL_COLOR)
            y = origin_y + row * CELL_SIZE + CELL_SIZE // 2
            app.screen.blit(label_surface, (origin_x - 24, y - label_surface.get_height() // 2))

        ship_cells = self._all_ship_cells(player)
        sunk_ship_cells = self._all_sunk_ship_cells(player)
        revealed_adjacent_cells = self._adjacent_cells_around_sunk_ships(player)
        for row in range(GRID_SIZE):
            for col in range(GRID_SIZE):
                rect = pygame.Rect(origin_x + col * CELL_SIZE, origin_y + row * CELL_SIZE, CELL_SIZE, CELL_SIZE)
                cell = (row, col)
                fill_color = GRID_COLOR
                if cell in player.misses:
                    fill_color = MISS_COLOR
                elif cell in player.hits:
                    fill_color = SUNK_COLOR if self._is_hit_on_sunk_ship(player, cell) else HIT_COLOR
                elif cell in revealed_adjacent_cells:
                    fill_color = REVEALED_ADJACENT_COLOR
                elif reveal_ships and cell in ship_cells:
                    fill_color = SHIP_COLOR

                pygame.draw.rect(app.screen, fill_color, rect)
                pygame.draw.rect(app.screen, OUTLINE_COLOR, rect, width=1)

    def _pixel_to_grid_cell(self, pos: tuple[int, int], origin_x: int, origin_y: int) -> tuple[int, int] | None:
        x, y = pos
        board_rect = pygame.Rect(origin_x, origin_y, GRID_SIZE * CELL_SIZE, GRID_SIZE * CELL_SIZE)
        if not board_rect.inflate(CELL_SIZE, CELL_SIZE).collidepoint(pos):
            return None

        x = min(max(x, origin_x), origin_x + GRID_SIZE * CELL_SIZE - 1)
        y = min(max(y, origin_y), origin_y + GRID_SIZE * CELL_SIZE - 1)

        col = (x - origin_x) // CELL_SIZE
        row = (y - origin_y) // CELL_SIZE
        if 0 <= row < GRID_SIZE and 0 <= col < GRID_SIZE:
            return (row, col)
        return None

    def _all_ship_cells(self, player: BattlePlayerState) -> set[tuple[int, int]]:
        cells: set[tuple[int, int]] = set()
        for ship in player.ships:
            cells.update(ship)
        return cells

    def _is_ship_cell(self, player: BattlePlayerState, cell: tuple[int, int]) -> bool:
        return any(cell in ship for ship in player.ships)

    def _is_sunk(self, player: BattlePlayerState, hit_cell: tuple[int, int]) -> bool:
        for ship in player.ships:
            if hit_cell in ship:
                return ship.issubset(player.hits)
        return False

    def _is_hit_on_sunk_ship(self, player: BattlePlayerState, cell: tuple[int, int]) -> bool:
        for ship in player.ships:
            if cell in ship:
                return ship.issubset(player.hits)
        return False

    def _all_ships_sunk(self, player: BattlePlayerState) -> bool:
        return all(ship.issubset(player.hits) for ship in player.ships)

    def _all_sunk_ship_cells(self, player: BattlePlayerState) -> set[tuple[int, int]]:
        cells: set[tuple[int, int]] = set()
        for ship in player.ships:
            if ship.issubset(player.hits):
                cells.update(ship)
        return cells

    def _adjacent_cells_around_sunk_ships(self, player: BattlePlayerState) -> set[tuple[int, int]]:
        adjacent: set[tuple[int, int]] = set()
        for ship in player.ships:
            if not ship.issubset(player.hits):
                continue
            for row, col in ship:
                for d_row in (-1, 0, 1):
                    for d_col in (-1, 0, 1):
                        n_row = row + d_row
                        n_col = col + d_col
                        if 0 <= n_row < GRID_SIZE and 0 <= n_col < GRID_SIZE:
                            candidate = (n_row, n_col)
                            if candidate not in ship:
                                adjacent.add(candidate)
        return adjacent


@dataclass
class WinnerMenuScreen(Screen):
    exit_button: Button = field(default_factory=lambda: Button(pygame.Rect(370, 505, 220, 50), "Exit"))

    def handle_event(self, app: "BattleshipMenuApp", event: pygame.event.Event) -> None:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        if self.exit_button.clicked(event.pos):
            app.running = False
            return

        options = self._build_option_buttons(app.mode_registry.menu_options())
        for option_id, button in options:
            if button.clicked(event.pos):
                mode = app.mode_registry.create(option_id)
                if mode is not None:
                    mode.on_selected(app)
                return

    def draw(self, app: "BattleshipMenuApp") -> None:
        app.draw_frame("Game Over")
        mouse_pos = pygame.mouse.get_pos()

        if app.battle_state is not None and app.battle_state.winner_index is not None:
            winner_text = f"Winner: Player {app.battle_state.winner_index}"
        else:
            winner_text = "Winner: Unknown"

        winner_surface = app.title_font.render(winner_text, True, TEXT_COLOR)
        app.screen.blit(winner_surface, (WINDOW_WIDTH // 2 - winner_surface.get_width() // 2, 210))

        options = self._build_option_buttons(app.mode_registry.menu_options())
        option_title = app.hint_font.render("Choose another game:", True, LABEL_COLOR)
        app.screen.blit(option_title, (WINDOW_WIDTH // 2 - option_title.get_width() // 2, 290))

        start_y = 320
        for index, (_, button) in enumerate(options):
            button.rect.y = start_y + index * 56
            button.draw(app.screen, app.button_font, mouse_pos)

        self.exit_button.draw(app.screen, app.button_font, mouse_pos)

    def _build_option_buttons(self, options: list[MenuOption]) -> list[tuple[str, Button]]:
        buttons: list[tuple[str, Button]] = []
        for index, option in enumerate(options):
            button_rect = pygame.Rect(320, 320 + index * 56, 320, 46)
            buttons.append((option.option_id, Button(button_rect, option.label)))
        return buttons


class BattleshipMenuApp:
    def __init__(self) -> None:
        pygame.init()
        pygame.display.set_caption("Morskii Boi - Menu")
        self.screen = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
        self.clock = pygame.time.Clock()

        self.title_font = pygame.font.SysFont("verdana", 56, bold=True)
        self.subtitle_font = pygame.font.SysFont("verdana", 24)
        self.button_font = pygame.font.SysFont("verdana", 30, bold=True)
        self.dropdown_font = pygame.font.SysFont("verdana", 24, bold=True)
        self.small_font = pygame.font.SysFont("verdana", 22)
        self.hint_font = pygame.font.SysFont("verdana", 18)

        self.mode_registry = GameModeRegistry()
        self.selected_mode_id: str | None = None
        self.dropdown_open = False
        self.setup_player_index = 1
        self.player_setup_states = {
            1: create_player_setup_state(),
            2: create_player_setup_state(),
        }
        self.battle_state: BattleState | None = None

        self.main_menu_screen = MainMenuScreen()
        self.mode_selection_screen = ModeSelectionScreen()
        self.local_setup_screen = LocalSetupScreen()
        self.local_battle_screen = LocalBattleScreen()
        self.winner_menu_screen = WinnerMenuScreen()
        self.current_screen: Screen = self.main_menu_screen
        self.running = True

    def register_mode(self, mode_cls: type[BaseGameMode]) -> None:
        self.mode_registry.register(mode_cls)

    def show_main_menu(self) -> None:
        self.dropdown_open = False
        self.battle_state = None
        self.current_screen = self.main_menu_screen

    def show_winner_menu(self, winner_index: int) -> None:
        self.dropdown_open = False
        if self.battle_state is not None:
            self.battle_state.winner_index = winner_index
        self.current_screen = self.winner_menu_screen

    def show_mode_selection(self) -> None:
        self.dropdown_open = False
        self.current_screen = self.mode_selection_screen

    def start_local_setup(self) -> None:
        self.dropdown_open = False
        self.battle_state = None
        self.setup_player_index = 1
        self.player_setup_states = {
            1: create_player_setup_state(),
            2: create_player_setup_state(),
        }
        self.current_screen = self.local_setup_screen

    def start_local_battle(self) -> None:
        player_1 = self._build_battle_player(self.player_setup_states[1])
        player_2 = self._build_battle_player(self.player_setup_states[2])
        self.battle_state = BattleState(
            players={1: player_1, 2: player_2},
            current_player_index=1,
            winner_index=None,
            message="Player 1 turn. Fire at Player 2 field",
        )
        self.current_screen = self.local_battle_screen

    def _build_battle_player(self, setup_state: PlayerSetupState) -> BattlePlayerState:
        ships: list[set[tuple[int, int]]] = []
        for ship in setup_state.ships:
            if ship.placed_cells is None:
                continue
            ships.append(set(ship.placed_cells))
        return BattlePlayerState(ships=ships)

    def get_active_setup_state(self) -> PlayerSetupState:
        return self.player_setup_states[self.setup_player_index]

    def draw_frame(self, subtitle_text: str, title_text: str | None = None) -> None:
        self.screen.fill(BG_COLOR)

        panel = pygame.Rect(180, 120, 600, 390)
        pygame.draw.rect(self.screen, PANEL_COLOR, panel, border_radius=14)
        pygame.draw.rect(self.screen, OUTLINE_COLOR, panel, width=2, border_radius=14)

        subtitle = self.subtitle_font.render(subtitle_text, True, SUBTEXT_COLOR)

        if title_text is not None:
            title = self.title_font.render(title_text, True, TEXT_COLOR)
            self.screen.blit(title, (WINDOW_WIDTH // 2 - title.get_width() // 2, 150))
            self.screen.blit(subtitle, (WINDOW_WIDTH // 2 - subtitle.get_width() // 2, 210))
        else:
            self.screen.blit(subtitle, (WINDOW_WIDTH // 2 - subtitle.get_width() // 2, 160))

    def run(self) -> None:
        try:
            while self.running:
                self.clock.tick(FPS)
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self.running = False
                    else:
                        self.current_screen.handle_event(self, event)

                self.current_screen.draw(self)
                pygame.display.flip()
        except KeyboardInterrupt:
            self.running = False
        finally:
            pygame.quit()
            sys.exit(0)


def main() -> None:
    app = BattleshipMenuApp()
    app.register_mode(LocalPlayMode)
    app.run()


if __name__ == "__main__":
    main()
