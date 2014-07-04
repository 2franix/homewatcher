#!/usr/bin/python3
# coding=utf-8

import sys
sys.path.append('../')
from pyknx import logger, linknx, configurator
from pyknx.communicator import Communicator
from pyknx.testing import base
from homewatcher import configuration
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

class ConfigurationTestCase(base.TestCaseBase):
	def checkConfigFails(self, configStr, exceptionMessage, resolvesConfig=False, configGetter = lambda config: config):
		config = None
		with self.assertRaises(configuration.Configuration.IntegrityException) as context:
			config = configuration.Configuration.parseString(configStr)
			# Resolve without checking the whole config since it may be
			# partially defined for testing purpose. The part to be tested will
			# be specifically tested afterwards.
			if resolvesConfig: config.resolve(checkIntegrityWhenDone=False)
			partOfConfigToTest = configGetter(config)
			if partOfConfigToTest:
				configClass = type(partOfConfigToTest) if not isinstance(partOfConfigToTest, list) else type(partOfConfigToTest[0])
				configClass.PROPERTY_DEFINITIONS.checkIntegrity(config, partOfConfigToTest)

		self.assertEqual(context.exception.args[0], exceptionMessage, context.exception)
		return config

	def checkSensorConfigFails(self, configStr, exceptionMessage):
		return self.checkConfigFails(configStr, exceptionMessage, resolvesConfig=True, configGetter=lambda config: config.sensors)

	def testConfigurationMethods(self):
		config = configuration.Configuration.parseString("""<config><sensors>
				<sensor name="s1" type="boolean"/>
				<sensor name="s2" type="boolean"/>
				<sensor name="s3" type="boolean"/>
				<class name="c1" type="boolean"/>
				<class name="c2" type="boolean"/>
				<class name="z3" type="boolean"/>
				</sensors></config>""")
		classesOnly = [c.name for c in config.classes]
		classesOnly.sort()
		self.assertEqual(classesOnly, ['boolean', 'c1', 'c2', 'float', 'root', 'z3'])
		sensorsOnly = [c.name for c in config.sensors]
		sensorsOnly.sort()
		self.assertEqual(sensorsOnly, ['s1', 's2', 's3'])
		allSensors = [s.name for s in config.sensorsAndClasses]
		allSensors.sort()
		self.assertEqual(allSensors, ['boolean', 'c1', 'c2', 'float', 'root', 's1', 's2', 's3', 'z3'])
		self.assertIsNone(config.getSensorByName(None))

		config = configuration.Configuration.parseString("""<config><sensors><sensor/></sensors></config>""")
		self.assertIsNone(config.getSensorByName(None))

	def testSensorMethods(self):
		config = configuration.Configuration.parseString("""<config><sensors>
				<sensor name="s1" type="boolean"/>
				<sensor name="s2" type="c2"/>
				<class name="c1" type="boolean"/>
				<class name="c2" type="c3"/>
				<class name="c3" type="boolean"/>
				</sensors></config>""")
		s1 = config.getSensorByName('s1')
		s2 = config.getSensorByName('s2')
		c1 = config.getClassByName('c1')
		c2 = config.getClassByName('c2')
		c3 = config.getClassByName('c3')

		self.assertTrue(config.doesSensorInherit(s1, 'boolean'))
		self.assertTrue(config.doesSensorInherit(s1, 'root'))

		self.assertTrue(config.doesSensorInherit(s2, 'c3'))
		self.assertTrue(config.doesSensorInherit(s2, c3))
		self.assertTrue(config.doesSensorInherit(s2, 'c2'))
		self.assertTrue(config.doesSensorInherit(s2, c2))
		self.assertTrue(config.doesSensorInherit(s2, 'boolean'))
		self.assertTrue(config.doesSensorInherit(s2, 'root'))
		self.assertFalse(config.doesSensorInherit(s2, 'c1'))
		self.assertFalse(config.doesSensorInherit(s2, c1))
		self.assertTrue(config.doesSensorInherit(s1, 'root'))

		self.assertFalse(config.doesSensorInherit(c2, c1))

	def testServicesIntegrityChecks(self):
		""" Exercises Configuration.checkIntegrity """
		# Test services repository is not mandatory.
		config = configuration.Configuration.parseString("""
		<config>
			<services/>
		</config>""")
		configuration.ServicesRepository.PROPERTY_DEFINITIONS.checkIntegrity(config, config.servicesRepository)

		# Test linknx service.
		config = configuration.Configuration.parseString("""
		<config>
			<services/>
		</config>""")
		configuration.ServicesRepository.PROPERTY_DEFINITIONS.checkIntegrity(config, config.servicesRepository)
		self.assertEqual(config.servicesRepository.linknx.host, 'localhost')
		self.assertEqual(config.servicesRepository.linknx.port, 1028)
		config = configuration.Configuration.parseString("""
		<config>
			<services>
				<linknx host="mylinknxhost"/>
			</services>
		</config>""")
		configuration.ServicesRepository.PROPERTY_DEFINITIONS.checkIntegrity(config, config.servicesRepository)
		self.assertEqual(config.servicesRepository.linknx.host, 'mylinknxhost')
		self.assertEqual(config.servicesRepository.linknx.port, 1028)
		config = configuration.Configuration.parseString("""
		<config>
			<services>
				<linknx port="1030"/>
			</services>
		</config>""")
		configuration.ServicesRepository.PROPERTY_DEFINITIONS.checkIntegrity(config, config.servicesRepository)
		self.assertEqual(config.servicesRepository.linknx.host, 'localhost')
		self.assertEqual(config.servicesRepository.linknx.port, 1030)

	def testAlertIntegrityChecks(self):
		""" Exercises Configuration.checkIntegrity """
		# Test name.
		config = self.checkConfigFails("""
		<config>
			<modes objectId="toto"></modes>
			<alerts>
				<alert/>
			</alerts>
		</config>""", '"Alert None" should define the property name (cf. the "name" attribute in XML).')
		config = self.checkConfigFails("""
		<config>
			<modes objectId="foo"/>
			<alerts>
				<alert name="alert1"/>
				<alert name="alert1"/>
			</alerts>
		</config>""", 'Property name (cf. the "name" attribute in XML) is invalid: Value alert1 is already assigned to another object.')

		# Test event type.
		config = self.checkConfigFails("""
		<config>
			<modes objectId="foo"/>
			<alerts>
				<alert name="intrusion">
					<event type="sensorjoined"/>
				</alert>
			</alerts>
		</config>""", 'Property type (cf. the "type" attribute in XML) is invalid: A value in {0} is expected, sensorjoined found.'.format(configuration.AlertEvent.Type.getAll()))
		config = self.checkConfigFails("""
		<config>
			<modes objectId="foo"/>
			<alerts>
				<alert name="intrusion">
					<event type="sensor joined">
						<action type="email" to="toto@titi.fr"/>
					</event>
					<event type="sensor joined">
						<action type="email" to="toto@titi.fr"/>
					</event>
				</alert>
			</alerts>
		</config>""", 'Property type (cf. the "type" attribute in XML) is invalid: Value sensor joined is already assigned to another object.')

		# Test presence of actions.
		config = self.checkConfigFails("""
		<config>
			<modes objectId="foo"/>
			<alerts>
				<alert name="intrusion">
					<event type="sensor joined"/>
				</alert>
			</alerts>
		</config>""", '"Event "sensor joined"" should define the property actions (cf. the "action" element in XML).')

		# # Test definition of actions.
		# config = self.checkConfigFails("""
		# <config>
			# <modes objectId="foo"/>
			# <alerts>
				# <alert name="intrusion">
					# <event type="sensor joined">
						# <action type="foo"/>
					# </event>
				# </alert>
			# </alerts>
		# </config>""", 'Property type (cf. the "type" attribute in XML) is invalid: A value in (\'email\', \'object\') is expected, foo found.')
