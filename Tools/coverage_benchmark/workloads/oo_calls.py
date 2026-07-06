"""Object-oriented dispatch workload (richards-flavoured).

Polymorphic method calls, attribute access, isinstance checks, and small
state machines: the shape of typical application/framework code.
"""


class Shape:
    def __init__(self, ident):
        self.ident = ident

    def area(self):
        raise NotImplementedError

    def describe(self):
        a = self.area()
        if a > 100.0:
            return 2
        elif a > 10.0:
            return 1
        return 0


class Circle(Shape):
    def __init__(self, ident, r):
        super().__init__(ident)
        self.r = r

    def area(self):
        return 3.14159265 * self.r * self.r


class Rect(Shape):
    def __init__(self, ident, w, h):
        super().__init__(ident)
        self.w = w
        self.h = h

    def area(self):
        return self.w * self.h


class Composite(Shape):
    def __init__(self, ident, children):
        super().__init__(ident)
        self.children = children

    def area(self):
        total = 0.0
        for child in self.children:
            total += child.area()
        return total


class Task:
    def __init__(self, priority, work):
        self.priority = priority
        self.work = work
        self.state = "ready"

    def step(self):
        if self.state == "ready":
            self.state = "running"
            return 1
        elif self.state == "running":
            self.work -= 1
            if self.work <= 0:
                self.state = "done"
            return 2
        return 0


class Scheduler:
    def __init__(self, tasks):
        self.tasks = list(tasks)

    def run(self):
        ticks = 0
        active = self.tasks
        while active:
            next_active = []
            for task in active:
                ticks += task.step()
                if task.state != "done":
                    next_active.append(task)
            active = next_active
        return ticks


def build_shapes(n):
    shapes = []
    for i in range(n):
        kind = i % 3
        if kind == 0:
            shapes.append(Circle(i, (i % 13) * 0.5))
        elif kind == 1:
            shapes.append(Rect(i, i % 7 + 1, i % 11 + 1))
        else:
            shapes.append(Composite(i, shapes[-2:]))
    return shapes


def setup():
    pass


def run():
    checksum = 0
    shapes = build_shapes(150_000)
    for shape in shapes:
        checksum += shape.describe()
        if isinstance(shape, Composite):
            checksum += len(shape.children)
    tasks = [Task(i % 5, i % 17 + 1) for i in range(30_000)]
    checksum += Scheduler(tasks).run()
    return checksum
