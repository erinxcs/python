"""ERINX BOXING: Neon Fight Night — standalone Pygame arcade boxing."""
import math
import random
import sys
from dataclasses import dataclass

import pygame

WIDTH, HEIGHT = 1000, 620
FPS = 60
FLOOR = 507
LEFT, RIGHT = 95, 905
ROUND_SECONDS = 45
MAX_ROUNDS = 3

BG = (9, 12, 25)
WHITE = (239, 243, 255)
MUTED = (139, 157, 194)
CYAN = (35, 215, 244)
PINK = (255, 80, 130)
GOLD = (255, 209, 104)
GREEN = (78, 238, 167)

pygame.init()
screen = pygame.display.set_mode((WIDTH, HEIGHT))
pygame.display.set_caption("ERINX BOXING | Neon Fight Night")
clock = pygame.time.Clock()


def font(size, bold=False):
    return pygame.font.SysFont("consolas", size, bold=bold)

F_SMALL = font(17)
F_MED = font(23, True)
F_LARGE = font(38, True)
F_TITLE = font(71, True)


def label(text, fnt, color, x, y, center=False):
    image = fnt.render(str(text), True, color)
    rect = image.get_rect(center=(x, y)) if center else image.get_rect(topleft=(x, y))
    screen.blit(image, rect)


def clamp(value, lo, hi):
    return max(lo, min(hi, value))


def bar(x, y, width, val, color, title, invert=False):
    pygame.draw.rect(screen, (43, 51, 74), (x, y, width, 17), border_radius=7)
    fill = int((width - 4) * clamp(val, 0, 100) / 100)
    inner_x = x + width - 2 - fill if invert else x + 2
    if fill > 0:
        pygame.draw.rect(screen, color, (inner_x, y + 2, fill, 13), border_radius=5)
    label(title, F_SMALL, MUTED, x, y - 24)


@dataclass
class Spark:
    x: float
    y: float
    vx: float
    vy: float
    ttl: float
    color: tuple


