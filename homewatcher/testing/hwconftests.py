#!/usr/bin/python3
# coding=utf-8

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
