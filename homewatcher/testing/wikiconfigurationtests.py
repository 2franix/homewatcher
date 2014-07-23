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

class WikiConfigurationTestCase(homewatcher.testing.base.TestCaseBase):
	""" Implements tests that ensure the documentation presented in the Configuration Reference Guide page is correct. """
	def setUp(self):
		homewatcher.testing.base.TestCaseBase.setUp(self, linknxConfFile=None, usesCommunicator=False)

	def testFullConfigForReferenceGuide(self):
		""" Tests the sample configuration proposed in the Configuration Reference Guide page. """
		configurationFile = self.getResourceFullName('homewatcher.conf.xml')
		config = configuration.Configuration.parseFile(configurationFile)
		config.resolve()
		config.checkIntegrity()

if __name__ == '__main__':
	unittest.main()