# 
		# config = self.checkConfigFails("""
		# <config>
			# <modes objectId="foo"/>
			# <alerts>
				# <alert name="intrusion">
					# <event type="sensor joined">
						# <action type="object"/>
					# </event>
				# </alert>
			# </alerts>
		# </config>""", '"Action of type=object" should define the property objectId (cf. the "objectId" attribute or element in XML).')
# 
		# config = self.checkConfigFails("""
		# <config>
			# <modes objectId="foo"/>
			# <alerts>
				# <alert name="intrusion">
					# <event type="sensor joined">
						# <action type="object" objectId="Siren"/>
					# </event>
				# </alert>
			# </alerts>
		# </config>""", '"Action of type=object" should define the property value (cf. the "value" attribute or element in XML).')
# 
		# config = self.checkConfigFails("""
		# <config>
			# <modes objectId="foo"/>
			# <alerts>
				# <alert name="intrusion">
					# <event type="sensor joined">
						# <action type="email"/>
					# </event>
				# </alert>
			# </alerts>
		# </config>""", '"Action of type=email" should define the property to (cf. the "to" attribute or element in XML).')
# 
		# config = configuration.Configuration.parseString("""<config>
			# <alerts>
				# <alert name="intrusion">
					# <event type="sensor joined">
						# <action type="email" to="me@there.com"/>
					# </event>
				# </alert>
			# </alerts>
		# </config>""")
		# configuration.Alert.PROPERTY_DEFINITIONS.checkIntegrity(config, config.alerts)
