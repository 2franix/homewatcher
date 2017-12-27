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
Reads a configuration file for Homewatcher and resolves its parameterized parts before dumping it again.
"""

# Check that pyknx is present as soon as possible.
from homewatcher import ensurepyknx

from homewatcher.configuration import Configuration
import argparse
import sys
import logging
import os
from pyknx import logger

__doc__ = __doc__.format(scriptname=os.path.basename(__file__))

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('homewatcherConfig', help='use HWCONF as the source configuration to resolve.', metavar='HWCONF')
    parser.add_argument('-o', '--output-file', dest='outputFile', help='write the resolved configuration to FILE rather than to standard output.', metavar='FILE')
    parser.add_argument('-v', '--verbose', dest='verbosityLevel', help='set verbosity level.', metavar='LEVEL', choices=[l.lower() for l in logger.getLevelsToString()], default='error')
    args = parser.parse_args()

    # Configure logger.
    logger.initLogger(None, args.verbosityLevel.upper())

    # Read configuration.
    config = Configuration.parseFile(args.homewatcherConfig)

    # Generate a resolved XML.
    config.resolve()
    resolvedDom = config.toXml()
    xmlOutput = resolvedDom.toprettyxml().strip()

    if args.outputFile:
        with open(args.outputFile, 'w') as f:
            f.write(xmlOutput)
    else:
        print(xmlOutput)
