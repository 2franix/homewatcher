#!/usr/bin/python3

# Copyright (C) 2012-2017 Cyrille Defranoux
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

"""
Standalone script used as a launcher for the Homewatcher daemon.
"""

# Check that pyknx is present as soon as possible.
from homewatcher import ensurepyknx

from pyknx import communicator, linknx, logger
from homewatcher import configuration
import argparse
import sys
import logging
import os

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('homewatcherConfig', help='use HWCONF as homewatcher configuration.', metavar='HWCONF')
    parser.add_argument('-d', '--daemonize', help='ask daemon to detach and run as a background daemon.', action='store_true', default=False)
    parser.add_argument('--pid-file', dest='pidFile', help='write the PID of the daemon process to PIDFILE.', metavar='PIDFILE')
    parser.add_argument('--log-file', dest='logFile', help='output daemon\'s activity to LOGFILE rather than to standard output.', metavar='LOGFILE', default=None)
    parser.add_argument('-v', '--verbosity', dest='verbosityLevel', help='set verbosity level.', metavar='LEVEL', choices=[l.lower() for l in logger.getLevelsToString()], default='info')

    args = parser.parse_args()

    # Configure logger.
    logger.initLogger(None, args.verbosityLevel.upper())

    # The homewatcher daemon is represented by an instance of
    # a pyknx.communicator.Communicator that runs with an "user script" dedicated to
    # interfacing linknx with homewatcher's capabilities.
    # First: read homewatcher config to read the linknx server url.
    # Second: start pyknxcommunicator with homewatcher's user script.
    logger.reportInfo('Reading config file {file}'.format(file=args.homewatcherConfig))
    config = configuration.Configuration.parseFile(args.homewatcherConfig)
    userScript = os.path.join(os.path.dirname(configuration.__file__), 'linknxuserfile.py')
    logger.reportDebug('Pyknx\'s user script for homewatcher is {script}'.format(script=userScript))
    userScriptArgs = {'hwconfig' : config}
    services = config.servicesRepository
    communicatorAddress=(services.daemon.host, services.daemon.port)
    logger.reportInfo('Starting Homewatcher at {communicatorAddr}, linked to linknx at {linknxAddr}'.format(communicatorAddr=communicatorAddress, linknxAddr=services.linknx.address))
    linknx = linknx.Linknx(services.linknx.host, services.linknx.port)
    communicator.Communicator.run(linknxAddress=linknx.address, userFile=userScript, communicatorAddress=communicatorAddress, userScriptArgs=userScriptArgs, verbosityLevel=args.verbosityLevel, logFile=args.logFile, daemonizes=args.daemonize, pidFile=args.pidFile)
