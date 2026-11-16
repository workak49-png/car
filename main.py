import math
import random
import sys

import pygame

WIDTH, HEIGHT = 960, 600
FPS = 60
HORIZON = HEIGHT // 2

SEG_LEN = 200
ROAD_W = 2000
RUMBLE_LEN = 3
LANES = 3
CAMERA_HEIGHT = 1000
FOV = 100
CAMERA_DEPTH = 1 / math.tan(math.radians(FOV / 2))
PLAYER_Z = CAMERA_HEIGHT * CAMERA_DEPTH
DRAW_DIST = 200

MAX_SPEED = SEG_LEN * 60
ACCEL = MAX_SPEED / 5
BRAKE = -MAX_SPEED
DECEL = -MAX_SPEED / 5
OFFROAD_DECEL = -MAX_SPEED / 2
OFFROAD_LIMIT = MAX_SPEED / 4
CENTRIFUGAL = 0.3
CAR_FRAC = 0.26

START_TIME = 70
LAP_BONUS = 45
COIN_TIME = 0.5
COIN_SCORE = 100

SKY_TOP = (38, 22, 84)
FOG = (255, 154, 96)
GRASS = ((78, 170, 72), (66, 152, 62))
RUMBLE = ((220, 60, 60), (245, 245, 245))
ROAD = ((112, 112, 120), (104, 104, 112))
LANE_C = (232, 232, 232)
START_C = (240, 240, 240)
WHITE = (255, 255, 255)
GOLD = (250, 199, 117)
GOLD_EDGE = (186, 117, 23)
RED = (226, 75, 74)

PLAYER_BODY = (24, 95, 165)
PLAYER_GLASS = (181, 212, 244)
TRAFFIC_COLORS = [
    (226, 75, 74),
    (239, 159, 39),
    (127, 119, 221),
    (29, 158, 117),
    (212, 83, 126),
    (225, 225, 232),
]

LANE_OFFSETS = (-0.55, 0.0, 0.55)
LANE_SPEEDS = (0.30, 0.40, 0.35)


def lerp(a, b, t):
    return a + (b - a) * t


def ease_in(a, b, p):
    return a + (b - a) * p * p


def ease_out(a, b, p):
    return a + (b - a) * (1 - (1 - p) ** 2)


def ease_in_out(a, b, p):
    return a + (b - a) * (-math.cos(p * math.pi) / 2 + 0.5)


def clamp(v, lo, hi):
    return max(lo, min(hi, v))


def mix_color(a, b, t):
    return (
        int(a[0] + (b[0] - a[0]) * t),
        int(a[1] + (b[1] - a[1]) * t),
        int(a[2] + (b[2] - a[2]) * t),
    )


def shade(c, f):
    return (int(c[0] * f), int(c[1] * f), int(c[2] * f))


def build_fog_tables():
    table, start, mixes = [], [], []
    for n in range(DRAW_DIST):
        mix = 1 - math.exp(-((n / DRAW_DIST) ** 2) * 4.0)

        def f(c):
            return mix_color(c, FOG, mix)

        light = (f(GRASS[0]), f(RUMBLE[0]), f(ROAD[0]), f(LANE_C))
        dark = (f(GRASS[1]), f(RUMBLE[1]), f(ROAD[1]), f(LANE_C))
        table.append((light, dark))
        start.append(f(START_C))
        mixes.append(mix)
    return table, start, mixes


FOG_COLORS, FOG_START, FOG_MIX = build_fog_tables()


class Point:
    __slots__ = ("y", "z", "cz", "scale", "sx", "sy", "sw")

    def __init__(self, y, z):
        self.y = y
        self.z = z
        self.cz = 0.0
        self.scale = 0.0
        self.sx = self.sy = self.sw = 0

    def project(self, cam_x, cam_y, cam_z):
        self.cz = self.z - cam_z
        if self.cz <= 0.001:
            self.scale = 0.0
            self.sx = self.sy = self.sw = 0
            return
        self.scale = CAMERA_DEPTH / self.cz
        self.sx = round(WIDTH / 2 + self.scale * (-cam_x) * WIDTH / 2)
        self.sy = round(HEIGHT / 2 - self.scale * (self.y - cam_y) * HEIGHT / 2)
        self.sw = round(self.scale * ROAD_W * WIDTH / 2)


