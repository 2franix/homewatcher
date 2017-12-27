#!/usr/bin/python3

# Copyright (C) 2014-2017 Cyrille Defranoux
#
# This file is part of Homewatcher.
#
# Homewatcher is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# Homewatcher is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with Homewatcher. If not, see <http://www.gnu.org/licenses/>.
#
# For any question, feature requests or bug reports, feel free to contact me at:
# knx at aminate dot net

from homewatcher import ensurepyknx

from pyknx import logger
import subprocess
import os
import threading
import time

class Timer(threading.Thread):
    def __init__(self, sensor, timeout, name, onTimeoutReached, onIterate = None, onTerminated = None):
        threading.Thread.__init__(self, name=name + ' (id={0})'.format(id(self)))
        self.sensor = sensor
        self.timeout = timeout
        self.reset()
        self.isTerminating = False
        self.isCancelled = False
        self.isTerminated = False # Mainly for unit testing.
        self.onIterate = onIterate
        self.onTimeoutReached = onTimeoutReached
        self.onTerminated = onTerminated

    def run(self):
        try:
            logger.reportDebug('Starting {0}'.format(self))
            while not self.isTerminating:
                if self.onIterate is not None: self.onIterate(self)

                # Check for termination.
                if self.isTerminating:
                    return

                # Main loop.
                if not self.isPaused:
                    if self.endTime is None: self.extend(starts=True)
                    if time.time() > self.endTime:
                        # Execute delayed job.
                        logger.reportDebug('Timeout reached for {0}.'.format(self))
                        if callable(self.onTimeoutReached): self.onTimeoutReached(self)
                        break

                time.sleep(0.2)
        finally:
            if self.isTerminating:
                # Timer has been stopped from outside.
                logger.reportDebug('{0} is canceled.'.format(self))
            else:
                # Maybe useless but set it for consistency.
                self.isTerminating = True
            if callable(self.onTerminated): self.onTerminated(self)
            logger.reportDebug('{0} is now terminated.'.format(self))
            self.isTerminated = True
            self.isTerminating = False

    def forceTimeout(self):
        logger.reportDebug('Forcing timeout of {0}'.format(self))
        self.endTime = 0

    def pause(self):
        self.isPaused = True

    def stop(self):
        if not self.isCancelled:
            self.isCancelled = True
            self.isTerminating = True
            logger.reportDebug('Cancelling {0}.'.format(self))

    def reset(self):
        self.endTime = None
        self.isPaused = False

    def __str__(self):
        return '{0} => {1} id={2}'.format(self.sensor, self.name, id(self))

    def extend(self, starts = False):
        """ Prolong duration by the timeout amount of time. """
        if self.isTerminating:
            raise Exception('Timer {0} is terminating, it cannot be extended.'.format(self))
        self.endTime = time.time() + self.timeout
        if starts:
            logger.reportDebug('{0} started for {1} seconds.'.format(self, self.timeout))
        else:
            logger.reportDebug('{0} is extended by {1} seconds.'.format(self, self.timeout))
