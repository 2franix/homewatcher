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

class HWConfTestCase(homewatcher.testing.base.TestCaseBase):
	def setUp(self):
		homewatcher.testing.base.TestCaseBase.setUp(self, usesLinknx=False, usesCommunicator=False)
		self.hwConfPyFile = os.path.join(self.homewatcherScriptsDirectory, 'hwconf.py')

	def testNoOption(self):
		self.assertShellCommand([self.hwConfPyFile], 'resources/HWConfTestCase.testNoOption.out', 'resources/HWConfTestCase.testNoOption.err')

	def testGeneratedConfiguration(self):
		inputHWConfig = 'homewatcher_test_conf.xml'
		inputLinknxConfig = 'linknx_test_conf.xml'
		expectedOutput = self.getResourceFullName('outputConfig')

		# Read from file, output to stdout.
		outputWithConfig = self.getResourceFullName('outWithConfig')
		self.assertShellCommand([self.hwConfPyFile, '-v', 'error', '-i', inputHWConfig, inputLinknxConfig], outputWithConfig)

		# Read from file, output to file.
		outputFile = self.getOutputFullName('outputConfig')
		self.assertShellCommand([self.hwConfPyFile, '-i', inputHWConfig, '-o', outputFile, inputLinknxConfig])
		self.assertFilesAreEqual(outputFile, expectedOutput)

		# Read from stdin, output to stdout.
		with open(inputHWConfig, 'r') as input:
			self.assertShellCommand([self.hwConfPyFile, '-v', 'error', inputLinknxConfig], outputWithConfig, stdin=input)

		# Read from stdin, output to file.
		with open(inputHWConfig, 'r') as input:
			self.assertShellCommand([self.hwConfPyFile, '-o', outputFile, inputLinknxConfig], stdin=input)
		self.assertFilesAreEqual(outputFile, expectedOutput)

if __name__ == '__main__':
	unittest.main()
