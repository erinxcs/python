"""ERINX: Echoes of the Grove — a self-contained Python/Pygame action RPG."""
import json
import math
import random
from pathlib import Path

import pygame

WIDTH, HEIGHT = 960, 640
FPS = 60
TILE = 40
SAVE_FILE = Path(__file__).with_name('savegame.json')
WORLD = [
    '########################',
    '#......................#',
    '#....####..............#',
    '#....#..#..............#',
    '#....#..#.....#####....#',
    '#....####.....#...#....#',
    '#.............#...#....#',
    '#.............#####....#',
    '#......................#',
    '#...####...............#',
    '#...#..#...............#',
    '#...####...............#',
    '#......................#',
    '#.................###..#',
    '#......................#',
    '########################',
]
assert len(WORLD) == 16 and all(len(r) == 24 for r in WORLD)
BG = (13, 19, 30)
CREAM = (235, 235, 216)
GOLD = (246, 192, 93)
GREEN = (88, 192, 138)
RED = (230, 98, 105)
BLUE = (91, 161, 220)


def text(surface, font, message, color, x, y):
    surface.blit(font.render(str(message), True, color), (x, y))


def box(surface, rect, color, radius=8, border=None):
    pygame.draw.rect(surface, color, rect, border_radius=radius)
    if border:
        pygame.draw.rect(surface, border, rect, 2, border_radius=radius)


