"""ERINX: STARFALL — self-contained arcade shooter built with Pygame."""
import json
import math
import random
from pathlib import Path

import pygame

WIDTH, HEIGHT = 960, 640
FPS = 60
SAVE = Path(__file__).with_name('highscore.json')
V2 = pygame.Vector2
BG = (7, 10, 25)
WHITE = (225, 240, 255)
CYAN = (70, 227, 255)
PINK = (255, 83, 158)
GOLD = (255, 205, 84)
GREEN = (103, 255, 168)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def text(surface, font, message, x, y, color=WHITE, center=False):
    image = font.render(str(message), True, color)
    rect = image.get_rect(center=(x, y)) if center else image.get_rect(topleft=(x, y))
    surface.blit(image, rect)


def glow_circle(surface, center, radius, color):
    x, y = int(center[0]), int(center[1])
    for amount, alpha in ((2.8, 16), (1.9, 32), (1.3, 54)):
        r = max(1, int(radius * amount))
        layer = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
        pygame.draw.circle(layer, (*color, alpha), (r + 1, r + 1), r)
        surface.blit(layer, (x-r-1, y-r-1), special_flags=pygame.BLEND_RGBA_ADD)
    pygame.draw.circle(surface, color, (x, y), max(1, int(radius)))


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption('ERINX: STARFALL | Space Shooter')
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        self.font = pygame.font.SysFont('consolas', 19, bold=True)
        self.small = pygame.font.SysFont('consolas', 15)
        self.medium = pygame.font.SysFont('consolas', 30, bold=True)
        self.large = pygame.font.SysFont('consolas', 68, bold=True)
        self.stars = [[random.uniform(0, WIDTH), random.uniform(0, HEIGHT), random.uniform(40, 190), random.choice([1, 1, 2])] for _ in range(115)]
        try:
            self.best = max(0, int(json.loads(SAVE.read_text()).get('best', 0)))
        except (OSError, ValueError, TypeError, AttributeError):
            self.best = 0
        self.state = 'menu'
        self.reset()

    def reset(self):
        self.player = V2(WIDTH/2, HEIGHT-93)
        self.hp = 100
        self.shield = 0
        self.lives = 3
        self.score = 0
        self.wave = 1
        self.kills = 0
        self.boss_spawned = False
        self.enemies = []
        self.bullets = []
        self.enemy_bullets = []
        self.powerups = []
        self.particles = []
        self.cooldown = 0
        self.spawn_timer = 0.7
        self.invulnerable = 0
        self.rapid = 0
        self.triple = 0
        self.shake = 0
        self.banner = 2
        self.elapsed = 0
        self.boss = None

    def emit(self, pos, color, count=12, strength=190):
        for _ in range(count):
            angle = random.uniform(0, math.tau)
            speed = random.uniform(40, strength)
            self.particles.append({'pos': V2(pos), 'vel': V2(math.cos(angle), math.sin(angle))*speed,
                                   'life': random.uniform(.2, .65), 'max': .65, 'color': color, 'r': random.uniform(1.5, 4)})

    def fire(self):
        if self.cooldown > 0:
            return
        self.cooldown = .105 if self.rapid > 0 else .21
        offsets = [(-15, -0.22), (0, 0), (15, .22)] if self.triple > 0 else [(0, 0)]
        for ox, dx in offsets:
            self.bullets.append({'pos': self.player + V2(ox, -23), 'vel': V2(dx*250, -660), 'radius': 5, 'damage': 24})
        self.emit(self.player + V2(0, -20), CYAN, 3, 70)

    def spawn_enemy(self):
        x = random.randint(42, WIDTH-42)
        elite = self.wave >= 3 and random.random() < .22
        self.enemies.append({'pos': V2(x, -36), 'base': x, 'age': 0., 'speed': random.uniform(105, 160)+self.wave*13,
                             'hp': 78 if elite else 38, 'maxhp': 78 if elite else 38, 'elite': elite,
                             'shot': random.uniform(1.1, 2.4), 'radius': 22 if elite else 18})

    def spawn_boss(self):
        self.boss = {'pos': V2(WIDTH/2, -75), 'hp': 750+self.wave*90, 'maxhp': 750+self.wave*90,
                     'age': 0., 'shot': 1., 'radius': 65}
        self.boss_spawned = True
        self.banner = 2.5

    def damage_player(self, damage):
        if self.invulnerable > 0:
            return
        if self.shield > 0:
            absorbed = min(self.shield, damage)
            self.shield -= absorbed
            damage -= absorbed
        self.hp -= damage
        self.invulnerable = .75
        self.shake = 9
        self.emit(self.player, CYAN if self.shield > 0 else PINK, 19)
        if self.hp <= 0:
            self.lives -= 1
            if self.lives <= 0:
                self.state = 'gameover'
                if self.score > self.best:
                    self.best = self.score
                    try:
                        SAVE.write_text(json.dumps({'best': self.best}, indent=2))
                    except OSError:
                        pass
            else:
                self.hp = 100
                self.invulnerable = 2.0
                self.player = V2(WIDTH/2, HEIGHT-93)

    def kill_enemy(self, enemy):
        self.score += 180 if enemy['elite'] else 100
        self.kills += 1
        self.emit(enemy['pos'], GOLD if enemy['elite'] else PINK, 22)
        if random.random() < .15:
            kind = random.choice(['heal', 'shield', 'rapid', 'triple'])
            self.powerups.append({'pos': V2(enemy['pos']), 'kind': kind, 'age': 0})
        if self.kills >= 8 + self.wave*3 and self.boss is None and not self.boss_spawned:
            self.spawn_boss()

    def update(self, dt):
        for star in self.stars:
            star[1] += star[2]*dt*(1.6 if self.state == 'playing' else .38)
            if star[1] > HEIGHT:
                star[0], star[1] = random.uniform(0, WIDTH), -4
        for part in self.particles[:]:
            part['pos'] += part['vel']*dt
            part['vel'] *= max(0, 1-2*dt)
            part['life'] -= dt
            if part['life'] <= 0:
                self.particles.remove(part)
        self.shake = max(0, self.shake-35*dt)
        if self.state != 'playing':
            return
        self.elapsed += dt
        self.banner -= dt
        self.invulnerable = max(0, self.invulnerable-dt)
        self.cooldown -= dt
        self.rapid = max(0, self.rapid-dt)
        self.triple = max(0, self.triple-dt)
        keys = pygame.key.get_pressed()
        direction = V2(int(keys[pygame.K_d] or keys[pygame.K_RIGHT])-int(keys[pygame.K_a] or keys[pygame.K_LEFT]),
                       int(keys[pygame.K_s] or keys[pygame.K_DOWN])-int(keys[pygame.K_w] or keys[pygame.K_UP]))
        if direction.length_squared():
            self.player += direction.normalize()*345*dt
        self.player.x = clamp(self.player.x, 24, WIDTH-24)
        self.player.y = clamp(self.player.y, 88, HEIGHT-28)
        if keys[pygame.K_SPACE] or keys[pygame.K_j]:
            self.fire()
        self.spawn_timer -= dt
        if self.spawn_timer <= 0 and self.boss is None and not self.boss_spawned:
            self.spawn_enemy()
            self.spawn_timer = max(.27, 1.1-self.wave*.08)*random.uniform(.7, 1.35)
        for bullet in self.bullets[:]:
            bullet['pos'] += bullet['vel']*dt
            if bullet['pos'].y < -20 or not (-30 < bullet['pos'].x < WIDTH+30):
                self.bullets.remove(bullet)
                continue
            hit = False
            for enemy in self.enemies[:]:
                if bullet['pos'].distance_squared_to(enemy['pos']) < (enemy['radius']+7)**2:
                    enemy['hp'] -= bullet['damage']
                    self.emit(bullet['pos'], GOLD, 5, 90)
                    hit = True
                    if enemy['hp'] <= 0:
                        self.enemies.remove(enemy)
                        self.kill_enemy(enemy)
                    break
            if not hit and self.boss is not None and bullet['pos'].distance_squared_to(self.boss['pos']) < 62**2:
                self.boss['hp'] -= bullet['damage']
                self.emit(bullet['pos'], PINK, 5, 95)
                hit = True
                if self.boss['hp'] <= 0:
                    self.emit(self.boss['pos'], GOLD, 95, 390)
                    self.score += 2500
                    self.boss = None
                    self.wave += 1
                    self.kills = 0
                    self.boss_spawned = False
                    self.enemies.clear()
                    self.enemy_bullets.clear()
                    self.spawn_timer = 1.5
                    self.banner = 3
                    self.shake = 18
            if hit and bullet in self.bullets:
                self.bullets.remove(bullet)
        for enemy in self.enemies[:]:
            enemy['age'] += dt
            enemy['pos'].y += enemy['speed']*dt
            enemy['pos'].x = enemy['base'] + math.sin(enemy['age']*2.7)*36
            enemy['shot'] -= dt
            if enemy['shot'] <= 0 and enemy['pos'].y > 0:
                aim = self.player-enemy['pos']
                if aim.length_squared():
                    self.enemy_bullets.append({'pos': enemy['pos'].copy(), 'vel': aim.normalize()*(230+self.wave*12), 'radius': 6})
                enemy['shot'] = random.uniform(1.2, 2.5)
            if enemy['pos'].y > HEIGHT+35:
                self.enemies.remove(enemy)
                continue
            if enemy['pos'].distance_squared_to(self.player) < (enemy['radius']+19)**2:
                self.damage_player(30)
                self.emit(enemy['pos'], PINK, 17)
                self.enemies.remove(enemy)
        if self.boss:
            b = self.boss
            b['age'] += dt
            b['pos'].y = min(125, b['pos'].y+100*dt)
            b['pos'].x = WIDTH/2 + math.sin(b['age']*.9)*275
            b['shot'] -= dt
            if b['shot'] <= 0 and b['pos'].y >= 120:
                for a in range(-2, 3):
                    angle = math.pi/2 + a*.23 + math.sin(b['age'])*.15
                    self.enemy_bullets.append({'pos': b['pos']+V2(0, 38), 'vel': V2(math.cos(angle), math.sin(angle))*300, 'radius': 8})
                b['shot'] = .74
            if b['pos'].distance_squared_to(self.player) < 79**2:
                self.damage_player(40)
        for bullet in self.enemy_bullets[:]:
            bullet['pos'] += bullet['vel']*dt
            if not (-25 < bullet['pos'].x < WIDTH+25 and -25 < bullet['pos'].y < HEIGHT+25):
                self.enemy_bullets.remove(bullet)
            elif bullet['pos'].distance_squared_to(self.player) < (bullet['radius']+16)**2:
                self.damage_player(17)
                self.enemy_bullets.remove(bullet)
        colors = {'heal': GREEN, 'shield': CYAN, 'rapid': GOLD, 'triple': PINK}
        for power in self.powerups[:]:
            power['age'] += dt
            power['pos'].y += 95*dt
            if power['pos'].y > HEIGHT+30:
                self.powerups.remove(power)
            elif power['pos'].distance_squared_to(self.player) < 32**2:
                kind = power['kind']
                if kind == 'heal': self.hp = min(100, self.hp+35)
                if kind == 'shield': self.shield = min(100, self.shield+50)
                if kind == 'rapid': self.rapid = 9
                if kind == 'triple': self.triple = 9
                self.emit(power['pos'], colors[kind], 24)
                self.score += 50
                self.powerups.remove(power)

    def draw_ship(self, surface, pos, color, enemy=False, elite=False):
        x, y = int(pos.x), int(pos.y)
        if enemy:
            points = [(x, y+19), (x-23, y-12), (x-9, y-7), (x, y-18), (x+9, y-7), (x+23, y-12)]
            pygame.draw.polygon(surface, color, points)
            pygame.draw.polygon(surface, (48, 21, 63), points, 3)
            glow_circle(surface, (x, y+2), 5, GOLD if elite else PINK)
        else:
            points = [(x, y-27), (x-18, y+15), (x-13, y+12), (x-24, y+21), (x-6, y+17), (x, y+11),
                      (x+6, y+17), (x+24, y+21), (x+13, y+12), (x+18, y+15)]
            pygame.draw.polygon(surface, (23, 91, 151), points)
            pygame.draw.polygon(surface, color, points, 3)
            glow_circle(surface, (x, y-2), 5, CYAN)
            if self.state == 'playing':
                pygame.draw.polygon(surface, GOLD, [(x-7, y+18), (x, y+random.randint(27, 42)), (x+7, y+18)])

    def draw(self):
        canvas = pygame.Surface((WIDTH, HEIGHT))
        canvas.fill(BG)
        for x, y, _, r in self.stars:
            pygame.draw.circle(canvas, (60+r*35, 90+r*22, 135+r*30), (int(x), int(y)), r)
        for i in range(8):
            pygame.draw.line(canvas, (12, 19, 39), (i*140, 0), (i*140, HEIGHT), 1)
        for i in range(7):
            pygame.draw.line(canvas, (12, 19, 39), (0, i*110), (WIDTH, i*110), 1)
        for part in self.particles:
            fraction = max(0, part['life']/part['max'])
            pygame.draw.circle(canvas, part['color'], part['pos'], max(1, int(part['r']*fraction)))
        if self.state in ('playing', 'paused', 'gameover'):
            for power in self.powerups:
                col = {'heal': GREEN, 'shield': CYAN, 'rapid': GOLD, 'triple': PINK}[power['kind']]
                glow_circle(canvas, power['pos'], 12, col)
                mark = {'heal': '+', 'shield': 'S', 'rapid': 'R', 'triple': '3'}[power['kind']]
                text(canvas, self.font, mark, int(power['pos'].x), int(power['pos'].y), BG, True)
            for bullet in self.bullets:
                pygame.draw.line(canvas, CYAN, bullet['pos'], bullet['pos']+V2(0, 17), 4)
            for bullet in self.enemy_bullets:
                glow_circle(canvas, bullet['pos'], bullet['radius'], PINK)
            for enemy in self.enemies:
                self.draw_ship(canvas, enemy['pos'], GOLD if enemy['elite'] else PINK, True, enemy['elite'])
            if self.boss is not None:
                b = self.boss
                x, y = int(b['pos'].x), int(b['pos'].y)
                pygame.draw.polygon(canvas, (133, 40, 98), [(x-73,y-14),(x-35,y-39),(x,y-15),(x+35,y-39),(x+73,y-14),(x+51,y+38),(x,y+55),(x-51,y+38)])
                pygame.draw.polygon(canvas, PINK, [(x-73,y-14),(x-35,y-39),(x,y-15),(x+35,y-39),(x+73,y-14),(x+51,y+38),(x,y+55),(x-51,y+38)], 3)
                glow_circle(canvas, (x,y+8), 20, PINK)
                pygame.draw.rect(canvas, (55, 27, 54), (WIDTH//2-210, 83, 420, 12), border_radius=5)
                pygame.draw.rect(canvas, PINK, (WIDTH//2-210, 83, max(0, int(420*b['hp']/b['maxhp'])), 12), border_radius=5)
                text(canvas, self.small, 'THE VOID TITAN', WIDTH//2, 67, PINK, True)
            if self.invulnerable <= 0 or int(self.invulnerable*12)%2 == 0:
                self.draw_ship(canvas, self.player, CYAN)
            if self.shield > 0:
                pygame.draw.circle(canvas, CYAN, self.player, 31, 2)
            pygame.draw.rect(canvas, (12, 18, 38), (0, 0, WIDTH, 61))
            text(canvas, self.font, f'SCORE {self.score:07d}', 18, 12)
            text(canvas, self.small, f'BEST {max(self.best,self.score):07d}', 18, 37, (126, 143, 175))
            text(canvas, self.font, f'WAVE {self.wave}', 314, 20, GOLD)
            text(canvas, self.font, f'LIVES {self.lives}', 445, 20, CYAN)
            pygame.draw.rect(canvas, (46, 31, 50), (690, 12, 245, 16), border_radius=5)
            pygame.draw.rect(canvas, PINK, (690, 12, round(245*clamp(self.hp, 0, 100)/100), 16), border_radius=5)
            text(canvas, self.small, f'HULL {max(0,self.hp):03.0f}%', 695, 12)
            pygame.draw.rect(canvas, (29, 40, 56), (690, 35, 245, 9), border_radius=4)
            pygame.draw.rect(canvas, CYAN, (690, 35, round(245*clamp(self.shield, 0, 100)/100), 9), border_radius=4)
            if self.rapid > 0: text(canvas, self.small, f'RAPID {self.rapid:.0f}s', 20, 611, GOLD)
            if self.triple > 0: text(canvas, self.small, f'TRIPLE {self.triple:.0f}s', 165, 611, PINK)
            if self.banner > 0 and self.state == 'playing':
                text(canvas, self.medium, 'BOSS INBOUND!' if self.boss else f'WAVE {self.wave}', WIDTH//2, 205, GOLD if self.boss else CYAN, True)
        if self.state in ('menu', 'paused', 'gameover'):
            overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            overlay.fill((5, 7, 20, 205))
            canvas.blit(overlay, (0, 0))
            title = 'STARFALL' if self.state == 'menu' else ('PAUSED' if self.state == 'paused' else 'GAME OVER')
            color = CYAN if self.state != 'gameover' else PINK
            text(canvas, self.small, 'E R I N X  //  A R C A D E', WIDTH//2, 145, GOLD, True)
            text(canvas, self.large, title, WIDTH//2, 220, color, True)
            if self.state == 'gameover':
                text(canvas, self.medium, f'SCORE {self.score:,}     BEST {self.best:,}', WIDTH//2, 310, WHITE, True)
                text(canvas, self.font, 'PRESS ENTER TO TRY AGAIN', WIDTH//2, 385, GOLD, True)
            elif self.state == 'paused':
                text(canvas, self.font, 'PRESS P OR ESC TO RESUME', WIDTH//2, 345, GOLD, True)
            else:
                text(canvas, self.font, 'SURVIVE THE WAVES. DEFEAT THE VOID TITAN.', WIDTH//2, 320, WHITE, True)
                text(canvas, self.medium, 'PRESS ENTER TO LAUNCH', WIDTH//2, 393, GOLD, True)
                text(canvas, self.small, f'PERSONAL BEST  {self.best:,}', WIDTH//2, 440, (140, 168, 200), True)
            text(canvas, self.small, 'WASD / ARROWS: MOVE    SPACE / J: FIRE    P / ESC: PAUSE', WIDTH//2, 548, (154, 175, 209), True)
            text(canvas, self.small, 'GREEN +HEAL    BLUE SHIELD    YELLOW RAPID    PINK TRIPLE', WIDTH//2, 575, (154, 175, 209), True)
        if self.shake and self.state == 'playing':
            self.screen.fill(BG)
            offset = (random.randint(-int(self.shake), int(self.shake)), random.randint(-int(self.shake), int(self.shake)))
            self.screen.blit(canvas, offset)
        else:
            self.screen.blit(canvas, (0, 0))
        pygame.display.flip()

    def run(self):
        running = True
        while running:
            dt = min(self.clock.tick(FPS)/1000, .04)
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_RETURN and self.state in ('menu', 'gameover'):
                        self.reset()
                        self.state = 'playing'
                    elif event.key in (pygame.K_ESCAPE, pygame.K_p):
                        if self.state == 'playing': self.state = 'paused'
                        elif self.state == 'paused': self.state = 'playing'
                        elif self.state == 'menu' and event.key == pygame.K_ESCAPE: running = False
            self.update(dt)
            self.draw()
        pygame.quit()


if __name__ == '__main__':
    Game().run()
