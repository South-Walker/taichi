import taichi_lang as ti
import math
import numpy as np
import cv2
import os
import taichi as tc
import matplotlib.pyplot as plt

real = ti.f32
ti.set_default_fp(real)

max_steps = 2048
vis_interval = 64
output_vis_interval = 2
steps = 1024
assert steps * 2 <= max_steps

vis_resolution = 1024

scalar = lambda: ti.var(dt=real)
vec = lambda: ti.Vector(2, dt=real)

loss = scalar()

# ti.cfg.arch = ti.cuda

init_x = vec()
init_v = vec()

x = vec()
v = vec()
impulse = vec()

billiard_layers = 4
n_balls = 1 + (1 + billiard_layers) * billiard_layers // 2
target_ball = n_balls - 1
# target_ball = 0
goal = [0.9, 0.75]
radius = 0.03
elasticity = 0.8


@ti.layout
def place():
  ti.root.dense(ti.l, max_steps).dense(ti.i, n_balls).place(x, v, impulse)
  ti.root.place(init_x, init_v)
  ti.root.place(loss)
  ti.root.lazy_grad()


dt = 0.003
alpha = 0.00000
learning_rate = 0.01


@ti.kernel
def collide(t: ti.i32):
  for i in range(n_balls):
    for j in range(i):
      imp = ti.Vector([0.0, 0.0])
      if i != j:
        dist = x[t, i] - x[t, j]
        dist_norm = dist.norm()
        if dist_norm < 2 * radius:
          dir = ti.Vector.normalized(dist)
          rela_v = v[t, i] - v[t, j]
          projected_v = dir.dot(rela_v)

          if projected_v < 0:
            imp = -(1 + elasticity) * 0.5 * projected_v * dir
      ti.atomic_add(impulse[t + 1, i], imp)
    for j_ in range(n_balls - i - 1):
      j = j_ + i + 1
      imp = ti.Vector([0.0, 0.0])
      if i != j:
        dist = x[t, i] - x[t, j]
        dist_norm = dist.norm()
        if dist_norm < 2 * radius:
          dir = ti.Vector.normalized(dist)
          rela_v = v[t, i] - v[t, j]
          projected_v = dir.dot(rela_v)

          if projected_v < 0:
            imp = -(1 + elasticity) * 0.5 * projected_v * dir
      ti.atomic_add(impulse[t + 1, i], imp)


@ti.kernel
def advance(t: ti.i32):
  for i in range(n_balls):
    v[t, i] = v[t - 1, i] + impulse[t, i]
    x[t, i] = x[t - 1, i] + dt * v[t, i]


@ti.kernel
def compute_loss(t: ti.i32):
  loss[None] = ti.sqr(x[t, target_ball][0] - goal[0]) + ti.sqr(
    x[t, target_ball][1] - goal[1])


@ti.kernel
def initialize():
  x[0, 0] = init_x
  v[0, 0] = init_v


gui = tc.core.GUI("Billiards", tc.Vectori(1024, 1024))


def forward(output=None):
  initialize()

  interval = vis_interval
  if output:
    interval = output_vis_interval
    os.makedirs('billiards/{}/'.format(output), exist_ok=True)

  count = 0
  for i in range(billiard_layers):
    for j in range(i + 1):
      count += 1
      x[0, count] = [i * 2 * radius + 0.5,
                     j * 2 * radius + 0.5 - i * radius * 0.7]

  pixel_radius = int(radius * 1024)

  canvas = gui.get_canvas()
  for t in range(1, steps):
    collide(t - 1)
    advance(t)

    if (t + 1) % interval == 0:
      canvas.clear(0x3C733F)

      canvas.circle(tc.Vector(goal[0], goal[1])).radius(pixel_radius).color(0x00000).finish()

      for i in range(n_balls):
        if i == 0:
          color = 0xCCCCCC
        elif i == n_balls - 1:
          color = 0xF2055C
        else:
          color = 0xF20530

        canvas.circle(tc.Vector(x[t, i][0], x[t, i][1])).radius(
          pixel_radius).color(color).finish()

      gui.update()
      # if output:
      #   cv2.imwrite('billiards/{}/{:04d}.png'.format(output, t), img * 255)

  compute_loss(steps - 1)


@ti.kernel
def clear():
  for t in range(0, max_steps):
    for i in range(0, n_balls):
      impulse[t, i] = ti.Vector([0.0, 0.0])


def main():
  init_x[None] = [0.1, 0.5]
  init_v[None] = [0.3, 0.0]

  for iter in range(200):
    clear()

    with ti.Tape(loss):
      forward()

    print('Iter=', iter, 'Loss=', loss[None])
    for d in range(2):
      init_x[None][d] -= learning_rate * init_x.grad[None][d]
      init_v[None][d] -= learning_rate * init_v.grad[None][d]

  clear()
  # forward('final')


if __name__ == '__main__':
  main()
