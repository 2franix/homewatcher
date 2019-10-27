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

import sys
sys.path.append('../')
from pyknx import logger, linknx, configurator
from pyknx.communicator import Communicator
from homewatcher import configuration
from homewatcher.testing import base
import logging
from homewatcher.sensor import *
from homewatcher.alarm import *
import os.path
import subprocess
import unittest
import time
import traceback
import inspect
import stat
import pwd, grp
import shutil
import xml.dom.minidom as xdm

class ActionTestCase(base.TestCaseBase):
    class LinknxMock(object):
        def __init__(self):
            self.actionXml = None
        def executeAction(self, actionXml):
            self.actionXml = actionXml

    class DaemonMock(object):
        def __init__(self):
            self.linknx = ActionTestCase.LinknxMock()

    def setUp(self):
        base.TestCaseBase.setUp(self, linknxConfFile=None, usesCommunicator=False)

    def testShellCommandAction(self):
        logger.reportInfo('\n\n*********INITIALIZE testShellCommandAction********************')

        # Configure action.
        actionConfigXml = xdm.parseString('<action type="shell-cmd"><cmd>fooCommand &quot;argument1&quot;</cmd></action>')
        actionConfig = configuration.Action.fromXML(actionConfigXml.getElementsByTagName('action')[0])

        # Mock daemon.
        daemonMock = ActionTestCase.DaemonMock()

        # Create action and execute it.
        action = ShellCommandAction(daemonMock, actionConfig)
        action.execute(None)

        self.assertEqual('<?xml version="1.0" ?><action cmd="fooCommand &quot;argument1&quot;" type="shell-cmd"/>', daemonMock.linknx.actionXml.toxml())

if __name__ == '__main__':
    unittest.main()
