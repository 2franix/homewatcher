#!/usr/bin/python3
# coding=utf-8

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