# 
		# config = configuration.Configuration.parseString("""<config>
			# <alerts>
				# <alert name="intrusion">
					# <event type="sensor joined">
						# <action type="email">
							# <to>me@there.com</to>
							# <to>you@there.com</to>
						# </action>
					# </event>
				# </alert>
			# </alerts>
		# </config>""")
		# configuration.Alert.PROPERTY_DEFINITIONS.checkIntegrity(config, config.alerts)
		# alert = config.getAlertByName('intrusion')
		# self.assertEqual(len(alert.events), 1)
		# self.assertEqual(len(alert.events[0].actions), 1)
		# self.assertEqual(len(alert.events[0].actions[0].to), 2)
		# for to in alert.events[0].actions[0].to:
			# self.assertIn(to, ('me@there.com', 'you@there.com'))

	def testModeIntegrityChecks(self):
		""" Exercises Configuration.checkIntegrity """
		# Test objectId.
		self.checkConfigFails("""
		<config>
			<modes>
				<mode value="2" name="Away"/>
			</modes>
		</config>""", '"ModesRepository([Away [value=2]])" should define the property objectId (cf. the "objectId" attribute or element in XML).')

		# Test name.
		self.checkConfigFails("""
		<config>
			<modes objectId="foo">
				<mode value="2"/>
			</modes>
		</config>""", '"None [value=2]" should define the property name (cf. the "name" attribute in XML).')

		# Test value.
		self.checkConfigFails("""
		<config>
			<modes objectId="foo">
				<mode name="away"/>
			</modes>
		</config>""", '"away [value=None]" should define the property value (cf. the "value" attribute in XML).')

		# Test events.
		self.checkConfigFails("""
		<config>
			<modes objectId="foo">
				<mode name="away"/>
			</modes>
			<alerts>
				<alert name="foo"/>
			</alerts>
			<sensors>
				<sensor name="bar" type="boolean" alert="foo" enabledObjectId="object1" watchedObjectId="object2"/>
			</sensors>
		</config>""", '"away [value=None]" should define the property value (cf. the "value" attribute in XML).')


		# Test involved sensors do exist.
		self.checkConfigFails("""
		<config>
			<modes objectId="foo">
				<mode name="away" value="1">
					<sensor>Sensor1</sensor>
				</mode>
			</modes>
			<sensors>
				<sensor name="s1" type="boolean" alert="intrusion" enabledObjectId="obj1" watchedObjectId="obj2"/>
			</sensors>
		</config>""", "Property sensorNames (cf. the \"sensor\" element in XML) is invalid: A value in ['root', 'boolean', 'float', 's1'] is expected, Sensor1 found.")

	def testSensorIntegrityChecks(self):
		""" Exercises Configuration.checkIntegrity """
		# Test base type does exist.
		self.checkSensorConfigFails("""
		<config>
			<sensors>
				<sensor type="TheUndefinedBaseType" name="sensor1" watchedObjectId="toto" enabledObjectId="titi"/>
			</sensors>
		</config>""", 'Property type (cf. the "type" attribute in XML) is invalid: A value in [\'boolean\', \'float\'] is expected, TheUndefinedBaseType found.')

		# Test sensor does not inherit the root class directly.
		self.checkSensorConfigFails("""
		<config>
			<sensors>
				<sensor type="root" name="sensor1" watchedObjectId="toto" enabledObjectId="titi"/>
			</sensors>
		</config>""", 'Property type (cf. the "type" attribute in XML) is invalid: A value in [\'boolean\', \'float\'] is expected, root found.')

		# Test base type is defined.
		self.checkSensorConfigFails("""
		<config>
			<sensors>
				<sensor name="sensor1" watchedObjectId="toto" enabledObjectId="titi"/>
			</sensors>
		</config>""", '"Sensor sensor1" should define the property type (cf. the "type" attribute in XML).')

		# Test sensor has a name.
		self.checkSensorConfigFails("""
		<config>
			<sensors>
				<sensor watchedObjectId="toto" enabledObjectId="titi"/>
			</sensors>
		</config>""", '"Sensor None" should define the property name (cf. the "name" attribute in XML).')

		# Test sensor's name is unique.
		self.checkSensorConfigFails("""
									<config>
										<sensors>
											<class name="Base" type="boolean" enabledObjectId="titi" watchedObjectId="toto" alert="intrusion" activationDelay="2"/>
											<sensor name="sensor1" type="Base"/>
											<sensor name="sensor1" type="Base"/>
										</sensors>
									</config>""", 'Property name (cf. the "name" attribute in XML) is invalid: Value sensor1 is already assigned to another object.')

		# Test multiple definition of the same property is forbidden
		# (prealertTimeout is defined through an attribute AND through a child
		# element in the sample below).
		self.checkSensorConfigFails("""
		<config>
			<sensors>
				<sensor name="sensor1" type="boolean" watchedObjectId="toto" enabledObjectId="titi" prealertTimeout="12">
					<prealertTimeout value="20"/>
				</sensor>
			</sensors>
		</config>""", 'Property prealertTimeout (cf. the "prealertTimeout" attribute or element in XML) is not a collection, it must have a single value.')

		# Test that a mode dependent delay cannot be defined twice for the same
		# mode.
		self.checkSensorConfigFails("""
		<config>
			<sensors>
				<sensor name="sensor1" type="boolean" watchedObjectId="toto" enabledObjectId="titi" alert="intrusion">
					<prealertTimeout value="20">
						<value mode="Away">30</value>
						<value mode="Away">30</value>
					</prealertTimeout>
				</sensor>
			</sensors>
		</config>""", 'Property modeName (cf. the "mode" attribute in XML) is invalid: Value Away is already assigned to another object.')

	def testModes(self):
		config = configuration.Configuration.parseString("""<config><modes>
				<mode name="Away" value="1">
					<sensor>Sensor1</sensor>
					<sensor>Sensor2</sensor>
				</mode>
				<mode name="At home" value="0"/>
				</modes></config>""")
		self.assertEqual(len(config.modesRepository.modes), 2)
		for m in config.modesRepository.modes:
			self.assertIn(m.name, ('Away', 'At home'))
		awayMode = config.getModeByName('Away')
		self.assertEqual(len(awayMode.sensorNames), 2)
		for s in awayMode.sensorNames:
			self.assertIn(s, ('Sensor1', 'Sensor2'))
		atHomeMode = config.getModeByName('At home')
		self.assertEqual(atHomeMode.sensorNames, [])

	def testSensorAttributesResolution(self):
		""" Exercises the parameterized attributes of a sensor. """
		# Define two sensors with an equivalent config but with attributes
		# ordered differently, so that the test does not pass because the natural ordering of attributes respect the dependency order.
		configStr = """
		<config>
			<sensors>
				<sensor type="boolean" name="Boolean1" key="1" watchedObjectId="{name}Trigger{key}" enabledObjectId="{watchedObjectId}Enabled"/>
				<sensor enabledObjectId="{watchedObjectId}Enabled" nameRewritten="Boolean{key}" type="boolean" key="2" watchedObjectId="{name}Trigger{key}" name="Boolean2">
					<activationCriterion type="sensor" sensor="{nameRewritten}" value="False"/>
				</sensor>
			</sensors>
		</config>"""
		config = configuration.Configuration.parseString(configStr)
		config.resolve(checkIntegrityWhenDone=False)

		for key in [1, 2]:
			sensor = config.getSensorByName('Boolean{key}'.format(key=key))
			self.assertEqual(sensor.watchedObjectId, 'Boolean{key}Trigger{key}'.format(key=key))
			self.assertEqual(sensor.enabledObjectId, 'Boolean{key}Trigger{key}Enabled'.format(key=key))
			self.assertEqual(sensor.activationCriterion.sensorName, 'Boolean{key}'.format(key=key))

	def testSensorInheritance(self):
		configStr= """<?xml version="1.0" encoding="UTF-8"?>
		<config xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance" xsi:schemaLocation="file://config.xsd">
			<modes objectId="Mode">
				<mode name="Presence" value="1"/>
				<mode name="Away" value="2">
					<sensor>EntranceDoorOpening</sensor>
					<sensor>LivingRoomWindowOpening</sensor>
				</mode>
				<mode name="Night" value="3">
					<sensor>EntranceDoorOpening</sensor>
					<sensor>LivingRoomWindowOpening</sensor>
				</mode>
			</modes>
			<alerts>
				<alert name="Intrusion" persistenceObjectId="IntrusionPersistence" >
					<event type="sensor joined">
						<action type="email" to="address@foo.com"/>
					</event>
					<event type="activated">
						<action type="object" objectId="Siren" value="on"/>
					</event>
					<event type="paused">
						<action type="object" objectId="Siren" value="off"/>
					</event>
				</alert>
			</alerts>
			<sensors>
				<sensor type="OpeningSensor" name="EntranceDoorOpening" location="Entrance">
					<activationDelay>
						<value mode="Away">5</value>
						<value mode="Night">3</value>
					</activationDelay>
					<prealertTimeout>
						<value mode="Away">6</value>
					</prealertTimeout>
				</sensor>
				<class type="boolean" name="OpeningSensor" watchedObjectId="OpeningTrigger{location}" enabledObjectId="{location}Enabled" alert="Intrusion" activationDelay="2" prealertTimeout="0" postalertTimeout="10">
					<activationCriterion type="sensor" sensor="{name}" whenTriggered="False"/>
				</class>
				<sensor type="OpeningSensor" name="LivingRoomWindowOpening" location="LivingRoom">
					<activationDelay>
						<value mode="Night">3</value>
					</activationDelay>
				</sensor>
			</sensors>
		</config>"""

		config = configuration.Configuration.parseString(configStr)

		config.resolve()

		resolvedEntranceSensor = config.getSensorByName('EntranceDoorOpening')
		self.assertEqual(resolvedEntranceSensor.alertName, 'Intrusion')
		self.assertEqual(resolvedEntranceSensor.type, 'boolean')
		self.assertEqual(resolvedEntranceSensor.enabledObjectId, 'EntranceEnabled')
		self.assertEqual(resolvedEntranceSensor.watchedObjectId, 'OpeningTriggerEntrance')
		self.assertEqual(resolvedEntranceSensor.persistenceObjectId, None)
		self.assertEqual(resolvedEntranceSensor.activationDelay.getForMode('Away'), 5)
		self.assertEqual(resolvedEntranceSensor.activationDelay.getForMode('Night'), 3)
		self.assertEqual(resolvedEntranceSensor.activationDelay.getForMode(None), 2)
		self.assertEqual(resolvedEntranceSensor.activationCriterion.type, 'sensor')
		self.assertEqual(resolvedEntranceSensor.activationCriterion.sensorName, 'EntranceDoorOpening')
		self.assertFalse(resolvedEntranceSensor.activationCriterion.whenTriggered)
		self.assertEqual(resolvedEntranceSensor.activationCriterion.sensorName, resolvedEntranceSensor.name)
		self.assertEqual(resolvedEntranceSensor.prealertTimeout.getForMode('Away'), 6)

if __name__ == '__main__':
	unittest.main()
