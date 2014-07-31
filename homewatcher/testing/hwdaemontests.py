#!/usr/bin/python3

# Copyright (C) 2014 Cyrille Defranoux
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

import sys
from pyknx import logger, linknx, configurator
from pyknx.communicator import Communicator
from homewatcher import configuration
from homewatcher.testing import base
import logging
import test
from homewatcher.sensor import *
from homewatcher.alarm import *
import os.path
import subprocess
import unittest
import time
import traceback
import tempfile
import inspect
import stat
import pwd, grp
import shutil

class HWDaemonTestCase(base.TestCaseBase):
    def testNoOption(self):
        self.assertShellCommand(['../../hwdaemon.py'], 'resources/HWDaemonTestCase.testNoOption.out', 'resources/HWDaemonTestCase.testNoOption.err')

    def testHelp(self):
        self.assertShellCommand(['../../hwdaemon.py', '-h'], 'resources/HWDaemonTestCase.testHelp.out')

if __name__ == '__main__':
    unittest.main()
