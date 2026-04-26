from __future__ import annotations

from abc import ABC, abstractmethod
import os
import random
import sys
import time
from dataclasses import dataclass, field
from typing import Any

sys.path.insert(0, os.path.dirname(__file__))

try:
    import pygame
except KeyboardInterrupt:
    raise SystemExit(0)

from multiplayer import MultiplayerClient, MultiplayerServerHandle, payload_to_ship_sets, start_multiplayer_server


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


@dataclass
class TextInput:
    rect: pygame.Rect
    text: str = ""
    placeholder: str = ""
    is_active: bool = False
    max_length: int = 128

    def handle_event(self, event: pygame.event.Event) -> bool:
        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            self.is_active = self.rect.collidepoint(event.pos)
            return self.is_active

        if event.type != pygame.KEYDOWN or not self.is_active:
            return False

        if event.key == pygame.K_BACKSPACE:
            self.text = self.text[:-1]
            return True

        if event.key in {pygame.K_RETURN, pygame.K_KP_ENTER, pygame.K_TAB}:
            return False

        if event.unicode and event.unicode.isprintable() and len(self.text) < self.max_length:
            self.text += event.unicode
            return True

        return False

    def draw(self, screen: pygame.Surface, font: pygame.font.Font) -> None:
        fill_color = (45, 63, 88) if self.is_active else (35, 50, 72)
        pygame.draw.rect(screen, fill_color, self.rect, border_radius=10)
        pygame.draw.rect(screen, OUTLINE_COLOR, self.rect, width=2, border_radius=10)

        display_text = self.text.strip() if self.text.strip() else self.placeholder
        text_color = TEXT_COLOR if self.text.strip() else SUBTEXT_COLOR
        text_surface = font.render(display_text, True, text_color)
        text_rect = text_surface.get_rect(midleft=(self.rect.x + 14, self.rect.centery))
        screen.blit(text_surface, text_rect)


def player_index_from_role(role: str | None) -> int | None:
    if role == "host":
        return 1
    if role == "client":
        return 2
    return None


def build_battle_state_from_snapshot(snapshot: dict[str, Any]) -> BattleState:
    players = {
        1: BattlePlayerState(
            ships=payload_to_ship_sets(snapshot.get("host_ships", [])),
            hits={(row, col) for row, col in snapshot.get("host_hits", [])},
            misses={(row, col) for row, col in snapshot.get("host_misses", [])},
        ),
        2: BattlePlayerState(
            ships=payload_to_ship_sets(snapshot.get("client_ships", [])),
            hits={(row, col) for row, col in snapshot.get("client_hits", [])},
            misses={(row, col) for row, col in snapshot.get("client_misses", [])},
        ),
    }
    current_player_index = player_index_from_role(snapshot.get("turn_role")) or 1
    winner_index = player_index_from_role(snapshot.get("winner_role"))
    message = snapshot.get("message", "")
    return BattleState(players=players, current_player_index=current_player_index, winner_index=winner_index, message=message)


def empty_multiplayer_setup_state() -> PlayerSetupState:
    return create_player_setup_state()


def grid_cell_rect(origin_x: int, origin_y: int, row: int, col: int) -> pygame.Rect:
    return pygame.Rect(origin_x + col * CELL_SIZE, origin_y + row * CELL_SIZE, CELL_SIZE, CELL_SIZE)


