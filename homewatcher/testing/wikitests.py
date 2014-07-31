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
import homewatcher.testing.base
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

class WikiTestCase(homewatcher.testing.base.TestCaseBase):
    """ Implements tests that ensure the documentation presented in the Wiki Pages is correct. """
    def setUp(self):
        linknxConfFile = self.getResourceFullName('linknx.conf.xml', appendsTestName=False)
        hwConfigFile = self.getResourceFullName('homewatcher.conf.xml', appendsTestName=False)
        homewatcher.testing.base.TestCaseBase.setUp(self, linknxConfFile=linknxConfFile, usesCommunicator=True, hwConfigFile=hwConfigFile)

    def testLightWhenOpeningDoor(self):
        """ Test the configuration sample proposed in the Getting Started page. """
        self.changeAlarmMode('Away', None)
        entranceTrigger = self.linknx.getObject('EntranceDoorTrigger')
        entranceLight = self.linknx.getObject('EntranceLight')
        entranceTrigger.value = False
        self.assertFalse(entranceLight.value)

        self.waitDuring(1, 'Initializing...')

        entranceTrigger.value = True
        self.waitDuring(0.3, 'Opening door...')
        self.assertTrue(entranceLight.value)

if __name__ == '__main__':
    unittest.main()