def center_of(tile_x, tile_y):
    return pygame.Vector2(tile_x * TILE + TILE / 2, tile_y * TILE + TILE / 2)


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('ERINX | Echoes of the Grove')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('consolas', 17, bold=True)
        self.small = pygame.font.SysFont('consolas', 14)
        self.medium = pygame.font.SysFont('consolas', 26, bold=True)
        self.big = pygame.font.SysFont('consolas', 52, bold=True)
        self.rng = random.Random(72)
        self.particles = [(self.rng.randrange(WIDTH), self.rng.randrange(HEIGHT), self.rng.randint(1, 2)) for _ in range(90)]
        self.state = 'title'
        self.reset()

    def reset(self):
        self.player = center_of(2, 2)
        self.direction = pygame.Vector2(0, 1)
        self.hp = 100
        self.max_hp = 100
        self.level = 1
        self.xp = 0
        self.gold = 0
        self.potions = 3
        self.crystals = 0
        self.kills = 0
        self.attack_cd = 0
        self.swing_time = 0
        self.invulnerable = 0
        self.message = 'Talk to Elder Rowan near the campfire. [E]'
        self.message_timer = 6
        self.quest_accepted = False
        self.quest_complete = False
        self.show_inventory = False
        self.show_help = False
        self.show_minimap = True
        self.pause = False
        self.time = 0.0
        self.enemies = []
        for x, y in [(11, 2), (17, 2), (20, 5), (10, 10), (17, 11), (21, 12), (10, 13), (14, 8)]:
            self.enemies.append({'pos': center_of(x, y), 'origin': center_of(x, y), 'hp': 36, 'max_hp': 36, 'alive': True, 'respawn': 0, 'hit': 0, 'phase': self.rng.random() * 7})

    def announce(self, msg, duration=3.0):
        self.message, self.message_timer = msg, duration

    def solid(self, pos, radius=11):
        for ox in (-radius, radius):
            for oy in (-radius, radius):
                x, y = int((pos.x + ox) // TILE), int((pos.y + oy) // TILE)
                if not (0 <= y < len(WORLD) and 0 <= x < len(WORLD[0])) or WORLD[y][x] == '#':
                    return True
        return False

    def move(self, pos, displacement, radius=11):
        next_pos = pygame.Vector2(pos)
        next_pos.x += displacement.x
        if not self.solid(next_pos, radius):
            pos.x = next_pos.x
        next_pos = pygame.Vector2(pos)
        next_pos.y += displacement.y
        if not self.solid(next_pos, radius):
            pos.y = next_pos.y

    def attack(self):
        if self.attack_cd > 0 or self.hp <= 0:
            return
        self.attack_cd, self.swing_time = 0.37, 0.16
        strike = self.player + self.direction * 29
        did_hit = False
        for enemy in self.enemies:
            if not enemy['alive']:
                continue
            if enemy['pos'].distance_to(strike) < 43:
                damage = 18 + 6 * (self.level - 1)
                enemy['hp'] -= damage
                enemy['hit'] = .14
                did_hit = True
                if enemy['hp'] <= 0:
                    enemy['alive'] = False
                    enemy['respawn'] = 14
                    self.gold += self.rng.randint(5, 12)
                    self.xp += 18
                    self.kills += 1
                    if self.rng.random() < .55:
                        self.crystals += 1
                        self.announce('Crystal shard collected!')
                    if self.xp >= self.level * 45:
                        self.xp -= self.level * 45
                        self.level += 1
                        self.max_hp += 15
                        self.hp = self.max_hp
                        self.announce('LEVEL UP! Health restored.')
        if did_hit and not self.message_timer:
            self.announce('A clean hit!', .55)

    def interact(self):
        if self.player.distance_to(center_of(3, 3)) < 78:
            if not self.quest_accepted:
                self.quest_accepted = True
                self.announce('ROWAN: Bring me 3 crystal shards from the slimes!', 5)
            elif not self.quest_complete and self.crystals >= 3:
                self.crystals -= 3
                self.quest_complete = True
                self.gold += 100
                self.potions += 2
                self.announce('QUEST COMPLETE! +100 gold, +2 potions. The Grove is saved!', 7)
            elif self.quest_complete:
                self.announce('ROWAN: You are the hero of the Grove. Thank you!', 4)
            else:
                self.announce(f'ROWAN: You have {self.crystals}/3 shards. Keep going!', 4)
        elif self.player.distance_to(center_of(6, 12)) < 75:
            if self.gold >= 25:
                self.gold -= 25
                self.potions += 1
                self.announce('Merchant: Purchased 1 health potion for 25 gold.')
            else:
                self.announce('Merchant: A potion costs 25 gold. Come back soon!')
        else:
            self.announce('Nothing to interact with nearby.', 1.5)

    def save(self):
        data = {'pos': [self.player.x, self.player.y], 'hp': self.hp, 'max_hp': self.max_hp,
                'level': self.level, 'xp': self.xp, 'gold': self.gold, 'potions': self.potions,
                'crystals': self.crystals, 'kills': self.kills, 'quest_accepted': self.quest_accepted,
                'quest_complete': self.quest_complete}
        try:
            SAVE_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
            self.announce('Game saved successfully [F5]')
        except OSError as exc:
            self.announce(f'Could not save: {exc}', 4)

    def load(self):
        try:
            data = json.loads(SAVE_FILE.read_text(encoding='utf-8'))
            required = ['pos', 'hp', 'max_hp', 'level', 'xp', 'gold', 'potions', 'crystals', 'kills', 'quest_accepted', 'quest_complete']
            if any(k not in data for k in required):
                raise ValueError('Save missing fields')
            pos = pygame.Vector2(data['pos'])
            if self.solid(pos):
                raise ValueError('Invalid saved position')
            self.reset()
            self.player = pos
            for key in required[1:]:
                setattr(self, key, data[key])
            self.state = 'game'
            self.announce('Adventure loaded! [F9]')
        except (OSError, ValueError, TypeError, KeyError) as exc:
            self.announce(f'Cannot load saved game: {exc}', 5)
            if self.state == 'title':
                self.state = 'game'

    def input(self, event):
        if event.type == pygame.QUIT:
            return False
        if event.type != pygame.KEYDOWN:
            return True
        key = event.key
        if self.state == 'title':
            if key in (pygame.K_RETURN, pygame.K_SPACE):
                self.reset()
                self.state = 'game'
            elif key == pygame.K_l:
                self.load()
            elif key == pygame.K_ESCAPE:
                return False
            return True
        if self.state == 'dead':
            if key == pygame.K_r:
                self.reset()
                self.state = 'game'
            if key == pygame.K_ESCAPE:
                self.state = 'title'
            return True
        if key == pygame.K_ESCAPE:
            self.pause = not self.pause
        elif key == pygame.K_F5:
            self.save()
        elif key == pygame.K_F9:
            self.load()
        elif key == pygame.K_h:
            self.show_help = not self.show_help
        elif key == pygame.K_i or key == pygame.K_TAB:
            self.show_inventory = not self.show_inventory
        elif key == pygame.K_m:
            self.show_minimap = not self.show_minimap
        elif not self.pause:
            if key in (pygame.K_SPACE, pygame.K_j):
                self.attack()
            elif key == pygame.K_e:
                self.interact()
            elif key == pygame.K_q:
                if self.potions > 0 and self.hp < self.max_hp:
                    self.potions -= 1
                    self.hp = min(self.max_hp, self.hp + 45)
                    self.announce('Health restored: +45 HP', 1.5)
                else:
                    self.announce('Cannot use a potion right now.', 1.5)
        return True

    def update(self, dt):
        self.time += dt
        self.message_timer = max(0, self.message_timer - dt)
        if self.state != 'game' or self.pause or self.show_help or self.show_inventory:
            return
        self.attack_cd = max(0, self.attack_cd - dt)
        self.swing_time = max(0, self.swing_time - dt)
        self.invulnerable = max(0, self.invulnerable - dt)
        keys = pygame.key.get_pressed()
        vel = pygame.Vector2(int(keys[pygame.K_d] or keys[pygame.K_RIGHT]) - int(keys[pygame.K_a] or keys[pygame.K_LEFT]),
                             int(keys[pygame.K_s] or keys[pygame.K_DOWN]) - int(keys[pygame.K_w] or keys[pygame.K_UP]))
        if vel.length_squared():
            vel = vel.normalize()
            self.direction = vel
            self.move(self.player, vel * 175 * dt)
        for enemy in self.enemies:
            if not enemy['alive']:
                enemy['respawn'] -= dt
                if enemy['respawn'] <= 0:
                    enemy['hp'] = enemy['max_hp']
                    enemy['pos'] = pygame.Vector2(enemy['origin'])
                    enemy['alive'] = True
                continue
            enemy['hit'] = max(0, enemy['hit'] - dt)
            dist = enemy['pos'].distance_to(self.player)
            if dist < 230 and dist > 1 and self.player.distance_to(center_of(2, 2)) > 95:
                vector = (self.player - enemy['pos']).normalize()
                self.move(enemy['pos'], vector * 61 * dt, 12)
            else:
                drift = pygame.Vector2(math.cos(self.time * .8 + enemy['phase']), math.sin(self.time * .7 + enemy['phase']))
                if enemy['pos'].distance_to(enemy['origin']) < 55:
                    self.move(enemy['pos'], drift * 13 * dt, 12)
            if dist < 29 and self.invulnerable <= 0:
                self.hp = max(0, self.hp - 13)
                self.invulnerable = .9
                self.announce('-13 HP! Press Q to use a potion.', 1.4)
                if self.hp == 0:
                    self.state = 'dead'

    def terrain(self):
        self.screen.fill(BG)
        for y, row in enumerate(WORLD):
            for x, tile in enumerate(row):
                rect = pygame.Rect(x * TILE, y * TILE, TILE, TILE)
                if tile == '#':
                    pygame.draw.rect(self.screen, (34, 65, 67), rect)
                    pygame.draw.rect(self.screen, (55, 103, 93), (rect.x + 3, rect.y + 2, 34, 7), border_radius=3)
                    pygame.draw.rect(self.screen, (25, 49, 56), (rect.x + 4, rect.y + 14, 32, 24), border_radius=3)
                else:
                    base = (25, 51, 51) if (x * 7 + y * 11) % 5 else (29, 58, 55)
                    pygame.draw.rect(self.screen, base, rect)
                    if (x * 17 + y * 7) % 9 == 0:
                        pygame.draw.line(self.screen, (47, 91, 76), (rect.x + 11, rect.y + 27), (rect.x + 16, rect.y + 17), 2)
        self.npc(center_of(3, 3), GOLD, 'ROWAN')
        self.npc(center_of(6, 12), BLUE, 'SHOP')
        # Flickering campfire.
        fx, fy = center_of(2, 4)
        pygame.draw.circle(self.screen, (94, 64, 46), (int(fx), int(fy)), 18)
        pygame.draw.circle(self.screen, (251, 146, 62), (int(fx), int(fy - 3)), int(8 + 2 * math.sin(self.time * 9)))
        pygame.draw.circle(self.screen, (255, 214, 108), (int(fx), int(fy - 5)), 4)

    def npc(self, pos, color, label):
        pygame.draw.ellipse(self.screen, (14, 31, 31), (pos.x - 13, pos.y + 11, 26, 9))
        pygame.draw.rect(self.screen, color, (pos.x - 11, pos.y - 7, 22, 25), border_radius=7)
        pygame.draw.circle(self.screen, (241, 209, 174), (int(pos.x), int(pos.y - 12)), 10)
        text(self.screen, self.small, label, CREAM, int(pos.x - 18), int(pos.y - 35))

    def actors(self):
        for enemy in self.enemies:
            if not enemy['alive']:
                continue
            p = enemy['pos']
            bounce = math.sin(self.time * 5 + enemy['phase']) * 3
            pygame.draw.ellipse(self.screen, (16, 37, 33), (p.x - 15, p.y + 9, 30, 9))
            color = CREAM if enemy['hit'] > 0 else (123, 207, 123)
            pygame.draw.ellipse(self.screen, color, (p.x - 15, p.y - 12 + bounce, 30, 28))
            pygame.draw.circle(self.screen, (20, 43, 43), (int(p.x - 5), int(p.y + bounce)), 3)
            pygame.draw.circle(self.screen, (20, 43, 43), (int(p.x + 6), int(p.y + bounce)), 3)
            pygame.draw.rect(self.screen, RED, (p.x - 15, p.y - 19 + bounce, 30, 4), border_radius=2)
            pygame.draw.rect(self.screen, GREEN, (p.x - 15, p.y - 19 + bounce, 30 * max(0, enemy['hp']) / enemy['max_hp'], 4), border_radius=2)
        p = self.player
        if self.invulnerable <= 0 or int(self.time * 15) % 2 == 0:
            pygame.draw.ellipse(self.screen, (11, 29, 34), (p.x - 13, p.y + 12, 27, 8))
            pygame.draw.rect(self.screen, (69, 129, 194), (p.x - 11, p.y - 2, 22, 26), border_radius=5)
            pygame.draw.circle(self.screen, (234, 193, 157), (int(p.x), int(p.y - 10)), 11)
            pygame.draw.arc(self.screen, (49, 48, 64), (p.x - 12, p.y - 23, 24, 20), 0, math.pi, 4)
            if self.swing_time > 0:
                front = p + self.direction * 30
                pygame.draw.circle(self.screen, GOLD, (int(front.x), int(front.y)), 26, 5)
                pygame.draw.line(self.screen, CREAM, p + self.direction * 8, p + self.direction * 43, 5)

    def hud(self):
        box(self.screen, pygame.Rect(12, 10, 306, 96), (12, 23, 35), border=(58, 87, 98))
        text(self.screen, self.font, f'LVL {self.level}   HP {self.hp}/{self.max_hp}', CREAM, 26, 19)
        pygame.draw.rect(self.screen, (71, 55, 65), (26, 48, 270, 14), border_radius=6)
        pygame.draw.rect(self.screen, RED, (26, 48, 270 * self.hp / self.max_hp, 14), border_radius=6)
        pygame.draw.rect(self.screen, (44, 55, 76), (26, 71, 270, 8), border_radius=4)
        pygame.draw.rect(self.screen, BLUE, (26, 71, 270 * self.xp / (self.level * 45), 8), border_radius=4)
        text(self.screen, self.small, f'Gold: {self.gold}    Potions: {self.potions}    Shards: {self.crystals}', GOLD, 26, 85)
        box(self.screen, pygame.Rect(584, 10, 360, 79), (12, 23, 35), border=(58, 87, 98))
        text(self.screen, self.font, 'MAIN QUEST  /  THE LOST SHARDS', GOLD, 601, 21)
        quest = 'Completed! The Grove is safe.' if self.quest_complete else ('Collect 3 shards; return to Rowan.' if self.quest_accepted else 'Speak to Elder Rowan [E].')
        text(self.screen, self.small, quest, CREAM, 601, 49)
        box(self.screen, pygame.Rect(10, 593, 940, 37), (12, 23, 35), border=(58, 87, 98))
        text(self.screen, self.small, 'WASD Move  |  SPACE Attack  |  E Talk  |  Q Potion  |  I Inventory  |  H Help  |  ESC Pause', CREAM, 22, 604)
        if self.message_timer > 0:
            surface = self.font.render(self.message, True, CREAM)
            rect = pygame.Rect(WIDTH // 2 - surface.get_width() // 2 - 17, 535, surface.get_width() + 34, 40)
            box(self.screen, rect, (13, 28, 38), border=(75, 125, 118))
            self.screen.blit(surface, (rect.x + 17, rect.y + 11))
        if self.show_minimap:
            self.minimap()

    def minimap(self):
        offset_x, offset_y, scale = 802, 110, 5
        box(self.screen, pygame.Rect(offset_x - 8, offset_y - 8, 138, 100), (11, 22, 34), border=(60, 94, 104))
        for y, row in enumerate(WORLD):
            for x, tile in enumerate(row):
                col = (58, 91, 89) if tile == '#' else (33, 61, 60)
                pygame.draw.rect(self.screen, col, (offset_x + x * scale, offset_y + y * scale, scale - 1, scale - 1))
        pygame.draw.circle(self.screen, GOLD, (offset_x + int(self.player.x / TILE * scale), offset_y + int(self.player.y / TILE * scale)), 4)

    def modal(self, heading, lines, footer='Press ESC to close'):
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((4, 10, 19, 200))
        self.screen.blit(overlay, (0, 0))
        rect = pygame.Rect(190, 152, 580, 328)
        box(self.screen, rect, (18, 35, 49), border=(91, 157, 151))
        text(self.screen, self.medium, heading, GOLD, 223, 182)
        for index, line in enumerate(lines):
            text(self.screen, self.font, line, CREAM, 223, 241 + index * 33)
        text(self.screen, self.small, footer, BLUE, 223, 442)

    def title(self):
        self.screen.fill(BG)
        for x, y, r in self.particles:
            pygame.draw.circle(self.screen, (45, 81, 97), (x, int((y + self.time * r * 7) % HEIGHT)), r)
        pygame.draw.circle(self.screen, (31, 74, 80), (480, 265), 155)
        pygame.draw.circle(self.screen, (55, 113, 106), (480, 265), 126, 3)
        text(self.screen, self.small, 'A PIXEL-STYLE PYTHON ADVENTURE', GREEN, 341, 149)
        text(self.screen, self.big, 'ECHOES OF', CREAM, 329, 207)
        text(self.screen, self.big, 'THE GROVE', GOLD, 329, 264)
        text(self.screen, self.font, 'Slimes roam the forest. Its fate rests in your hands.', CREAM, 246, 379)
        text(self.screen, self.medium, 'ENTER  -  NEW ADVENTURE', GREEN, 301, 437)
        text(self.screen, self.font, 'L  -  LOAD SAVED GAME', CREAM, 372, 480)
        text(self.screen, self.small, 'ERINX RPG  |  MADE WITH PYTHON + PYGAME', BLUE, 316, 583)

    def render(self):
        if self.state == 'title':
            self.title()
            return
        self.terrain()
        self.actors()
        self.hud()
        if self.show_inventory and self.state == 'game':
            self.modal('INVENTORY & STATS', [f'Health potions: {self.potions}  (Q to use)',
                f'Crystal shards: {self.crystals} / 3 required', f'Gold coins: {self.gold}',
                f'Slime defeats: {self.kills}    Level: {self.level}', 'Hint: Visit the shop in the southwest.'], 'Press I or TAB to close')
        elif self.show_help and self.state == 'game':
            self.modal('CONTROLS & TIPS', ['WASD / Arrows  -  Move', 'SPACE / J  -  Sword attack',
                'E  -  Interact with NPCs', 'Q  -  Drink health potion', 'F5  -  Save   |   F9  -  Load',
                'I / TAB  -  Inventory   |   M  -  Mini-map'], 'Press H to close')
        elif self.pause and self.state == 'game':
            self.modal('PAUSED', ['Your journey is on hold.', 'F5 saves your current adventure.',
                'F9 loads your last save.'], 'Press ESC to resume')
        if self.state == 'dead':
            self.modal('YOU HAVE FALLEN', [f'Slimes defeated: {self.kills}', f'Gold collected: {self.gold}',
                'The Grove needs you once more.'], 'Press R to restart, ESC for title')

    def run(self):
        running = True
        while running:
            dt = min(self.clock.tick(FPS) / 1000.0, .05)
            for event in pygame.event.get():
                if not self.input(event):
                    running = False
            self.update(dt)
            self.render()
            pygame.display.flip()
        pygame.quit()


if __name__ == '__main__':
    Game().run()