def draw_grid_labels(screen: pygame.Surface, font: pygame.font.Font, origin_x: int, origin_y: int, x_offset: int, y_offset: int) -> None:
    for col in range(GRID_SIZE):
        label = chr(ord("A") + col)
        label_surface = font.render(label, True, LABEL_COLOR)
        x = origin_x + col * CELL_SIZE + CELL_SIZE // 2
        screen.blit(label_surface, (x - label_surface.get_width() // 2, origin_y - y_offset))

    for row in range(GRID_SIZE):
        label_surface = font.render(str(row + 1), True, LABEL_COLOR)
        y = origin_y + row * CELL_SIZE + CELL_SIZE // 2
        screen.blit(label_surface, (origin_x - x_offset, y - label_surface.get_height() // 2))


def iter_ship_cells(ships: list[set[tuple[int, int]]]) -> set[tuple[int, int]]:
    cells: set[tuple[int, int]] = set()
    for ship in ships:
        cells.update(ship)
    return cells


def ship_is_sunk(ship: set[tuple[int, int]], hits: set[tuple[int, int]]) -> bool:
    return ship.issubset(hits)


def adjacent_cells_around_ship(ship: set[tuple[int, int]]) -> set[tuple[int, int]]:
    adjacent: set[tuple[int, int]] = set()
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


def build_button_column(
    items: list[tuple[str, str]],
    x: int,
    start_y: int,
    width: int,
    height: int,
    gap: int,
) -> list[tuple[str, Button]]:
    buttons: list[tuple[str, Button]] = []
    for index, (option_id, label) in enumerate(items):
        button_rect = pygame.Rect(x, start_y + index * gap, width, height)
        buttons.append((option_id, Button(button_rect, label)))
    return buttons


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


class MultiplayerPlayMode(BaseGameMode):
    mode_id = "multiplayer"
    label = "Play Multiplayer"

    def on_selected(self, app: "BattleshipMenuApp") -> None:
        app.selected_mode_id = self.mode_id
        app.show_multiplayer_menu()


@dataclass
class GameModeRegistry:
    _mode_classes: dict[str, type[BaseGameMode]] = field(default_factory=dict)

    def _mode_entries(self) -> list[BaseGameMode]:
        return list(self._mode_classes.values())

    def register(self, mode_cls: type[BaseGameMode]) -> None:
        if not mode_cls.mode_id:
            raise ValueError("mode_id must be non-empty")
        if not mode_cls.label:
            raise ValueError("label must be non-empty")
        self._mode_classes[mode_cls.mode_id] = mode_cls

    def options(self) -> list[ModeOption]:
        return [ModeOption(mode_id=mode.mode_id, label=mode.label) for mode in self._mode_entries()]

    def create(self, mode_id: str) -> BaseGameMode | None:
        mode_cls = self._mode_classes.get(mode_id)
        if mode_cls is None:
            return None
        return mode_cls()

    def menu_options(self) -> list[MenuOption]:
        return [MenuOption(option_id=mode.mode_id, label=mode.label) for mode in self._mode_entries()]


class Screen(ABC):
    def update(self, app: "BattleshipMenuApp") -> None:
        return

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
        items = [(option.mode_id, option.label) for option in options]
        return build_button_column(items, 340, 246, 280, 56, 64)


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
        draw_grid_labels(app.screen, app.small_font, GRID_ORIGIN_X, GRID_ORIGIN_Y, x_offset=28, y_offset=28)

        for row in range(GRID_SIZE):
            for col in range(GRID_SIZE):
                rect = grid_cell_rect(GRID_ORIGIN_X, GRID_ORIGIN_Y, row, col)
                pygame.draw.rect(app.screen, GRID_COLOR, rect)
                pygame.draw.rect(app.screen, OUTLINE_COLOR, rect, width=1)

        for row, col in state.occupied_cells:
            rect = grid_cell_rect(GRID_ORIGIN_X, GRID_ORIGIN_Y, row, col)
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
        draw_grid_labels(app.screen, app.hint_font, origin_x, origin_y, x_offset=24, y_offset=31)

        ship_cells = self._all_ship_cells(player)
        revealed_adjacent_cells = self._adjacent_cells_around_sunk_ships(player)
        for row in range(GRID_SIZE):
            for col in range(GRID_SIZE):
                rect = grid_cell_rect(origin_x, origin_y, row, col)
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
        return iter_ship_cells(player.ships)

    def _is_ship_cell(self, player: BattlePlayerState, cell: tuple[int, int]) -> bool:
        return any(cell in ship for ship in player.ships)

    def _is_sunk(self, player: BattlePlayerState, hit_cell: tuple[int, int]) -> bool:
        for ship in player.ships:
            if hit_cell in ship:
                return ship_is_sunk(ship, player.hits)
        return False

    def _is_hit_on_sunk_ship(self, player: BattlePlayerState, cell: tuple[int, int]) -> bool:
        for ship in player.ships:
            if cell in ship:
                return ship_is_sunk(ship, player.hits)
        return False

    def _all_ships_sunk(self, player: BattlePlayerState) -> bool:
        return all(ship_is_sunk(ship, player.hits) for ship in player.ships)

    def _all_sunk_ship_cells(self, player: BattlePlayerState) -> set[tuple[int, int]]:
        cells: set[tuple[int, int]] = set()
        for ship in player.ships:
            if ship_is_sunk(ship, player.hits):
                cells.update(ship)
        return cells

    def _adjacent_cells_around_sunk_ships(self, player: BattlePlayerState) -> set[tuple[int, int]]:
        adjacent: set[tuple[int, int]] = set()
        for ship in player.ships:
            if not ship_is_sunk(ship, player.hits):
                continue
            adjacent.update(adjacent_cells_around_ship(ship))
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
        items = [(option.option_id, option.label) for option in options]
        return build_button_column(items, 320, 320, 320, 46, 56)


@dataclass
class MultiplayerMenuScreen(Screen):
    host_button: Button = field(default_factory=lambda: Button(pygame.Rect(320, 250, 320, 68), "Host Game"))
    join_button: Button = field(default_factory=lambda: Button(pygame.Rect(320, 340, 320, 68), "Join Game"))
    back_button: Button = field(default_factory=lambda: Button(pygame.Rect(320, 430, 320, 68), "Back"))

    def handle_event(self, app: "BattleshipMenuApp", event: pygame.event.Event) -> None:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        if self.host_button.clicked(event.pos):
            app.start_multiplayer_host()
            return

        if self.join_button.clicked(event.pos):
            app.show_multiplayer_join()
            return

        if self.back_button.clicked(event.pos):
            app.show_main_menu()

    def draw(self, app: "BattleshipMenuApp") -> None:
        app.draw_frame("Multiplayer")
        mouse_pos = pygame.mouse.get_pos()
        info = app.hint_font.render("Host starts a local server. Join connects to it.", True, LABEL_COLOR)
        app.screen.blit(info, (WINDOW_WIDTH // 2 - info.get_width() // 2, 210))
        self.host_button.draw(app.screen, app.button_font, mouse_pos)
        self.join_button.draw(app.screen, app.button_font, mouse_pos)
        self.back_button.draw(app.screen, app.button_font, mouse_pos)


@dataclass
class MultiplayerJoinScreen(Screen):
    address_input: TextInput = field(
        default_factory=lambda: TextInput(
            pygame.Rect(250, 270, 460, 48),
            text="127.0.0.1:8765",
            placeholder="http://127.0.0.1:8765",
            is_active=True,
        )
    )
    connect_button: Button = field(default_factory=lambda: Button(pygame.Rect(360, 340, 240, 56), "Connect"))
    back_button: Button = field(default_factory=lambda: Button(pygame.Rect(360, 410, 240, 56), "Back"))

    def handle_event(self, app: "BattleshipMenuApp", event: pygame.event.Event) -> None:
        handled_text = self.address_input.handle_event(event)
        if event.type == pygame.KEYDOWN and event.key in {pygame.K_RETURN, pygame.K_KP_ENTER} and self.address_input.is_active:
            self._connect(app)
            return

        if handled_text:
            return

        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        if self.connect_button.clicked(event.pos):
            self._connect(app)
            return

        if self.back_button.clicked(event.pos):
            app.show_multiplayer_menu()

    def draw(self, app: "BattleshipMenuApp") -> None:
        app.draw_frame("Join Multiplayer")
        mouse_pos = pygame.mouse.get_pos()

        prompt = app.hint_font.render("Enter host address, for example 127.0.0.1:8765", True, LABEL_COLOR)
        app.screen.blit(prompt, (WINDOW_WIDTH // 2 - prompt.get_width() // 2, 220))
        self.address_input.draw(app.screen, app.button_font)
        self.connect_button.draw(app.screen, app.button_font, mouse_pos)
        self.back_button.draw(app.screen, app.button_font, mouse_pos)

        if app.multiplayer_status_message:
            status = app.hint_font.render(app.multiplayer_status_message, True, SUBTEXT_COLOR)
            app.screen.blit(status, (WINDOW_WIDTH // 2 - status.get_width() // 2, 480))

    def _connect(self, app: "BattleshipMenuApp") -> None:
        app.start_multiplayer_join(self.address_input.text)


@dataclass
class MultiplayerHostWaitScreen(Screen):
    back_button: Button = field(default_factory=lambda: Button(pygame.Rect(360, 480, 240, 56), "Back"))

    def update(self, app: "BattleshipMenuApp") -> None:
        app.sync_multiplayer_lobby()

    def handle_event(self, app: "BattleshipMenuApp", event: pygame.event.Event) -> None:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        if self.back_button.clicked(event.pos):
            app.stop_multiplayer_session()
            app.show_main_menu()

    def draw(self, app: "BattleshipMenuApp") -> None:
        app.draw_frame("Hosting Multiplayer")
        mouse_pos = pygame.mouse.get_pos()

        host_url = app.multiplayer_server.advertised_url if app.multiplayer_server is not None else ""
        host_url_surface = app.button_font.render(host_url, True, TEXT_COLOR)
        app.screen.blit(host_url_surface, (WINDOW_WIDTH // 2 - host_url_surface.get_width() // 2, 250))

        waiting_text = app.hint_font.render("Waiting for client connection...", True, LABEL_COLOR)
        app.screen.blit(waiting_text, (WINDOW_WIDTH // 2 - waiting_text.get_width() // 2, 320))

        if app.multiplayer_status_message:
            status = app.hint_font.render(app.multiplayer_status_message, True, SUBTEXT_COLOR)
            app.screen.blit(status, (WINDOW_WIDTH // 2 - status.get_width() // 2, 360))

        self.back_button.draw(app.screen, app.button_font, mouse_pos)


@dataclass
class MultiplayerSetupScreen(LocalSetupScreen):
    def __post_init__(self) -> None:
        self.next_button.label = "Ready"

    def update(self, app: "BattleshipMenuApp") -> None:
        app.sync_multiplayer_setup()

    def handle_event(self, app: "BattleshipMenuApp", event: pygame.event.Event) -> None:
        state = app.multiplayer_setup_state
        if state is None:
            return

        if event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            if self.auto_place_button.clicked(event.pos):
                self._auto_place_ships(state)
                return
            if self.next_button.clicked(event.pos):
                if self._all_ships_placed(state):
                    app.submit_multiplayer_setup()
                else:
                    app.multiplayer_status_message = "Place all ships before sending your field"
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
        state = app.multiplayer_setup_state
        if state is None:
            app.show_multiplayer_menu()
            return

        app.screen.fill(BG_COLOR)

        subtitle = app.subtitle_font.render("Multiplayer Setup", True, SUBTEXT_COLOR)
        app.screen.blit(subtitle, (WINDOW_WIDTH // 2 - subtitle.get_width() // 2, 24))

        board_panel = pygame.Rect(140, 110, 430, 390)
        ships_panel = pygame.Rect(590, 110, 230, 390)
        pygame.draw.rect(app.screen, PANEL_COLOR, board_panel, border_radius=12)
        pygame.draw.rect(app.screen, OUTLINE_COLOR, board_panel, width=2, border_radius=12)
        pygame.draw.rect(app.screen, SHIP_AREA_COLOR, ships_panel, border_radius=12)
        pygame.draw.rect(app.screen, OUTLINE_COLOR, ships_panel, width=2, border_radius=12)

        ships_title = app.small_font.render("Your Ships", True, LABEL_COLOR)
        app.screen.blit(ships_title, (ships_panel.centerx - ships_title.get_width() // 2, 126))

        self._draw_grid(app, state)
        self._draw_ships(app, state)

        status_text = app.multiplayer_status_message or "Rotate ships with right click"
        status = app.hint_font.render(status_text, True, LABEL_COLOR)
        app.screen.blit(status, (WINDOW_WIDTH // 2 - status.get_width() // 2, 78))

        mouse_pos = pygame.mouse.get_pos()
        self.auto_place_button.draw(app.screen, app.dropdown_font, mouse_pos)
        self.next_button.draw(app.screen, app.button_font, mouse_pos)


@dataclass
class MultiplayerBattleScreen(LocalBattleScreen):
    def update(self, app: "BattleshipMenuApp") -> None:
        app.sync_multiplayer_battle()

    def handle_event(self, app: "BattleshipMenuApp", event: pygame.event.Event) -> None:
        if event.type != pygame.MOUSEBUTTONDOWN or event.button != 1:
            return

        if self.back_button.clicked(event.pos):
            app.stop_multiplayer_session()
            app.show_main_menu()
            return

        battle = app.battle_state
        if battle is None or battle.winner_index is not None or app.multiplayer_role is None:
            return

        local_player_index = player_index_from_role(app.multiplayer_role)
        if local_player_index is None:
            return

        if battle.current_player_index != local_player_index:
            battle.message = "Waiting for opponent turn"
            return

        target_player_index = 2 if local_player_index == 1 else 1
        target_origin_x = BATTLE_RIGHT_GRID_X if target_player_index == 2 else BATTLE_LEFT_GRID_X
        cell = self._pixel_to_grid_cell(event.pos, target_origin_x, BATTLE_GRID_Y)
        if cell is None:
            battle.message = "Click on the enemy field"
            return

        target = battle.players[target_player_index]
        if cell in target.hits or cell in target.misses:
            battle.message = "Cell already targeted"
            return

        if cell in self._adjacent_cells_around_sunk_ships(target):
            battle.message = "Cell blocked"
            return

        app.submit_multiplayer_shot(cell)

    def draw(self, app: "BattleshipMenuApp") -> None:
        battle = app.battle_state
        if battle is None:
            app.show_main_menu()
            return

        local_player_index = player_index_from_role(app.multiplayer_role)
        if local_player_index is None:
            app.show_main_menu()
            return

        opponent_player_index = 2 if local_player_index == 1 else 1

        app.screen.fill(BG_COLOR)

        if battle.winner_index is None:
            turn_text = "Your turn" if battle.current_player_index == local_player_index else "Waiting for opponent"
        else:
            turn_text = f"Winner: Player {battle.winner_index}"

        turn_surface = app.title_font.render(turn_text, True, TEXT_COLOR)
        message = app.hint_font.render(battle.message, True, LABEL_COLOR)
        app.screen.blit(turn_surface, (WINDOW_WIDTH // 2 - turn_surface.get_width() // 2, 24))
        app.screen.blit(message, (WINDOW_WIDTH // 2 - message.get_width() // 2, 84))

        own_origin_x = BATTLE_LEFT_GRID_X if local_player_index == 1 else BATTLE_RIGHT_GRID_X
        enemy_origin_x = BATTLE_RIGHT_GRID_X if local_player_index == 1 else BATTLE_LEFT_GRID_X
        own_label = app.hint_font.render("Your Field", True, LABEL_COLOR)
        enemy_label = app.hint_font.render("Enemy Field", True, LABEL_COLOR)
        app.screen.blit(own_label, (own_origin_x, 505))
        app.screen.blit(enemy_label, (enemy_origin_x, 505))

        self._draw_battle_grid(app, battle.players[local_player_index], own_origin_x, BATTLE_GRID_Y, reveal_ships=True)
        self._draw_battle_grid(app, battle.players[opponent_player_index], enemy_origin_x, BATTLE_GRID_Y, reveal_ships=False)

        mouse_pos = pygame.mouse.get_pos()
        self.back_button.draw(app.screen, app.hint_font, mouse_pos)


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
        self.multiplayer_server: MultiplayerServerHandle | None = None
        self.multiplayer_client: MultiplayerClient | None = None
        self.multiplayer_role: str | None = None
        self.multiplayer_setup_state: PlayerSetupState | None = None
        self.multiplayer_status_message: str = ""
        self._last_multiplayer_sync_at = 0.0

        self.main_menu_screen = MainMenuScreen()
        self.mode_selection_screen = ModeSelectionScreen()
        self.local_setup_screen = LocalSetupScreen()
        self.local_battle_screen = LocalBattleScreen()
        self.winner_menu_screen = WinnerMenuScreen()
        self.multiplayer_menu_screen = MultiplayerMenuScreen()
        self.multiplayer_join_screen = MultiplayerJoinScreen()
        self.multiplayer_host_wait_screen = MultiplayerHostWaitScreen()
        self.multiplayer_setup_screen = MultiplayerSetupScreen()
        self.multiplayer_battle_screen = MultiplayerBattleScreen()
        self.current_screen: Screen = self.main_menu_screen
        self.running = True

    def register_mode(self, mode_cls: type[BaseGameMode]) -> None:
        self.mode_registry.register(mode_cls)

    def stop_multiplayer_session(self) -> None:
        if self.multiplayer_client is not None:
            self.multiplayer_client.close()
            self.multiplayer_client = None
        if self.multiplayer_server is not None:
            self.multiplayer_server.close()
            self.multiplayer_server = None
        self.multiplayer_role = None
        self.multiplayer_setup_state = None
        self.multiplayer_status_message = ""
        self._last_multiplayer_sync_at = 0.0

    def show_multiplayer_menu(self) -> None:
        self.dropdown_open = False
        self.stop_multiplayer_session()
        self.current_screen = self.multiplayer_menu_screen

    def show_multiplayer_join(self) -> None:
        self.dropdown_open = False
        self.stop_multiplayer_session()
        self.current_screen = self.multiplayer_join_screen

    def start_multiplayer_host(self) -> None:
        self.stop_multiplayer_session()
        try:
            self.multiplayer_server = start_multiplayer_server()
            self.multiplayer_client = MultiplayerClient(self.multiplayer_server.base_url)
            self.multiplayer_role = "host"
            self.multiplayer_setup_state = empty_multiplayer_setup_state()
            self.battle_state = None
            self.multiplayer_status_message = "Server started. Waiting for client to join"
            self.current_screen = self.multiplayer_host_wait_screen
            snapshot: dict[str, Any] | None = None
            deadline = time.monotonic() + 1.0
            while time.monotonic() < deadline:
                try:
                    snapshot = self.multiplayer_client.state()
                    break
                except Exception:  # noqa: BLE001
                    time.sleep(0.05)
            if snapshot is not None:
                self._sync_multiplayer_snapshot(snapshot)
        except Exception as exc:  # noqa: BLE001
            self.multiplayer_status_message = f"Failed to start host session: {exc}"
            self.stop_multiplayer_session()
            self.current_screen = self.multiplayer_menu_screen

    def start_multiplayer_join(self, base_url: str) -> None:
        self.stop_multiplayer_session()
        try:
            self.multiplayer_client = MultiplayerClient(base_url)
            self.multiplayer_client.join()
            self.multiplayer_role = "client"
            self.multiplayer_setup_state = empty_multiplayer_setup_state()
            self.battle_state = None
            self.multiplayer_status_message = "Connected. Place your ships"
            self.current_screen = self.multiplayer_setup_screen
            self._sync_multiplayer_snapshot(self.multiplayer_client.state())
        except Exception as exc:  # noqa: BLE001
            self.multiplayer_status_message = f"Connection failed: {exc}"
            if self.multiplayer_client is not None:
                self.multiplayer_client.close()
                self.multiplayer_client = None
            self.multiplayer_role = None
            self.current_screen = self.multiplayer_join_screen

    def submit_multiplayer_setup(self) -> None:
        if self.multiplayer_client is None or self.multiplayer_role is None or self.multiplayer_setup_state is None:
            return

        ships = [set(ship.placed_cells or ()) for ship in self.multiplayer_setup_state.ships if ship.placed_cells is not None]
        try:
            snapshot = self.multiplayer_client.submit_setup(self.multiplayer_role, ships)
            self._sync_multiplayer_snapshot(snapshot)
        except Exception as exc:  # noqa: BLE001
            self.multiplayer_status_message = f"Failed to submit setup: {exc}"

    def submit_multiplayer_shot(self, cell: tuple[int, int]) -> None:
        if self.multiplayer_client is None or self.multiplayer_role is None:
            return

        try:
            snapshot = self.multiplayer_client.submit_shot(self.multiplayer_role, cell[0], cell[1])
            self._sync_multiplayer_snapshot(snapshot)
            if self.battle_state is not None and self.battle_state.winner_index is not None:
                self.show_winner_menu(self.battle_state.winner_index)
        except Exception as exc:  # noqa: BLE001
            if self.battle_state is not None:
                self.battle_state.message = f"Shot failed: {exc}"

    def sync_multiplayer_lobby(self) -> None:
        if not self._should_poll_multiplayer():
            return
        snapshot = self._fetch_multiplayer_snapshot()
        if snapshot is None:
            return
        self._sync_multiplayer_snapshot(snapshot)
        if snapshot.get("client_connected"):
            self.multiplayer_status_message = snapshot.get("message", self.multiplayer_status_message)
            if snapshot.get("phase") in {"setup", "battle", "finished"}:
                self.current_screen = self.multiplayer_setup_screen

    def sync_multiplayer_setup(self) -> None:
        if not self._should_poll_multiplayer():
            return
        snapshot = self._fetch_multiplayer_snapshot()
        if snapshot is None:
            return
        self._sync_multiplayer_snapshot(snapshot)
        if snapshot.get("phase") == "battle":
            self.current_screen = self.multiplayer_battle_screen

    def sync_multiplayer_battle(self) -> None:
        if not self._should_poll_multiplayer():
            return
        snapshot = self._fetch_multiplayer_snapshot()
        if snapshot is None:
            return
        self._sync_multiplayer_snapshot(snapshot)
        if self.battle_state is not None and self.battle_state.winner_index is not None:
            self.show_winner_menu(self.battle_state.winner_index)

    def _fetch_multiplayer_snapshot(self) -> dict[str, Any] | None:
        if self.multiplayer_client is None:
            return None
        try:
            return self.multiplayer_client.state()
        except Exception:  # noqa: BLE001
            return None

    def _should_poll_multiplayer(self) -> bool:
        now = time.monotonic()
        if now - self._last_multiplayer_sync_at < 0.25:
            return False
        self._last_multiplayer_sync_at = now
        return True

    def _sync_multiplayer_snapshot(self, snapshot: dict[str, Any]) -> None:
        self.multiplayer_status_message = snapshot.get("message", self.multiplayer_status_message)
        if snapshot.get("phase") in {"setup", "battle", "finished"}:
            self.battle_state = build_battle_state_from_snapshot(snapshot)
        if snapshot.get("phase") == "finished" and self.battle_state is not None and self.battle_state.winner_index is not None:
            self.current_screen = self.winner_menu_screen

    def show_main_menu(self) -> None:
        self.dropdown_open = False
        self.stop_multiplayer_session()
        self.battle_state = None
        self.current_screen = self.main_menu_screen

    def show_winner_menu(self, winner_index: int) -> None:
        self.dropdown_open = False
        if self.battle_state is not None:
            self.battle_state.winner_index = winner_index
        self.current_screen = self.winner_menu_screen

    def show_mode_selection(self) -> None:
        self.dropdown_open = False
        self.stop_multiplayer_session()
        self.current_screen = self.mode_selection_screen

    def start_local_setup(self) -> None:
        self.dropdown_open = False
        self.stop_multiplayer_session()
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

                self.current_screen.update(self)
                self.current_screen.draw(self)
                pygame.display.flip()
        except KeyboardInterrupt:
            self.running = False
        finally:
            self.stop_multiplayer_session()
            pygame.quit()
            sys.exit(0)


def main() -> None:
    app = BattleshipMenuApp()
    app.register_mode(LocalPlayMode)
    app.register_mode(MultiplayerPlayMode)
    app.run()


if __name__ == "__main__":
    main()
