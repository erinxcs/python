"""ERINX: Little Harvest — a self-contained Pygame farming simulator."""
from __future__ import annotations
import json
import math
import random
from pathlib import Path
import pygame

WIDTH, HEIGHT = 1100, 720
FPS = 60
SAVE_FILE = Path(__file__).with_name('savegame.json')
CROPS = {
    'Carrot': {'seed': 4, 'sell': 12, 'days': 2, 'color': (245, 144, 55)},
    'Tomato': {'seed': 8, 'sell': 23, 'days': 3, 'color': (235, 76, 82)},
    'Corn': {'seed': 13, 'sell': 38, 'days': 4, 'color': (247, 205, 67)},
    'Pumpkin': {'seed': 24, 'sell': 75, 'days': 5, 'color': (240, 125, 55)},
}
SEED_NAMES = list(CROPS)
WHITE = (246, 247, 234)
DARK = (27, 44, 48)
MUTED = (135, 157, 148)
GREEN = (89, 178, 106)
GOLD = (250, 207, 106)


def txt(surface, font, message, pos, color=WHITE, center=False):
    img = font.render(str(message), True, color)
    rect = img.get_rect(center=pos) if center else img.get_rect(topleft=pos)
    surface.blit(img, rect)


def rr(surface, color, rect, radius=12, border=0):
    pygame.draw.rect(surface, color, rect, border, border_radius=radius)