class Segment:
    __slots__ = ("index", "p1", "p2", "curve", "dark", "cars", "coins", "trees", "clip", "start")

    def __init__(self, index, y1, y2, curve):
        self.index = index
        self.p1 = Point(y1, index * SEG_LEN)
        self.p2 = Point(y2, (index + 1) * SEG_LEN)
        self.curve = curve
        self.dark = (index // RUMBLE_LEN) % 2 == 1
        self.cars = []
        self.coins = []
        self.trees = []
        self.clip = HEIGHT
        self.start = False


class Car:
    __slots__ = ("z", "offset", "speed", "color")

    def __init__(self, z, offset, speed, color):
        self.z = z
        self.offset = offset
        self.speed = speed
        self.color = color


class Coin:
    __slots__ = ("offset", "phase")

    def __init__(self, offset):
        self.offset = offset
        self.phase = random.uniform(0, 6.28)


class Track:
    SHORT, MEDIUM, LONG = 10, 20, 40
    EASY, MID, HARD = 2, 4, 6
    LOW, MED_H, HIGH = 15, 30, 45

    def __init__(self):
        self.segments = []
        self.build()
        self.count = len(self.segments)
        self.length = self.count * SEG_LEN
        for i in range(3):
            self.segments[i].start = True
        self.decorate()

    def last_y(self):
        return self.segments[-1].p2.y if self.segments else 0.0

    def add_segment(self, curve, y):
        n = len(self.segments)
        self.segments.append(Segment(n, self.last_y(), y, curve))

    def add_road(self, enter, hold, leave, curve, hill):
        start_y = self.last_y()
        end_y = start_y + hill * SEG_LEN
        total = enter + hold + leave
        for n in range(enter):
            self.add_segment(
                ease_in(0, curve, n / enter), ease_in_out(start_y, end_y, n / total)
            )
        for n in range(hold):
            self.add_segment(curve, ease_in_out(start_y, end_y, (enter + n) / total))
        for n in range(leave):
            self.add_segment(
                ease_out(curve, 0, n / leave),
                ease_in_out(start_y, end_y, (enter + hold + n) / total),
            )

    def road(self, num, curve=0, hill=0):
        self.add_road(num, num, num, curve, hill)

    def rolling_hills(self, num=None, height=None):
        num = num or self.SHORT
        h = height or self.LOW
        self.road(num, 0, h / 2)
        self.road(num, 0, -h)
        self.road(num, self.EASY, h)
        self.road(num, 0, 0)
        self.road(num, -self.EASY, h / 2)
        self.road(num, 0, 0)

    def s_curves(self):
        m = self.MEDIUM
        self.road(m, -self.EASY, 0)
        self.road(m, self.MID, -self.LOW)
        self.road(m, self.EASY, self.LOW)
        self.road(m, -self.EASY, self.LOW)
        self.road(m, -self.MID, -self.LOW)

    def bumps(self):
        for h in (5, -2, -5, 8, 5, -7, 5, -2):
            self.road(5, 0, h)

    def build(self):
        S, M, L = self.SHORT, self.MEDIUM, self.LONG
        self.road(S)
        self.rolling_hills()
        self.s_curves()
        self.road(M, self.MID, self.LOW)
        self.bumps()
        self.rolling_hills()
        self.road(L, self.MID, self.MED_H)
        self.road(M)
        self.road(M, 0, self.HIGH)
        self.road(L, -self.MID, 0)
        self.road(L, 0, self.HIGH)
        self.road(L, self.MID, -self.LOW)
        self.bumps()
        self.road(L, 0, -self.MED_H - self.HIGH)
        self.road(M)
        self.s_curves()
        hill = -self.last_y() / SEG_LEN
        num = max(20, int(abs(hill) / 1.2))
        self.road(num, -self.EASY, hill)

    def find(self, z):
        return self.segments[int(z // SEG_LEN) % self.count]

    def decorate(self):
        rnd = random.Random(7)
        segs = self.segments
        for n in range(8, self.count - 8, 4):
            side = rnd.choice((-1, 1))
            if rnd.random() < 0.75:
                segs[n].trees.append((side * rnd.uniform(1.6, 2.5), rnd.uniform(0.8, 1.25)))
            if rnd.random() < 0.45:
                segs[n].trees.append((-side * rnd.uniform(1.7, 2.8), rnd.uniform(0.8, 1.25)))
            if rnd.random() < 0.35:
                segs[n].trees.append((side * rnd.uniform(3.2, 6.0), rnd.uniform(1.0, 1.5)))

    def populate(self):
        for seg in self.segments:
            seg.cars.clear()
            seg.coins.clear()
        cars = []
        for lane, off in enumerate(LANE_OFFSETS):
            z = random.uniform(6000, 12000)
            while z < self.length - 4000:
                car = Car(
                    z,
                    off + random.uniform(-0.04, 0.04),
                    MAX_SPEED * LANE_SPEEDS[lane],
                    random.choice(TRAFFIC_COLORS),
                )
                self.find(z).cars.append(car)
                cars.append(car)
                z += random.uniform(5000, 14000)
        for n in range(100, self.count - 60, 80):
            off = random.choice(LANE_OFFSETS)
            for k in range(5):
                self.segments[n + k * 3].coins.append(Coin(off))
        return cars


def build_sky():
    sky = pygame.Surface((WIDTH, HEIGHT))
    for y in range(HORIZON + 1):
        t = (y / HORIZON) ** 1.3
        pygame.draw.line(sky, mix_color(SKY_TOP, FOG, t), (0, y), (WIDTH, y))
    pygame.draw.rect(sky, FOG, (0, HORIZON, WIDTH, HEIGHT - HORIZON))
    sun = (int(WIDTH * 0.66), HORIZON - 60)
    pygame.draw.circle(sky, (255, 214, 150), sun, 52)
    pygame.draw.circle(sky, (255, 240, 200), sun, 40)
    return sky


def build_hills(color, amp, ks, phases):
    surf = pygame.Surface((WIDTH, HORIZON + 2), pygame.SRCALPHA)
    pts = [(0, HORIZON)]
    for x in range(0, WIDTH + 1, 6):
        a = 2 * math.pi * x / WIDTH
        v = (
            0.55 * math.sin(a * ks[0] + phases[0])
            + 0.30 * math.sin(a * ks[1] + phases[1])
            + 0.15 * math.sin(a * ks[2] + phases[2])
        )
        pts.append((x, HORIZON - amp * (0.55 + 0.45 * v)))
    pts.append((WIDTH, HORIZON))
    pygame.draw.polygon(surf, color, pts)
    return surf


def poly(surf, color, x1, y1, w1, x2, y2, w2):
    pygame.draw.polygon(
        surf, color, ((x1 - w1, y1), (x2 - w2, y2), (x2 + w2, y2), (x1 + w1, y1))
    )


def draw_car_rear(surf, cx, by, w, body, glass, light, fog=0.0, lean=0.0):
    if w < 3:
        return
    h = w * 0.62

    def c(col):
        return mix_color(col, FOG, fog) if fog > 0.03 else col

    x0 = cx - w / 2
    dark = shade(body, 0.72)
    if w < 10:
        pygame.draw.rect(surf, c(body), (int(x0), int(by - h), max(1, int(w)), max(1, int(h))))
        return
    pygame.draw.ellipse(
        surf, c((44, 44, 54)), (int(x0 - w * 0.04), int(by - h * 0.14), int(w * 1.08), max(2, int(h * 0.28)))
    )
    ww, wh = max(2, int(w * 0.17)), max(2, int(h * 0.34))
    for wx in (x0 + w * 0.02, x0 + w * 0.81):
        pygame.draw.rect(surf, c((28, 28, 32)), (int(wx), int(by - wh), ww, wh), border_radius=max(1, ww // 4))
    body_h = h * 0.5
    body_top = by - h * 0.14 - body_h
    pygame.draw.rect(
        surf, c(body), (int(x0), int(body_top), int(w), int(body_h)), border_radius=max(1, int(w * 0.08))
    )
    shift = lean * w * 0.03
    cabin = [
        (x0 + w * 0.15, body_top + h * 0.03),
        (x0 + w * 0.25 + shift, by - h),
        (x0 + w * 0.75 + shift, by - h),
        (x0 + w * 0.85, body_top + h * 0.03),
    ]
    pygame.draw.polygon(surf, c(dark), cabin)
    win = [
        (x0 + w * 0.2, body_top),
        (x0 + w * 0.29 + shift, by - h * 0.93),
        (x0 + w * 0.71 + shift, by - h * 0.93),
        (x0 + w * 0.80, body_top),
    ]
    pygame.draw.polygon(surf, c(glass), win)
    ly = body_top + body_h * 0.28
    lh = max(2, int(h * 0.11))
    lw = max(2, int(w * 0.24))
    for lx in (x0 + w * 0.05, x0 + w * 0.71):
        pygame.draw.rect(surf, c(light), (int(lx), int(ly), lw, lh))
    pygame.draw.rect(
        surf, c(dark), (int(x0 + w * 0.02), int(by - h * 0.25), int(w * 0.96), max(2, int(h * 0.09)))
    )


def draw_tree(surf, cx, by, w, h, fog):
    if h < 3:
        return

    def c(col):
        return mix_color(col, FOG, fog) if fog > 0.03 else col

    if h < 16:
        pygame.draw.polygon(
            surf, c((36, 116, 66)), ((cx - w * 0.45, by), (cx, by - h), (cx + w * 0.45, by))
        )
        return
    tw = max(2, int(w * 0.14))
    th = h * 0.22
    pygame.draw.rect(surf, c((92, 62, 40)), (int(cx - tw / 2), int(by - th), tw, int(th)))
    tiers = (
        ((28, 98, 58), 0.0, 0.42, 0.30),
        ((36, 116, 66), 0.2, 0.42, 0.42),
        ((46, 134, 76), 0.4, 0.5, 0.5),
    )
    for col, top_f, hgt_f, half_f in tiers:
        apex = by - h + h * top_f
        base = apex + h * hgt_f
        pygame.draw.polygon(
            surf, c(col), ((cx - w * half_f, base), (cx, apex), (cx + w * half_f, base))
        )


class Game:
    def __init__(self):
        pygame.init()
        pygame.display.set_caption("Машина гонкасы 3D")
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT))
        self.clock = pygame.time.Clock()
        names = "arial,dejavusans,freesans,liberationsans,verdana"
        self.f_small = pygame.font.SysFont(names, 16)
        self.f_mid = pygame.font.SysFont(names, 26, bold=True)
        self.f_big = pygame.font.SysFont(names, 42, bold=True)
        self.f_huge = pygame.font.SysFont(names, 96, bold=True)
        self.sky = build_sky()
        self.far_hills = build_hills((124, 66, 122), 90, (2, 5, 9), (0.4, 1.7, 2.9))
        self.near_hills = build_hills((88, 46, 100), 52, (3, 7, 13), (2.1, 0.6, 1.3))
        self.track = Track()
        self.best = 0
        self.state = "menu"
        self.t = 0.0
        self.reset()

    def reset(self):
        self.cars = self.track.populate()
        self.position = 0.0
        self.distance = 0.0
        self.laps_done = 0
        self.player_x = 0.0
        self.speed = 0.0
        self.score = 0.0
        self.coin_count = 0
        self.time_left = float(START_TIME)
        self.countdown = 3.0
        self.go_timer = 0.0
        self.invincible = 0.0
        self.flash = 0.0
        self.lean = 0.0
        self.far_off = 0.0
        self.near_off = 0.0
        self.banner = ""
        self.banner_t = 0.0
        self.braking = False

    def quit(self):
        pygame.quit()
        sys.exit()

    def say(self, msg, secs=2.0):
        self.banner = msg
        self.banner_t = secs

    def crash(self, speed, new_pos):
        tl = self.track.length
        delta = ((new_pos - self.position + tl / 2) % tl) - tl / 2
        self.distance += delta
        self.position = new_pos % tl
        self.speed = speed
        self.invincible = 1.3
        self.flash = 0.35

    def update(self, dt):
        if self.countdown > 0:
            self.countdown -= dt
            if self.countdown <= 0:
                self.go_timer = 0.8
            return
        if self.go_timer > 0:
            self.go_timer -= dt

        keys = pygame.key.get_pressed()
        left = keys[pygame.K_LEFT] or keys[pygame.K_a]
        right = keys[pygame.K_RIGHT] or keys[pygame.K_d]
        gas = keys[pygame.K_UP] or keys[pygame.K_w]
        brake = keys[pygame.K_DOWN] or keys[pygame.K_s]
        self.braking = bool(brake)

        track = self.track
        tl = track.length
        step = self.speed * dt
        self.position = (self.position + step) % tl
        self.distance += step
        pz = self.position + PLAYER_Z
        seg = track.find(pz)

        sp = self.speed / MAX_SPEED
        dx = dt * 2 * sp
        if left:
            self.player_x -= dx
        if right:
            self.player_x += dx
        self.player_x -= dx * sp * seg.curve * CENTRIFUGAL

        if gas:
            self.speed += ACCEL * dt
        elif brake:
            self.speed += BRAKE * dt
        else:
            self.speed += DECEL * dt
        if abs(self.player_x) > 1 and self.speed > OFFROAD_LIMIT:
            self.speed += OFFROAD_DECEL * dt
        self.speed = clamp(self.speed, 0, MAX_SPEED)
        self.player_x = clamp(self.player_x, -2.5, 2.5)

        target = -1.0 if left else (1.0 if right else 0.0)
        self.lean += (target - self.lean) * min(1.0, dt * 10)

        if self.invincible > 0:
            self.invincible -= dt
        elif abs(self.player_x) > 1:
            idx = int(pz // SEG_LEN)
            hit = False
            for k in range(0, 2):
                s = track.segments[(idx + k) % track.count]
                for off, _size in s.trees:
                    if abs(self.player_x - off) < 0.42:
                        self.crash(MAX_SPEED * 0.1, s.p1.z - PLAYER_Z - 200)
                        hit = True
                        break
                if hit:
                    break

        if self.invincible <= 0:
            self.check_cars(self.position + PLAYER_Z)

        self.update_traffic(dt)
        self.collect_coins(self.position + PLAYER_Z)

        self.score += self.speed * dt * 0.01
        self.time_left -= dt

        laps = int((self.distance + PLAYER_Z) // tl)
        if laps > self.laps_done:
            self.laps_done = laps
            self.time_left += LAP_BONUS
            self.score += 500
            self.say(f"Тур {laps} бүттү!  +{LAP_BONUS} сек", 2.2)

        curve = track.find(self.position + PLAYER_Z).curve
        adv = step / SEG_LEN
        self.far_off = (self.far_off + 0.0006 * curve * adv * WIDTH) % WIDTH
        self.near_off = (self.near_off + 0.0012 * curve * adv * WIDTH) % WIDTH

        if self.flash > 0:
            self.flash -= dt
        if self.banner_t > 0:
            self.banner_t -= dt

        if self.time_left <= 0:
            self.time_left = 0
            self.best = max(self.best, int(self.score))
            self.state = "over"

    def check_cars(self, pz):
        track = self.track
        tl = track.length
        idx = int(pz // SEG_LEN)
        for k in range(-1, 3):
            seg = track.segments[(idx + k) % track.count]
            for car in seg.cars:
                if self.speed <= car.speed:
                    continue
                dz = ((car.z - pz + tl / 2) % tl) - tl / 2
                if -150 < dz < 350 and abs(self.player_x - car.offset) < CAR_FRAC:
                    self.crash(car.speed * 0.5, car.z - PLAYER_Z - 450)
                    return

    def update_traffic(self, dt):
        track = self.track
        tl = track.length
        for car in self.cars:
            old = track.find(car.z)
            car.z = (car.z + car.speed * dt) % tl
            new = track.find(car.z)
            if new is not old:
                old.cars.remove(car)
                new.cars.append(car)

    def collect_coins(self, pz):
        track = self.track
        tl = track.length
        idx = int(pz // SEG_LEN)
        for k in range(-1, 2):
            seg = track.segments[(idx + k) % track.count]
            if not seg.coins:
                continue
            z = seg.p1.z + SEG_LEN / 2
            dz = ((z - pz + tl / 2) % tl) - tl / 2
            if abs(dz) > SEG_LEN * 0.9:
                continue
            for coin in seg.coins[:]:
                if abs(coin.offset - self.player_x) < 0.3:
                    seg.coins.remove(coin)
                    self.coin_count += 1
                    self.score += COIN_SCORE
                    self.time_left += COIN_TIME

    def handle_event(self, event):
        if event.type == pygame.QUIT:
            self.quit()
        if event.type != pygame.KEYDOWN:
            return
        if event.key == pygame.K_ESCAPE:
            self.quit()
        if self.state == "menu":
            if event.key in (pygame.K_SPACE, pygame.K_RETURN):
                self.reset()
                self.state = "play"
        elif self.state == "play":
            if event.key == pygame.K_p:
                self.state = "pause"
        elif self.state == "pause":
            if event.key in (pygame.K_p, pygame.K_SPACE):
                self.state = "play"
        elif self.state == "over":
            if event.key in (pygame.K_r, pygame.K_SPACE, pygame.K_RETURN):
                self.reset()
                self.state = "play"

    def draw_background(self):
        s = self.screen
        s.blit(self.sky, (0, 0))
        for layer, off in ((self.far_hills, self.far_off), (self.near_hills, self.near_off)):
            ox = int(off)
            s.blit(layer, (-ox, 0))
            s.blit(layer, (WIDTH - ox, 0))

    def draw_segment(self, seg, n):
        p1, p2 = seg.p1, seg.p2
        grass_c, rumble_c, road_c, lane_c = FOG_COLORS[n][1 if seg.dark else 0]
        if seg.start:
            road_c = FOG_START[n]
        s = self.screen
        pygame.draw.rect(s, grass_c, (0, p2.sy, WIDTH, p1.sy - p2.sy))
        poly(s, rumble_c, p1.sx, p1.sy, p1.sw * 1.17, p2.sx, p2.sy, p2.sw * 1.17)
        poly(s, road_c, p1.sx, p1.sy, p1.sw, p2.sx, p2.sy, p2.sw)
        if not seg.dark and not seg.start:
            lw1 = p1.sw * 2 / LANES
            lw2 = p2.sw * 2 / LANES
            lx1 = p1.sx - p1.sw + lw1
            lx2 = p2.sx - p2.sw + lw2
            for _ in range(1, LANES):
                poly(s, lane_c, lx1, p1.sy, p1.sw / 64, lx2, p2.sy, p2.sw / 64)
                lx1 += lw1
                lx2 += lw2

    def draw_road(self):
        track = self.track
        segs = track.segments
        count = track.count
        base = track.find(self.position)
        base_pct = (self.position % SEG_LEN) / SEG_LEN
        pz = self.position + PLAYER_Z
        pseg = track.find(pz)
        ppct = (pz % SEG_LEN) / SEG_LEN
        cam_y = lerp(pseg.p1.y, pseg.p2.y, ppct) + CAMERA_HEIGHT

        max_y = HEIGHT
        x = 0.0
        dx = -(base.curve * base_pct)
        for n in range(DRAW_DIST):
            seg = segs[(base.index + n) % count]
            looped = seg.index < base.index
            cam_z = self.position - (track.length if looped else 0)
            seg.p1.project(self.player_x * ROAD_W - x, cam_y, cam_z)
            seg.p2.project(self.player_x * ROAD_W - x - dx, cam_y, cam_z)
            x += dx
            dx += seg.curve
            seg.clip = max_y
            if (
                seg.p1.cz <= CAMERA_DEPTH
                or seg.p2.sy >= seg.p1.sy
                or seg.p2.sy >= max_y
            ):
                continue
            self.draw_segment(seg, n)
            max_y = seg.p1.sy

        s = self.screen
        for n in range(DRAW_DIST - 1, 0, -1):
            seg = segs[(base.index + n) % count]
            if not (seg.cars or seg.coins or seg.trees):
                continue
            p1, p2 = seg.p1, seg.p2
            if p1.cz <= CAMERA_DEPTH:
                continue
            fog = FOG_MIX[n]
            s.set_clip((0, 0, WIDTH, max(0, int(seg.clip))))
            for off, size in seg.trees:
                tx = p1.sx + p1.sw * off
                draw_tree(s, tx, p1.sy, p1.sw * 0.85 * size, p1.sw * 1.4 * size, fog)
            for coin in seg.coins:
                mid_x = (p1.sx + p2.sx) / 2
                mid_y = (p1.sy + p2.sy) / 2
                sw = (p1.sw + p2.sw) / 2
                r = max(2, sw * 0.055)
                cx = mid_x + sw * coin.offset
                cy = mid_y - r * 2.4
                spin = abs(math.cos(self.t * 6 + coin.phase))
                rw = max(1, r * (0.25 + 0.75 * spin))
                rect = pygame.Rect(int(cx - rw), int(cy - r), max(2, int(rw * 2)), max(2, int(r * 2)))
                pygame.draw.ellipse(s, mix_color(GOLD, FOG, fog), rect)
                pygame.draw.ellipse(s, mix_color(GOLD_EDGE, FOG, fog), rect, max(1, int(r * 0.25)))
            for car in seg.cars:
                pct = (car.z % SEG_LEN) / SEG_LEN
                sx = lerp(p1.sx, p2.sx, pct)
                sy = lerp(p1.sy, p2.sy, pct)
                sw = lerp(p1.sw, p2.sw, pct)
                cx = sx + sw * car.offset
                draw_car_rear(
                    s, cx, sy, sw * CAR_FRAC * 2, car.color,
                    mix_color(car.color, (230, 240, 250), 0.6), (235, 55, 55), fog,
                )
            s.set_clip(None)

    def draw_player(self):
        if self.invincible > 0 and int(self.invincible * 12) % 2 == 0:
            return
        sp = self.speed / MAX_SPEED
        bounce = 0.0
        if self.speed > 0 and self.countdown <= 0:
            shake = 1.2 if abs(self.player_x) <= 1 else 4.0
            bounce = random.uniform(-1, 1) * sp * shake
        light = (255, 40, 40) if self.braking else (200, 40, 40)
        draw_car_rear(
            self.screen, WIDTH // 2 + self.lean * 4, HEIGHT - 16 + bounce,
            WIDTH * CAR_FRAC, PLAYER_BODY, PLAYER_GLASS, light, 0.0, self.lean,
        )

    def text(self, font, msg, color, center=None, topleft=None, topright=None, shadow=True):
        img = font.render(msg, True, color)
        rect = img.get_rect()
        if center:
            rect.center = center
        elif topleft:
            rect.topleft = topleft
        elif topright:
            rect.topright = topright
        if shadow:
            dark = font.render(msg, True, (0, 0, 0))
            self.screen.blit(dark, rect.move(2, 2))
        self.screen.blit(img, rect)

    def panel(self, x, y, w, h):
        p = pygame.Surface((w, h), pygame.SRCALPHA)
        pygame.draw.rect(p, (0, 0, 0, 120), (0, 0, w, h), border_radius=10)
        self.screen.blit(p, (x, y))

    def draw_hud(self):
        t = max(0, int(math.ceil(self.time_left)))
        low = self.time_left < 10
        self.panel(16, 14, 150, 66)
        self.text(self.f_small, "Убакыт", (210, 210, 215), topleft=(28, 20), shadow=False)
        self.text(self.f_big, str(t), RED if low else WHITE, topleft=(28, 36), shadow=False)

        self.panel(WIDTH // 2 - 100, 14, 200, 66)
        self.text(self.f_small, "Упай", (210, 210, 215), center=(WIDTH // 2, 30), shadow=False)
        self.text(self.f_big, str(int(self.score)), WHITE, center=(WIDTH // 2, 56), shadow=False)

        self.panel(WIDTH - 186, 14, 170, 66)
        self.text(self.f_mid, f"Тур {self.laps_done + 1}", WHITE, topleft=(WIDTH - 172, 20), shadow=False)
        self.text(self.f_small, f"Тыйын: {self.coin_count}", GOLD, topleft=(WIDTH - 172, 54), shadow=False)

        self.panel(16, HEIGHT - 86, 210, 70)
        kmh = int(self.speed / MAX_SPEED * 300)
        self.text(self.f_big, f"{kmh}", WHITE, topleft=(28, HEIGHT - 82), shadow=False)
        self.text(self.f_small, "км/с", (210, 210, 215), topleft=(112, HEIGHT - 62), shadow=False)
        bar = int(180 * self.speed / MAX_SPEED)
        pygame.draw.rect(self.screen, (60, 60, 66), (28, HEIGHT - 32, 180, 8), border_radius=4)
        if bar > 0:
            pygame.draw.rect(
                self.screen, GOLD if bar < 150 else RED, (28, HEIGHT - 32, bar, 8), border_radius=4
            )

    def draw_overlay(self, title, lines):
        veil = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        veil.fill((10, 5, 30, 150))
        self.screen.blit(veil, (0, 0))
        self.text(self.f_big, title, WHITE, center=(WIDTH // 2, HEIGHT // 2 - 110))
        for i, line in enumerate(lines):
            self.text(self.f_mid, line, GOLD, center=(WIDTH // 2, HEIGHT // 2 - 30 + i * 40))

    def draw(self):
        self.draw_background()
        self.draw_road()
        self.draw_player()

        if self.flash > 0:
            fl = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
            fl.fill((255, 60, 40, int(150 * self.flash / 0.35)))
            self.screen.blit(fl, (0, 0))

        if self.state in ("play", "pause", "over"):
            self.draw_hud()
            if self.countdown > 0:
                self.text(self.f_huge, str(int(math.ceil(self.countdown))), WHITE, center=(WIDTH // 2, 210))
            elif self.go_timer > 0:
                self.text(self.f_huge, "ЖӨНӨ!", GOLD, center=(WIDTH // 2, 210))
            if self.banner_t > 0:
                self.text(self.f_big, self.banner, GOLD, center=(WIDTH // 2, 150))

        if self.state == "menu":
            self.draw_overlay(
                "Машина гонкасы 3D",
                [
                    "SPACE - баштоо",
                    "↑ газ,  ↓ тормоз,  ← → бурулуу",
                    "Убакыт бүтпөсүн: тыйын чогулт, турду бүтүр",
                    "P - тыным,  ESC - чыгуу",
                ],
            )
        elif self.state == "pause":
            self.draw_overlay("Тыным", ["P - улантуу"])
        elif self.state == "over":
            self.draw_overlay(
                "Убакыт бүттү",
                [
                    f"Упай: {int(self.score)}",
                    f"Тур: {self.laps_done}   Тыйын: {self.coin_count}",
                    f"Рекорд: {self.best}",
                    "R - кайра баштоо",
                ],
            )
        pygame.display.flip()

    def run(self):
        while True:
            dt = min(self.clock.tick(FPS) / 1000, 0.05)
            self.t += dt
            for event in pygame.event.get():
                self.handle_event(event)
            if self.state == "play":
                self.update(dt)
            self.draw()


if __name__ == "__main__":
    Game().run()