class Fighter:
    def __init__(self, x, name, shirt, glove, ai=False):
        self.x = float(x)
        self.name = name
        self.shirt = shirt
        self.glove = glove
        self.ai = ai
        self.health = 100.0
        self.stamina = 100.0
        self.face = 1
        self.action = None
        self.action_time = 0.0
        self.cooldown = 0.0
        self.stun = 0.0
        self.invulnerable = 0.0
        self.blocking = False
        self.dodging = 0.0
        self.walk_phase = 0.0
        self.wins = 0
        self.hits = 0
        self.ai_think = 0.0
        self.ai_move = 0
        self.ai_block = False

    def reset_round(self, x):
        self.x = float(x)
        self.health = 100.0
        self.stamina = 100.0
        self.action = None
        self.action_time = 0.0
        self.cooldown = 0.0
        self.stun = 0.0
        self.invulnerable = 0.0
        self.blocking = False
        self.dodging = 0.0
        self.ai_move = 0
        self.ai_block = False

    def attack(self, kind):
        costs = {"jab": 13, "hook": 26}
        if self.cooldown > 0 or self.stun > 0 or self.action or self.blocking:
            return False
        if self.stamina < costs[kind]:
            return False
        self.stamina -= costs[kind]
        self.action = kind
        self.action_time = 0.0
        self.cooldown = 0.29 if kind == "jab" else 0.51
        return True

    def update(self, dt):
        self.cooldown = max(0, self.cooldown - dt)
        self.stun = max(0, self.stun - dt)
        self.invulnerable = max(0, self.invulnerable - dt)
        self.dodging = max(0, self.dodging - dt)
        self.stamina = min(100, self.stamina + (8 if self.blocking else 17) * dt)
        if self.action:
            self.action_time += dt
            if self.action_time >= (0.27 if self.action == "jab" else 0.42):
                self.action = None
                self.action_time = 0

    def active_punch(self):
        if self.action == "jab" and 0.08 < self.action_time < 0.19:
            return 10, 80
        if self.action == "hook" and 0.16 < self.action_time < 0.30:
            return 19, 66
        return None

    def draw(self, t):
        x = int(self.x)
        bob = math.sin(self.walk_phase) * 3
        y = FLOOR + int(bob)
        direction = self.face
        if self.dodging:
            y += 19
        if self.stun:
            x -= direction * 8
        # shadow and back limbs
        pygame.draw.ellipse(screen, (3, 6, 15), (x - 48, FLOOR - 2, 96, 15))
        for foot in [-1, 1]:
            legx = x + foot * 17
            pygame.draw.line(screen, (39, 53, 82), (x + foot * 12, y - 65), (legx, y - 14), 17)
            pygame.draw.ellipse(screen, (15, 20, 34), (legx - 19, y - 17, 40, 18))
        # torso
        pygame.draw.rect(screen, self.shirt, (x - 29, y - 150, 58, 87), border_radius=17)
        pygame.draw.rect(screen, (21, 25, 40), (x - 29, y - 79, 58, 18), border_radius=5)
        pygame.draw.line(screen, (245, 187, 142), (x, y - 153), (x, y - 163), 16)
        # face
        pygame.draw.circle(screen, (238, 180, 136), (x, y - 189), 30)
        pygame.draw.arc(screen, (26, 29, 49), (x - 30, y - 218, 60, 48), math.pi * .10, math.pi * .95, 9)
        pygame.draw.circle(screen, (25, 27, 39), (x + direction * 11, y - 191), 3)
        pygame.draw.line(screen, (132, 68, 71), (x + direction * 8, y - 174), (x + direction * 19, y - 175), 3)
        # arms + punching glove
        back_shoulder = (x - direction * 20, y - 135)
        pygame.draw.line(screen, (228, 167, 122), back_shoulder, (x - direction * 30, y - 110), 15)
        pygame.draw.circle(screen, self.glove, (x - direction * 24, y - 123), 19)
        reach = 0
        upper = 0
        if self.action == "jab":
            phase = clamp(self.action_time / 0.13, 0, 1)
            if self.action_time > .15:
                phase = clamp((.27 - self.action_time) / .12, 0, 1)
            reach = int(68 * phase)
        if self.action == "hook":
            phase = math.sin(clamp(self.action_time / .42, 0, 1) * math.pi)
            reach = int(54 * phase)
            upper = int(13 * phase)
        if self.blocking:
            front = (x + direction * 22, y - 185)
        else:
            front = (x + direction * (31 + reach), y - 128 - upper)
        pygame.draw.line(screen, (236, 178, 133), (x + direction * 20, y - 139), front, 15)
        pygame.draw.circle(screen, self.glove, front, 20)
        pygame.draw.circle(screen, (255, 255, 255), (front[0] - 6, front[1] - 7), 5)
        if self.invulnerable > 0:
            pygame.draw.circle(screen, WHITE, (x, y - 145), 65, 2)