class Game:
    def __init__(self):
        pygame.init()
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        pygame.display.set_caption('ERINX | LITTLE HARVEST')
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('segoeui', 19)
        self.small = pygame.font.SysFont('segoeui', 15)
        self.big = pygame.font.SysFont('segoeui', 40, bold=True)
        self.mid = pygame.font.SysFont('segoeui', 25, bold=True)
        self.tiny = pygame.font.SysFont('segoeui', 13)
        self.rng = random.Random()
        self.reset()
        self.particles = []
        self.toast = 'Welcome to Little Harvest! Press H for help.'
        self.toast_timer = 330
        self.load(silent=True)

    def reset(self):
        self.day = 1
        self.money = 120
        self.energy = 12
        self.max_energy = 12
        self.seeds = {'Carrot': 5, 'Tomato': 2, 'Corn': 0, 'Pumpkin': 0}
        self.harvest = {k: 0 for k in CROPS}
        self.plots = [{'crop': None, 'age': 0, 'watered': False} for _ in range(24)]
        self.selected_crop = 'Carrot'
        self.tool = 'plant'
        self.active_plot = None
        self.shop = False
        self.help = False
        self.pause = False
        self.anim = 0
        self.watering_upgrade = False
        self.energy_upgrade = False
        self.earned = 0
        self.harvest_count = 0
        self.weather = 'Sunny'

    def notify(self, text):
        self.toast = text
        self.toast_timer = 210

    def save(self):
        data = {key: getattr(self, key) for key in ['day', 'money', 'energy', 'max_energy', 'seeds', 'harvest', 'plots', 'selected_crop', 'tool', 'watering_upgrade', 'energy_upgrade', 'earned', 'harvest_count', 'weather']}
        try:
            SAVE_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')
            self.notify('Farm saved!  (F5)')
        except OSError:
            self.notify('Could not save game.')

    def load(self, silent=False):
        if not SAVE_FILE.exists():
            if not silent: self.notify('No save found yet. Press F5 to save.')
            return
        try:
            data = json.loads(SAVE_FILE.read_text(encoding='utf-8'))
            if not isinstance(data['plots'], list) or len(data['plots']) != 24: raise ValueError('bad plots')
            for p in data['plots']:
                if p['crop'] not in (None, *CROPS.keys()): raise ValueError('bad crop')
            self.day = max(1, int(data['day']))
            self.money = max(0, int(data['money']))
            self.max_energy = max(1, min(30, int(data.get('max_energy', 12))))
            self.energy = max(0, min(self.max_energy, int(data.get('energy', self.max_energy))))
            self.seeds = {k: max(0, int(data['seeds'].get(k, 0))) for k in CROPS}
            self.harvest = {k: max(0, int(data['harvest'].get(k, 0))) for k in CROPS}
            self.plots = [{'crop': p['crop'], 'age': max(0, int(p['age'])), 'watered': bool(p['watered'])} for p in data['plots']]
            self.selected_crop = data.get('selected_crop', 'Carrot') if data.get('selected_crop') in CROPS else 'Carrot'
            self.tool = data.get('tool', 'plant') if data.get('tool') in ('plant', 'water', 'harvest', 'clear') else 'plant'
            self.watering_upgrade = bool(data.get('watering_upgrade', False))
            self.energy_upgrade = bool(data.get('energy_upgrade', False))
            self.earned = max(0, int(data.get('earned', 0)))
            self.harvest_count = max(0, int(data.get('harvest_count', 0)))
            self.weather = data.get('weather', 'Sunny')
            if not silent: self.notify('Farm loaded!  (F9)')
        except (OSError, ValueError, KeyError, TypeError):
            self.notify('Save file is damaged. Starting fresh.')

    def plot_rect(self, index):
        col, row = index % 6, index // 6
        return pygame.Rect(85 + col * 125, 213 + row * 105, 100, 82)

    def action(self, index):
        p = self.plots[index]
        if self.energy <= 0:
            self.notify('Out of energy! Click SLEEP to start a new day.')
            return
        if self.tool == 'plant':
            if p['crop']:
                self.notify('This plot is occupied!')
            elif self.seeds[self.selected_crop] <= 0:
                self.notify('No seeds! Open the market to buy more.')
            else:
                self.seeds[self.selected_crop] -= 1
                p.update(crop=self.selected_crop, age=0, watered=False)
                self.energy -= 1
                self.spark(index, GREEN)
                self.notify(f'Planted {self.selected_crop}. Water it to grow!')
        elif self.tool == 'water':
            targets = [index]
            if self.watering_upgrade:
                c, r = index % 6, index // 6
                targets += [n for n in (index - 1, index + 1) if 0 <= n < 24 and n // 6 == r]
            watered = 0
            for idx in targets:
                pp = self.plots[idx]
                if pp['crop'] and not pp['watered'] and pp['age'] < CROPS[pp['crop']]['days']:
                    pp['watered'] = True
                    watered += 1
                    self.spark(idx, (100, 197, 235))
            if watered:
                self.energy -= 1
                self.notify(f'Watered {watered} crop(s). Sleep for growth!')
            else: self.notify('No thirsty crops here.')
        elif self.tool == 'harvest':
            if not p['crop']:
                self.notify('Nothing to harvest!')
            elif p['age'] < CROPS[p['crop']]['days']:
                self.notify('Not ripe yet. Keep watering and sleeping.')
            else:
                crop = p['crop']
                qty = 2 if self.weather == 'Rainy' else 1
                self.harvest[crop] += qty
                self.harvest_count += qty
                self.energy -= 1
                self.spark(index, GOLD)
                p.update(crop=None, age=0, watered=False)
                self.notify(f'Harvested {qty} {crop}! Sell at the market.')
        elif self.tool == 'clear':
            if not p['crop']: self.notify('This plot is already clear.')
            else:
                p.update(crop=None, age=0, watered=False)
                self.energy -= 1
                self.notify('Plot cleared.')

    def sleep(self):
        self.day += 1
        self.weather = self.rng.choices(['Sunny', 'Cloudy', 'Rainy'], weights=[55, 25, 20])[0]
        grew = 0
        for p in self.plots:
            if p['crop']:
                if p['watered'] or self.weather == 'Rainy':
                    if p['age'] < CROPS[p['crop']]['days']:
                        p['age'] += 1
                        grew += 1
                p['watered'] = self.weather == 'Rainy'
        self.energy = self.max_energy
        self.notify(f'Day {self.day}: {self.weather}! {grew} crops grew overnight.')
        if self.day % 3 == 0: self.save()

    def buy_seed(self, crop):
        cost = CROPS[crop]['seed']
        if self.money < cost: self.notify('Not enough coins!')
        else:
            self.money -= cost
            self.seeds[crop] += 1
            self.notify(f'Bought 1 {crop} seed (-{cost} coins).')

    def sell(self, crop):
        if self.harvest[crop] < 1: self.notify('No harvested crops to sell.')
        else:
            count = self.harvest[crop]
            amount = count * CROPS[crop]['sell']
            self.harvest[crop] = 0
            self.money += amount
            self.earned += amount
            self.notify(f'Sold {count} {crop} for {amount} coins!')

    def upgrade(self, kind):
        if kind == 'watering':
            if self.watering_upgrade: self.notify('Sprinkler is already unlocked.')
            elif self.money < 180: self.notify('Need 180 coins for the sprinkler.')
            else:
                self.money -= 180
                self.watering_upgrade = True
                self.notify('Sprinkler unlocked! Water 3 plots at once.')
        else:
            if self.energy_upgrade: self.notify('Energy upgrade already purchased.')
            elif self.money < 140: self.notify('Need 140 coins for the energy upgrade.')
            else:
                self.money -= 140
                self.energy_upgrade = True
                self.max_energy += 6
                self.energy += 6
                self.notify('Energy upgraded! +6 max energy.')

    def spark(self, index, color):
        rect = self.plot_rect(index)
        for _ in range(12):
            angle = self.rng.uniform(0, math.tau)
            speed = self.rng.uniform(1.0, 3.6)
            self.particles.append([float(rect.centerx), float(rect.centery), math.cos(angle)*speed, math.sin(angle)*speed-1.5, self.rng.randint(22, 42), color])

    def button(self, rect, label, action, mouse, enabled=True, primary=False, font=None):
        hover = enabled and rect.collidepoint(mouse)
        col = (93, 181, 121) if primary else (54, 79, 76)
        if hover: col = (119, 205, 146) if primary else (71, 108, 97)
        if not enabled: col = (40, 56, 55)
        rr(self.screen, col, rect, 10)
        txt(self.screen, font or self.font, label, rect.center, WHITE if enabled else MUTED, center=True)
        return (rect, action) if enabled else None

    def draw_crop(self, crop, rect, age, ready, t):
        data = CROPS[crop]
        growth = min(1, age / data['days'])
        cx = rect.centerx
        cy = rect.bottom - 14
        stalk = int(13 + growth * 39)
        pygame.draw.line(self.screen, (74, 145, 76), (cx, cy), (cx, cy-stalk), 5)
        leaf_y = cy - int(stalk*.58)
        pygame.draw.ellipse(self.screen, (81, 181, 95), (cx-21, leaf_y-6, 22, 12))
        pygame.draw.ellipse(self.screen, (116, 199, 100), (cx+1, leaf_y-10, 23, 13))
        if growth > .25:
            r = int(5 + growth*13)
            wobble = int(math.sin(t*.07 + cx)*2) if ready else 0
            fruit_y = cy-stalk+wobble
            if crop == 'Corn':
                rr(self.screen, data['color'], (cx-r//2, fruit_y, r, r*2), 6)
            elif crop == 'Carrot':
                pygame.draw.polygon(self.screen, data['color'], [(cx-r, fruit_y), (cx+r, fruit_y), (cx, fruit_y+int(1.5*r))])
            elif crop == 'Pumpkin':
                pygame.draw.ellipse(self.screen, data['color'], (cx-r-3, fruit_y-3, (r+3)*2, r*2))
                pygame.draw.line(self.screen, (56, 119, 63), (cx, fruit_y), (cx+2, fruit_y-8), 4)
            else:
                pygame.draw.circle(self.screen, data['color'], (cx, fruit_y+r//3), r)
                pygame.draw.circle(self.screen, (248, 151, 149), (cx-4, fruit_y-1), 3)
        if ready:
            txt(self.screen, self.small, 'READY!', (rect.centerx, rect.top+5), GOLD, center=True)
        else:
            txt(self.screen, self.tiny, f'{age}/{data["days"]} days', (rect.centerx, rect.top+5), (227, 220, 186), center=True)

    def draw(self):
        s = self.screen
        s.fill((21, 41, 45))
        mouse = pygame.mouse.get_pos()
        self.clicks = []
        rr(s, (28, 51, 55), (24, 20, 1052, 100), 19)
        txt(s, self.mid, 'LITTLE HARVEST', (44, 33), GOLD)
        txt(s, self.small, 'A cozy farming adventure by ERINX', (46, 71), MUTED)
        for i, (head, value) in enumerate([('DAY', self.day), ('WEATHER', self.weather), ('COINS', f'{self.money} g'), ('ENERGY', f'{self.energy}/{self.max_energy}')]):
            x = 520 + i*137
            txt(s, self.tiny, head, (x, 42), MUTED)
            txt(s, self.font, value, (x, 63), GOLD if i == 2 else WHITE)
        rr(s, (32, 67, 61), (29, 141, 802, 535), 16)
        # decorative field grooves
        for x in range(50, 830, 31):
            pygame.draw.line(s, (38, 75, 64), (x, 166), (x+18, 169), 2)
        txt(s, self.mid, 'YOUR FARM', (51, 155))
        txt(s, self.small, f'{sum(1 for p in self.plots if p["crop"])} / 24 planted plots', (236, 163), MUTED)
        for index, p in enumerate(self.plots):
            rect = self.plot_rect(index)
            hovered = rect.collidepoint(mouse) and not self.shop and not self.help
            rr(s, (25, 45, 40), rect.move(2, 5), 13)
            rr(s, (106, 76, 55) if not hovered else (139, 103, 67), rect, 13)
            inner = rect.inflate(-10, -10)
            rr(s, (125, 89, 62), inner, 9)
            for j in range(3):
                pygame.draw.line(s, (100, 69, 48), (inner.left+10, inner.top+17+j*16), (inner.right-10, inner.top+17+j*16), 2)
            if p['crop']:
                ready = p['age'] >= CROPS[p['crop']]['days']
                self.draw_crop(p['crop'], rect, p['age'], ready, self.anim)
                if p['watered']:
                    pygame.draw.circle(s, (97, 195, 241), (rect.right-11, rect.bottom-12), 5)
            else:
                txt(s, self.mid, '+', rect.center, (163, 124, 90), center=True)
        # sidebar
        rr(s, (29, 53, 57), (846, 141, 230, 535), 16)
        txt(s, self.mid, 'TOOLS', (866, 158))
        tool_names = [('plant', '1   PLANT'), ('water', '2   WATER'), ('harvest', '3   HARVEST'), ('clear', '4   CLEAR')]
        for i, (key, label) in enumerate(tool_names):
            rect = pygame.Rect(861, 200+i*43, 200, 36)
            pair = self.button(rect, label, ('tool', key), mouse, primary=self.tool == key, font=self.small)
            if pair: self.clicks.append(pair)
        txt(s, self.small, 'SEED TYPE', (866, 390), MUTED)
        for i, crop in enumerate(SEED_NAMES):
            rect = pygame.Rect(862+(i%2)*100, 419+(i//2)*42, 96, 34)
            label = f'{crop[:6]} {self.seeds[crop]}'
            pair = self.button(rect, label, ('crop', crop), mouse, primary=self.selected_crop==crop, font=self.tiny)
            if pair: self.clicks.append(pair)
        for rect, label, event, color in [
            (pygame.Rect(862, 518, 199, 41), 'MARKET  [B]', 'shop', True),
            (pygame.Rect(862, 568, 199, 41), 'SLEEP / NEXT DAY  [N]', 'sleep', False),
            (pygame.Rect(862, 618, 96, 35), 'SAVE F5', 'save', False),
            (pygame.Rect(965, 618, 96, 35), 'HELP H', 'help', False),
        ]:
            pair = self.button(rect, label, event, mouse, primary=color, font=self.small)
            if pair: self.clicks.append(pair)
        if self.toast_timer > 0:
            rr(s, (48, 82, 77), (32, 682, 1035, 30), 9)
            txt(s, self.small, self.toast, (45, 687), WHITE)
        else:
            txt(s, self.tiny, 'CLICK PLOTS  •  [1-4] TOOLS  •  [B] MARKET  •  [N] NEXT DAY  •  [H] HELP', (50, 688), MUTED)
        for particle in self.particles:
            pygame.draw.circle(s, particle[5], (int(particle[0]), int(particle[1])), 3)
        if self.shop: self.draw_shop(mouse)
        if self.help: self.draw_help(mouse)
        if self.pause: self.draw_pause(mouse)
        pygame.display.flip()

    def modal_background(self):
        shade = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        shade.fill((5, 16, 22, 210))
        self.screen.blit(shade, (0, 0))

    def draw_shop(self, mouse):
        self.modal_background()
        self.clicks = []
        rr(self.screen, (37, 65, 66), (205, 91, 690, 540), 20)
        txt(self.screen, self.big, 'FARMER\'S MARKET', (241, 121), GOLD)
        txt(self.screen, self.small, f'Wallet: {self.money} coins  •  Click BUY or SELL to trade', (245, 173), MUTED)
        txt(self.screen, self.small, 'CROP', (240, 222), MUTED)
        txt(self.screen, self.small, 'SEEDS', (409, 222), MUTED)
        txt(self.screen, self.small, 'HARVEST', (543, 222), MUTED)
        for i, crop in enumerate(SEED_NAMES):
            y = 251 + i*57
            if i % 2 == 0: rr(self.screen, (44, 78, 76), (230, y-5, 640, 48), 10)
            pygame.draw.circle(self.screen, CROPS[crop]['color'], (248, y+15), 9)
            txt(self.screen, self.font, crop, (267, y+3))
            txt(self.screen, self.small, str(self.seeds[crop]), (433, y+6))
            txt(self.screen, self.small, str(self.harvest[crop]), (569, y+6))
            for rect, label, action, enabled in [
                (pygame.Rect(640, y, 106, 33), f'BUY {CROPS[crop]["seed"]}g', ('buy', crop), self.money >= CROPS[crop]['seed']),
                (pygame.Rect(752, y, 108, 33), f'SELL {CROPS[crop]["sell"]}g', ('sell', crop), self.harvest[crop] > 0),
            ]:
                pair = self.button(rect, label, action, mouse, enabled=enabled, font=self.tiny)
                if pair: self.clicks.append(pair)
        txt(self.screen, self.small, 'UPGRADES', (240, 491), GOLD)
        for rect, label, action, enabled in [
            (pygame.Rect(236, 519, 290, 42), 'SPRINKLER (3 plots)  - 180g' if not self.watering_upgrade else 'SPRINKLER  -  OWNED', ('upgrade', 'watering'), not self.watering_upgrade),
            (pygame.Rect(536, 519, 327, 42), '+6 MAX ENERGY  - 140g' if not self.energy_upgrade else 'ENERGY UPGRADE  -  OWNED', ('upgrade', 'energy'), not self.energy_upgrade),
        ]:
            pair = self.button(rect, label, action, mouse, enabled=enabled, font=self.small)
            if pair: self.clicks.append(pair)
        pair = self.button(pygame.Rect(713, 582, 148, 35), 'CLOSE  [B/ESC]', 'close', mouse, primary=True, font=self.small)
        if pair: self.clicks.append(pair)

    def draw_help(self, mouse):
        self.modal_background()
        self.clicks = []
        rr(self.screen, (37, 65, 66), (190, 98, 720, 530), 20)
        txt(self.screen, self.big, 'HOW TO PLAY', (232, 131), GOLD)
        instructions = [
            '1. Choose PLANT [1] and a seed type (Carrot, Tomato, Corn, Pumpkin).',
            '2. Click an empty soil plot to plant a seed (costs 1 energy).',
            '3. Choose WATER [2] and click planted crops (costs 1 energy).',
            '4. Click SLEEP or press [N] to end the day and grow watered crops.',
            '5. Repeat watering and sleeping until the crop says READY!',
            '6. Choose HARVEST [3] and click a ripe crop to collect it.',
            '7. Visit the MARKET [B] to sell crops and buy new seeds.',
            '8. Buy upgrades: a 3-plot sprinkler and +6 maximum energy.',
            'Rainy weather waters all planted crops for free overnight.',
            'F5 = Save  |  F9 = Load  |  ESC = Pause / close menu',
        ]
        for i, line in enumerate(instructions):
            txt(self.screen, self.small, line, (234, 215+i*32), WHITE if i < 8 else GOLD)
        pair = self.button(pygame.Rect(732, 575, 145, 36), 'LET\'S FARM!', 'close', mouse, primary=True, font=self.small)
        if pair: self.clicks.append(pair)

    def draw_pause(self, mouse):
        self.modal_background()
        self.clicks = []
        rr(self.screen, (37, 65, 66), (362, 225, 376, 264), 20)
        txt(self.screen, self.big, 'PAUSED', (550, 264), GOLD, center=True)
        for i, (label, action) in enumerate([('RESUME', 'resume'), ('SAVE GAME', 'save'), ('HELP', 'help')]):
            pair = self.button(pygame.Rect(417, 321+i*50, 267, 39), label, action, mouse, primary=i==0)
            if pair: self.clicks.append(pair)

    def click(self, pos):
        if self.shop or self.help or self.pause:
            for rect, action in self.clicks:
                if rect.collidepoint(pos):
                    self.handle(action)
                    return
            return
        for rect, action in self.clicks:
            if rect.collidepoint(pos):
                self.handle(action)
                return
        for i in range(24):
            if self.plot_rect(i).collidepoint(pos):
                self.action(i)
                return

    def handle(self, action):
        if isinstance(action, tuple):
            kind, val = action
            if kind == 'tool': self.tool = val
            elif kind == 'crop': self.selected_crop = val
            elif kind == 'buy': self.buy_seed(val)
            elif kind == 'sell': self.sell(val)
            elif kind == 'upgrade': self.upgrade(val)
        elif action == 'shop': self.shop = True
        elif action == 'sleep': self.sleep()
        elif action == 'save': self.save()
        elif action == 'help':
            self.pause = False
            self.help = True
        elif action == 'resume': self.pause = False
        elif action == 'close':
            self.shop = False
            self.help = False

    def update(self):
        for p in self.particles[:]:
            p[0] += p[2]
            p[1] += p[3]
            p[3] += .09
            p[4] -= 1
            if p[4] <= 0: self.particles.remove(p)
        if self.toast_timer > 0: self.toast_timer -= 1
        self.anim += 1

    def run(self):
        running = True
        while running:
            self.clock.tick(FPS)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
                    self.click(event.pos)
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_F5: self.save()
                    elif event.key == pygame.K_F9: self.load()
                    elif event.key == pygame.K_ESCAPE:
                        if self.shop or self.help:
                            self.shop = self.help = False
                        else: self.pause = not self.pause
                    elif self.pause:
                        pass
                    elif event.key == pygame.K_h:
                        self.help = not self.help
                        self.shop = False
                    elif event.key == pygame.K_b:
                        self.shop = not self.shop
                        self.help = False
                    elif not self.shop and not self.help:
                        if event.key == pygame.K_n: self.sleep()
                        elif event.key in (pygame.K_1, pygame.K_2, pygame.K_3, pygame.K_4):
                            self.tool = ['plant', 'water', 'harvest', 'clear'][event.key-pygame.K_1]
            self.update()
            self.draw()
        pygame.quit()


if __name__ == '__main__':
    Game().run()
