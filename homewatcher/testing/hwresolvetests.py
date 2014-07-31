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

class HWResolveTestCase(homewatcher.testing.base.TestCaseBase):
    def setUp(self):
        homewatcher.testing.base.TestCaseBase.setUp(self, linknxConfFile=None, usesCommunicator=False)
        self.hwResolvePyFile = os.path.join(self.homewatcherScriptsDirectory, 'hwresolve.py')

    def testNoOption(self):
        self.assertShellCommand([self.hwResolvePyFile], self.getResourceFullName('out'), self.getResourceFullName('err'))

    def testOutput(self):
        inputHWConfig = 'homewatcher_test_conf.xml'

        # Output to stdout.
        expectedOutput = self.getResourceFullName('out')
        self.assertShellCommand([self.hwResolvePyFile, '-v', 'error', inputHWConfig], expectedOutput)

        # Output to file.
        outputFile = self.getOutputFullName('out')
        self.assertShellCommand([self.hwResolvePyFile, '-v', 'error', '-o', outputFile, inputHWConfig])
        self.assertFilesAreEqual(outputFile, expectedOutput)

    def testResolvedConfigurationIsEquivalentToOriginal(self):
        inputHWConfig = 'homewatcher_test_conf.xml'
        inputLinknxConfig = 'linknx_test_conf.xml'
        hwConfPyFile = os.path.join(self.homewatcherScriptsDirectory, 'hwconf.py')

        # Resolve configuration.
        try:
            resolvedConfigHandle, resolvedConfigFilename = tempfile.mkstemp()
            resolvedLinknxConfig = tempfile.mkstemp()
            unresolvedLinknxConfig = tempfile.mkstemp()
            self.assertShellCommand([self.hwResolvePyFile, '-v', 'error', '-o', resolvedConfigFilename, inputHWConfig])

            # Run hwconf on this resolved configuration.
            self.assertShellCommand([hwConfPyFile, '-v', 'error', '-i', resolvedConfigFilename, '-o', resolvedLinknxConfig[1], inputLinknxConfig])

            # Do the same on the unresolved configuration.
            self.assertShellCommand([hwConfPyFile, '-v', 'error', '-i', inputHWConfig, '-o', unresolvedLinknxConfig[1], inputLinknxConfig])

            # Both linknx configurations must be identical.
            self.assertFilesAreEqual(unresolvedLinknxConfig[1], resolvedLinknxConfig[1])
        finally:
            for f in (resolvedConfigFilename, resolvedLinknxConfig[1], unresolvedLinknxConfig[1]):
                if os.path.exists(f):
                    os.remove(f)

if __name__ == '__main__':
    unittest.main()