class Game:
    def __init__(self):
        self.state = "menu"
        self.player = Fighter(330, "YOU", CYAN, (12, 155, 224))
        self.enemy = Fighter(670, "IRON VIPER", PINK, (214, 37, 95), ai=True)
        self.round = 1
        self.seconds = ROUND_SECONDS
        self.pause_timer = 0.0
        self.flash = 0.0
        self.sparks = []
        self.notice = ""
        self.notice_timer = 0.0
        self.result = ""
        self.time = 0.0

    def start(self):
        self.round = 1
        self.player.wins = self.enemy.wins = 0
        self.next_round()

    def next_round(self):
        self.player.reset_round(325)
        self.enemy.reset_round(675)
        self.seconds = ROUND_SECONDS
        self.state = "fight"
        self.pause_timer = 1.4
        self.notice = f"ROUND {self.round} - FIGHT!"
        self.notice_timer = 1.5
        self.sparks.clear()

    def message(self, text, duration=1.0):
        self.notice = text
        self.notice_timer = duration

    def hit(self, attacker, defender, damage, reach):
        if defender.invulnerable or defender.dodging > 0:
            return
        if abs(attacker.x - defender.x) > reach:
            return
        blocked = defender.blocking and defender.face == -attacker.face
        actual = damage * (0.22 if blocked else 1.0)
        defender.health = max(0, defender.health - actual)
        defender.stun = 0.04 if blocked else (0.20 if damage > 15 else 0.13)
        defender.invulnerable = 0.14
        defender.x = clamp(defender.x + attacker.face * (7 if blocked else 17), LEFT, RIGHT)
        attacker.hits += 1
        for _ in range(12 if blocked else 22):
            a = random.random() * math.tau
            speed = random.uniform(55, 220)
            self.sparks.append(Spark(defender.x + attacker.face * 8, FLOOR - 168,
                                    math.cos(a) * speed, math.sin(a) * speed,
                                    random.uniform(0.2, 0.55), GOLD if blocked else WHITE))
        self.flash = 0.07 if blocked else 0.12
        if defender.health <= 0:
            self.finish_round(attacker, knockout=True)

    def finish_round(self, winner, knockout=False):
        winner.wins += 1
        if knockout or winner.wins == 2 or self.round >= MAX_ROUNDS:
            self.state = "gameover"
            self.result = "YOU WIN!" if winner is self.player else "YOU LOSE"
            self.message("KNOCKOUT!" if knockout else "FINAL BELL!", 3)
        else:
            self.state = "break"
            self.pause_timer = 2.6
            self.message(("YOU TAKE" if winner is self.player else "VIPER TAKES") + " THE ROUND", 2.5)

    def manage_round_timeout(self):
        if self.player.health == self.enemy.health:
            winner = self.player if self.player.hits >= self.enemy.hits else self.enemy
        else:
            winner = self.player if self.player.health > self.enemy.health else self.enemy
        self.finish_round(winner)

    def update_ai(self, dt):
        ai, target = self.enemy, self.player
        distance = abs(ai.x - target.x)
        ai.ai_think -= dt
        if ai.ai_think <= 0:
            ai.ai_think = random.uniform(0.15, 0.42)
            threat = target.action and distance < 142
            ai.ai_block = bool(threat and random.random() < .66)
            if distance > 118:
                ai.ai_move = -1 if ai.x > target.x else 1
            elif distance < 71:
                ai.ai_move = 1 if ai.x > target.x else -1
            else:
                ai.ai_move = random.choice([0, 0, -1, 1])
            if 63 < distance < 136 and not ai.ai_block and random.random() < .76:
                ai.attack("hook" if random.random() < .29 else "jab")
        ai.blocking = ai.ai_block and not ai.action and ai.stun <= 0
        if ai.stun <= 0 and not ai.blocking and not ai.action:
            ai.x += ai.ai_move * 148 * dt
            ai.walk_phase += abs(ai.ai_move) * 10 * dt

    def update(self, dt, keys):
        self.time += dt
        self.notice_timer = max(0, self.notice_timer - dt)
        self.flash = max(0, self.flash - dt)
        for p in self.sparks[:]:
            p.x += p.vx * dt
            p.y += p.vy * dt
            p.vy += 250 * dt
            p.ttl -= dt
            if p.ttl <= 0:
                self.sparks.remove(p)
        if self.state == "break":
            self.pause_timer -= dt
            if self.pause_timer <= 0:
                self.round += 1
                self.next_round()
            return
        if self.state != "fight":
            return
        if self.pause_timer > 0:
            self.pause_timer -= dt
            return
        p, e = self.player, self.enemy
        p.face = 1 if e.x >= p.x else -1
        e.face = -p.face
        p.update(dt)
        e.update(dt)
        p.blocking = bool(keys[pygame.K_l] or keys[pygame.K_s]) and not p.action and not p.stun
        direction = int(bool(keys[pygame.K_d] or keys[pygame.K_RIGHT])) - int(bool(keys[pygame.K_a] or keys[pygame.K_LEFT]))
        if p.stun <= 0 and not p.blocking and not p.action:
            p.x += direction * 210 * dt
            p.walk_phase += abs(direction) * 12 * dt
        self.update_ai(dt)
        p.x = clamp(p.x, LEFT, RIGHT)
        e.x = clamp(e.x, LEFT, RIGHT)
        # Prevent fighters from physically overlapping.
        gap = e.x - p.x
        if abs(gap) < 65:
            push = (65 - abs(gap)) / 2
            side = 1 if gap >= 0 else -1
            p.x = clamp(p.x - side * push, LEFT, RIGHT)
            e.x = clamp(e.x + side * push, LEFT, RIGHT)
        for attacker, defender in ((p, e), (e, p)):
            punch = attacker.active_punch()
            if punch and not getattr(attacker, "_landed", False):
                self.hit(attacker, defender, *punch)
                attacker._landed = True
            if not attacker.action:
                attacker._landed = False
            if self.state != "fight":
                break
        if self.state == "fight":
            self.seconds -= dt
            if self.seconds <= 0:
                self.seconds = 0
                self.manage_round_timeout()

    def event(self, evt):
        if evt.type == pygame.QUIT:
            pygame.quit()
            sys.exit()
        if evt.type != pygame.KEYDOWN:
            return
        if evt.key == pygame.K_F11:
            global screen
            fullscreen = bool(screen.get_flags() & pygame.FULLSCREEN)
            screen = pygame.display.set_mode(
                (WIDTH, HEIGHT), 0 if fullscreen else pygame.FULLSCREEN
            )
        elif evt.key == pygame.K_ESCAPE:
            if self.state == "fight":
                self.state = "paused"
            elif self.state == "paused":
                self.state = "fight"
            else:
                self.state = "menu"
        elif evt.key == pygame.K_RETURN:
            if self.state in ("menu", "gameover"):
                self.start()
            elif self.state == "paused":
                self.state = "fight"
        elif evt.key == pygame.K_r and self.state == "gameover":
            self.start()
        elif self.state == "fight" and self.pause_timer <= 0:
            if evt.key in (pygame.K_j, pygame.K_z):
                if self.player.attack("jab"):
                    self.player._landed = False
            elif evt.key in (pygame.K_k, pygame.K_x):
                if self.player.attack("hook"):
                    self.player._landed = False
            elif evt.key in (pygame.K_SPACE, pygame.K_LSHIFT, pygame.K_RSHIFT):
                p = self.player
                if p.stamina >= 17 and p.dodging <= 0 and not p.action:
                    p.stamina -= 17
                    p.dodging = 0.38
                    p.invulnerable = 0.38
                    p.x = clamp(p.x - p.face * 70, LEFT, RIGHT)

    def environment(self):
        for y in range(HEIGHT):
            mix = y / HEIGHT
            col = (int(9 + mix * 12), int(12 + mix * 10), int(25 + mix * 18))
            pygame.draw.line(screen, col, (0, y), (WIDTH, y))
        # crowd and stadium beams
        for i in range(25):
            x = 15 + i * 41
            y = 300 + int(math.sin(i * 9.3) * 24)
            pygame.draw.circle(screen, (22, 36, 62), (x, y), 18)
            pygame.draw.circle(screen, (9, 15, 28), (x, y - 5), 12)
        pygame.draw.ellipse(screen, (24, 43, 69), (70, 416, 860, 180))
        pygame.draw.rect(screen, (20, 25, 42), (49, FLOOR, 902, 76))
        for i, c in enumerate([CYAN, (236, 240, 255), PINK]):
            y = 362 + i * 46
            pygame.draw.line(screen, c, (57, y), (943, y), 4)
        for x in (61, 939):
            pygame.draw.rect(screen, (98, 110, 143), (x - 7, 332, 14, 220), border_radius=5)
        pygame.draw.line(screen, (59, 72, 102), (0, 580), (WIDTH, 580), 4)
        label("ERINX   /   FIGHT NIGHT", F_MED, (45, 64, 88), WIDTH // 2, 555, center=True)

    def hud(self):
        pygame.draw.rect(screen, (13, 19, 34), (0, 0, WIDTH, 124))
        label("BLUE CORNER", F_SMALL, CYAN, 55, 14)
        label("RED CORNER", F_SMALL, PINK, 793, 14)
        bar(55, 52, 305, self.player.health, CYAN, "HEALTH")
        bar(640, 52, 305, self.enemy.health, PINK, "HEALTH", invert=True)
        pygame.draw.rect(screen, (40, 49, 70), (55, 83, 305, 9), border_radius=5)
        pygame.draw.rect(screen, (40, 49, 70), (640, 83, 305, 9), border_radius=5)
        pygame.draw.rect(screen, GOLD, (55, 83, max(0, int(305 * self.player.stamina / 100)), 9), border_radius=5)
        pygame.draw.rect(screen, GOLD, (945 - max(0, int(305 * self.enemy.stamina / 100)), 83, max(0, int(305 * self.enemy.stamina / 100)), 9), border_radius=5)
        label("STAMINA", F_SMALL, MUTED, 55, 96)
        label("STAMINA", F_SMALL, MUTED, 862, 96)
        label(f"{math.ceil(self.seconds):02d}", F_LARGE, WHITE, 500, 62, center=True)
        label(f"ROUND {self.round}/{MAX_ROUNDS}", F_SMALL, GOLD, 500, 107, center=True)
        label(f"{self.player.wins} - {self.enemy.wins}", F_SMALL, MUTED, 500, 19, center=True)
        label("A/D MOVE   J JAB   K HOOK   L BLOCK   SPACE DODGE   ESC PAUSE", F_SMALL, MUTED, WIDTH // 2, 598, center=True)

    def overlay(self, heading, lines, color=WHITE):
        tint = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        tint.fill((3, 8, 20, 205))
        screen.blit(tint, (0, 0))
        label(heading, F_TITLE, color, WIDTH // 2, 207, center=True)
        for i, line in enumerate(lines):
            label(line, F_MED if i == 0 else F_SMALL, WHITE if i == 0 else MUTED,
                  WIDTH // 2, 310 + 37 * i, center=True)

    def draw(self):
        self.environment()
        self.player.draw(self.time)
        self.enemy.draw(self.time)
        for s in self.sparks:
            pygame.draw.circle(screen, s.color, (int(s.x), int(s.y)), max(1, int(s.ttl * 9)))
        self.hud()
        if self.flash > 0:
            layer = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            layer.fill((255, 255, 255, int(self.flash / .12 * 54)))
            screen.blit(layer, (0, 0))
        if self.notice_timer > 0 and self.state in ("fight", "break"):
            label(self.notice, F_LARGE, GOLD, WIDTH // 2, 246, center=True)
        if self.state == "menu":
            self.overlay("ERINX BOXING", ["NEON FIGHT NIGHT", "3 rounds | 45 seconds each | Best of 3",
                                          "A / D move     J jab     K hook     L block",
                                          "SPACE dodge      ESC pause",
                                          "PRESS ENTER TO FIGHT"], CYAN)
        elif self.state == "paused":
            self.overlay("PAUSED", ["PRESS ENTER OR ESC TO RESUME", "Stay sharp, champ."], GOLD)
        elif self.state == "gameover":
            win = self.result == "YOU WIN!"
            self.overlay(self.result, ["KNOCKOUT!" if self.seconds > 0 else "MATCH COMPLETE",
                                       f"Rounds won: You {self.player.wins} - {self.enemy.wins} Viper",
                                       "PRESS ENTER / R TO PLAY AGAIN", "ESC FOR MENU"], GREEN if win else PINK)
        pygame.display.flip()


def main():
    game = Game()
    while True:
        dt = min(clock.tick(FPS) / 1000, .04)
        for event in pygame.event.get():
            game.event(event)
        game.update(dt, pygame.key.get_pressed())
        game.draw()


if __name__ == "__main__":
    main()
