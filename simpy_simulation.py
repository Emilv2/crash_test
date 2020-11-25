import math
from random import normalvariate, seed

import numpy as np
import simpy


def format_straight_line_plot(data):
    previous = data[0][1]
    result = []
    for time, value in data:
        result.append((time - np.spacing(time), previous))
        result.append((time, value))
        previous = value
    return result


class RO:
    def __init__(self, env, period, jitter, out_pipe, verbose=False):
        self.env = env
        self.state = True
        self.jitter = jitter
        self.period = period
        self.half_period = period / 2
        self.frequency = 1 / period
        self.out_pipe = out_pipe
        self.data = []
        self.verbose = verbose

    def run(self):
        if self.out_pipe:
            yield self.env.timeout(self.period / 4)
        while True:
            yield self.env.timeout(
                self.half_period + normalvariate(0, self.jitter * math.sqrt(2) / 2)
            )
            self.state = not self.state
            if self.out_pipe:
                self.out_pipe.put(self.state)
            if self.verbose:
                self.data.append((self.env.now, self.state))


class FF:
    def __init__(self, env, i_clk_pipe, i_data, o_beat_pipe, verbose=False):
        self.env = env
        self.i_clk_pipe = i_clk_pipe
        self.i_data = i_data
        self.o_beat_pipe = o_beat_pipe
        self.state = False
        self.old_state = False
        self.data = []
        self.verbose = verbose

    def run(self):
        while True:
            if (yield self.i_clk_pipe.get()):
                self.old_state = self.state
                self.state = self.i_data.state
                if self.verbose:
                    self.data.append((self.env.now, self.state))
                self.o_beat_pipe.put(self.state)


class Counter:
    def __init__(self, env, i_clk_pipe, i_rst, o_Q_pipe, verbose=False):
        self.env = env
        self.i_clk_pipe = i_clk_pipe
        self.i_rst = i_rst
        self.o_Q_pipe = o_Q_pipe
        self.count = 0
        self.data = []
        self.count_max = []
        self.avg = 0
        self.n = 1
        self.verbose = verbose
        self.old_state = False

    @property
    def state(self):
        return self.count % 2

    def run(self):
        while True:
            # if rising_edge(i_clk)
            if (yield self.i_clk_pipe.get()):
                # wait a little bit for randout to catch the value
                yield self.env.timeout(1e-15)
                if self.verbose:
                    self.data.append((self.env.now, self.count))
                self.o_Q_pipe.put(self.count)
                if self.i_rst.state and not self.old_state:
                    self.avg = self.avg + (self.count - self.avg) / self.n
                    self.n = self.n + 1
                    self.count_max.append(self.count)
                    self.count = 0
                else:
                    self.count = self.count + 1
                self.old_state = self.i_rst.state


class RandOut:
    def __init__(self, env, i_clk_pipe, i_Q, verbose=False):
        self.env = env
        self.i_clk_pipe = i_clk_pipe
        self.i_Q = i_Q
        self.data = []
        self.old_i_clk = False
        self.verbose = verbose

    def run(self):
        while True:
            # if rising_edge(i_clk)
            i_clk = yield self.i_clk_pipe.get()
            if i_clk and not self.old_i_clk:
                if self.verbose:
                    self.data.append((self.env.now, self.i_Q.state))
                else:
                    self.data.append(self.i_Q.state)
            self.old_i_clk = i_clk


class TRNG:
    def __init__(self, period, delta, jitter1, jitter2, verbose=False):
        self.env = simpy.Environment()
        self.period = period
        self.delta = delta
        self.jitter1 = jitter1
        self.jitter2 = jitter2

        self.ro2_bc_pipe = BroadcastPipe(self.env)
        self.beat_bc_pipe = BroadcastPipe(self.env)
        self.counter_pipe = simpy.Store(self.env)
        self.q_pipe = simpy.Store(self.env)
        self.out_pipe = simpy.Store(self.env)

        self.ro1 = RO(self.env, self.period, self.jitter1, None, verbose=verbose)
        self.ro2 = RO(
            self.env,
            self.period + self.delta,
            self.jitter2,
            self.ro2_bc_pipe,
            verbose=verbose,
        )
        self.beat_ff = FF(
            self.env,
            self.ro2_bc_pipe.get_output_conn(),
            self.ro1,
            self.beat_bc_pipe,
            verbose=verbose,
        )
        self.counter = Counter(
            self.env,
            self.ro2_bc_pipe.get_output_conn(),
            self.beat_ff,
            self.q_pipe,
            verbose=verbose,
        )

        self.rand_out = RandOut(
            self.env, self.beat_bc_pipe.get_output_conn(), self.counter, verbose=verbose
        )

        self.ro1_proc = self.env.process(self.ro1.run())
        self.ro2_proc = self.env.process(self.ro2.run())
        self.beat_ff_proc = self.env.process(self.beat_ff.run())
        self.counter_proc = self.env.process(self.counter.run())
        self.rand_out_proc = self.env.process(self.rand_out.run())
        self.data = []

    @property
    def sigma(self):
        return (
            # ignore first count value because it's incomplete
            np.std(self.counter.count_max[1:])
            * self.delta
            / np.sqrt(2 * self.period / self.delta)
        )


class BroadcastPipe(object):
    """A Broadcast pipe that allows one process to send messages to many.

    This construct is useful when message consumers are running at
    different rates than message generators and provides an event
    buffering to the consuming processes.

    The parameters are used to create a new
    :class:`~simpy.resources.store.Store` instance each time
    :meth:`get_output_conn()` is called.

    source:
    https://simpy.readthedocs.io/en/latest/examples/process_communication.html

    """

    def __init__(self, env, capacity=simpy.core.Infinity):
        self.env = env
        self.capacity = capacity
        self.pipes = []

    def put(self, value):
        """Broadcast a *value* to all receivers."""
        if not self.pipes:
            raise RuntimeError("There are no output pipes.")
        events = [store.put(value) for store in self.pipes]
        return self.env.all_of(events)  # Condition event for all "events"

    def get_output_conn(self):
        """Get a new output connection for this broadcast pipe.

        The return value is a :class:`~simpy.resources.store.Store`.

        """
        pipe = simpy.Store(self.env, capacity=self.capacity)
        self.pipes.append(pipe)
        return pipe




seed(1)
trng = TRNG(3.79e-9, 10e-12, 10e-12, 10e-12)
trng.env.run(until=5e-3)
