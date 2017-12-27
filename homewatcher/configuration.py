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

from homewatcher import ensurepyknx

from pyknx import logger
import xml.dom.minidom
import os.path
import itertools
import re
from functools import cmp_to_key

class Property(object):
    """
    Represents a property of an object which is part of the configuration.

    A Property is an atomic piece of data that composes the object.
    """
    class XMLEntityTypes(object):
        ATTRIBUTE = 1 << 0
        CHILD_ELEMENT = 1 << 1
        INNER_TEXT = 1 << 2

    def __init__(self, name, type, xmlEntityType, namesInXML=None, groupNameInXML = None, isCollection=False, isUnique=False, values=None, getter=None):
        # Use property's name as name in XML by default.
        if namesInXML == None: namesInXML = name

        # Names in XML must always be iterable.
        if isinstance(namesInXML, str): namesInXML = (namesInXML,)

        self.name = name
        self.type = type
        self.namesInXML = namesInXML # Names of the attribute or child element in xml when applicable, None if this property does not come from a single attribute.
        self.groupNameInXML = groupNameInXML
        self.xmlEntityType = xmlEntityType
        self.isCollection = isCollection # Whether this property is a collection of values.
        self.isUnique = isUnique
        self.values = values # Collection of possible values. May be a callable (configuration object and property's owner object are passed as arguments). If None, no restriction on values.
        self.getter = getter # Optional method to call to retrieve property value. If set to None, the owner object's field named the same as this property is used.

    def isOfPrimitiveType(self):
        return self.type in (str, int, float, bool)

    def isOfClassType(self):
        return not self.isOfPrimitiveType()

    def isDefinedOn(self, object):
        return self.name in vars(object) and vars(object)[self.name] != None

    def checkValue(self, configuration, object, value, collectedValues):
        if self.isCollection:
            if not isinstance(value, list):
                raise Configuration.IntegrityException('A list is expected.')
            values = value
        else:
            values = [value]

        acceptableValues = self.getAcceptablesValues(configuration, object)
        if self.type == str:
            acceptableTypes = (str,)
        elif self.type == float:
            # Accept int too!
            acceptableTypes = (self.type, int)
        else:
            acceptableTypes = (self.type,)
        for v in values:
            if v == None: continue
            if not isinstance(v, acceptableTypes):
                raise Configuration.IntegrityException('A value of type {0} was expected, \"{1}\" of type {2} found.'.format(acceptableTypes, v, type(v)))
            if acceptableValues != None and not v in acceptableValues:
                raise Configuration.IntegrityException('A value in {0} is expected, {1} found.'.format(acceptableValues, v))

            # Is this value unique?
            if self.isUnique and self.name in collectedValues and v in collectedValues[self.name]:
                raise Configuration.IntegrityException('Value {0} is already assigned to another object.'.format(v))

            # Collect this value.
            if not self.name in  collectedValues:
                collectedValues[self.name] = []
            collectedValues[self.name].append(v)

    def getAcceptablesValues(self, configuration, object):
        if self.values == None: return None
        if callable(self.values):
            return self.values(configuration, object)
        else:
            return self.values

    def getValueFor(self, object, config):
        if not self.isDefinedOn(object): return None
        if self.getter == None:
            return vars(object)[self.name]
        else:
            return self.getter(object, config)

    def checkObjectIntegrity(self, configuration, object, collectedValues):
        if not self.isDefinedOn(object): return
        value = self.getValueFor(object, configuration)
        try:
            self.checkValue(configuration, object, value, collectedValues)
        except Configuration.IntegrityException as e:
            raise Configuration.IntegrityException('Property {0} is invalid: {1}'.format(self, e), problematicObject=object)
        if self.isOfClassType():
            if hasattr(self.type, 'PROPERTY_DEFINITIONS'):
                self.type.PROPERTY_DEFINITIONS.checkIntegrity(configuration, value)

    def clone(self, source, destination):
        if self.name in vars(source):
            if vars(source)[self.name] == None:
                vars(destination)[self.name] = None
                return

            copyProperty = lambda p: p if self.isOfPrimitiveType() else p.copy()
            if self.isCollection:
                vars(destination)[self.name] = []
                for prop in vars(source)[self.name]:
                    vars(destination)[self.name].append(copyProperty(prop))
            else:
                vars(destination)[self.name] = copyProperty(vars(source)[self.name])

    def fromXML(self, xmlElement):
        # Scan sources for this property.
        sources = []
        for nameInXML in self.namesInXML:
            if self.xmlEntityType & Property.XMLEntityTypes.ATTRIBUTE != 0:
                attributeValue = Configuration.getXmlAttribute(xmlElement, nameInXML, None)
                if attributeValue != None:
                    sources.append(attributeValue)
            if self.xmlEntityType & Property.XMLEntityTypes.CHILD_ELEMENT != 0:
                sources += Configuration.getElementsInConfig(xmlElement, nameInXML, self.groupNameInXML)
            if self.xmlEntityType & Property.XMLEntityTypes.INNER_TEXT != 0:
                sources.append(Configuration.getTextInElement(xmlElement, mustFind=False))

        values = []
        for source in sources:
            if source == None: continue

            if self.isOfPrimitiveType():
                # Property type is a primitive type, let's get a string from
                # source.
                if not isinstance(source, str):
                    # Source is assumed to be an xml element.
                    sourceStr = Configuration.getTextInElement(source, mustFind = True)
                else:
                    sourceStr = source

            if self.type == str:
                values.append(sourceStr)
            elif self.type == int:
                values.append(int(sourceStr))
            elif self.type == float:
                values.append(float(sourceStr))
            elif self.type == bool:
                if sourceStr.lower() == 'true':
                    values.append(True)
                elif sourceStr.lower() == 'false':
                    values.append(False)
                else:
                    raise Configuration.IntegrityException('Property {0}={1} is not a boolean constant. Expecting {{true, false}}, case insensitive.'.format(self, sourceStr), xmlContext=xmlElement.toxml())
            else:
                # Type corresponds to a class.
                if isinstance(source, str):
                    values.append(self.type.fromString(source))
                else:
                    # Call the static method "fromXML" if present. Otherwise,
                    # run the predefined behaviour.
                    if hasattr(self.type, 'fromXML') and callable(self.type.fromXML):
                        newPropertyValue = self.type.fromXML(source)
                    else:
                        # Create a default instance.
                        try:
                            newPropertyValue = self.type()
                            if hasattr(self.type, 'PROPERTY_DEFINITIONS'):
                                self.type.PROPERTY_DEFINITIONS.readObjectFromXML(newPropertyValue, source)
                        except:
                            # logger.reportException('Type {type} has neither static fromXML(xmlElement) nor __init__() method. At least one is required to parse it properly.'.format(type=self.type))
                            raise

                    # Assign attributes from XML.
                    if hasattr(newPropertyValue, 'attributes'):
                        for k, v in source.attributes.items():
                            newPropertyValue.attributes[k] = v
                    values.append(newPropertyValue)




        if not values: return None
        if self.isCollection:
            return values
        else:
            if len(values) > 1:
                raise Configuration.IntegrityException('Property {0} is not a collection, it must have a single value.'.format(self), xmlContext=xmlElement.toxml())
            return values[0]

    def toXml(self, config, propertyOwner, xmlDoc, xmlElement):
        # Create group if necessary.
        if self.groupNameInXML != None:
            group = next(Configuration.getElementsInConfig(xmlElement, self.groupNameInXML, None), None)
            if not group:
                group = xmlDoc.createElement(self.groupNameInXML)
                xmlElement.appendChild(group)
            xmlElement = group

        value = self.getValueFor(propertyOwner, config)

        # Make sure the remainder of this method works on a collection of values.
        values = value if isinstance(value, list) else [value]
        for value in values:
            if hasattr(value, 'toXml') and callable(value.toXml):
                # Use the instance toXml() method.
                value.toXml(config, self, propertyOwner, xmlDoc, xmlElement)
            else:
                # Format property using its inner properties.
                logger.reportDebug('toXml for {0} on {1}'.format(self, propertyOwner))
                if self.xmlEntityType & Property.XMLEntityTypes.ATTRIBUTE != 0:
                    valueStr = str(value)
                    xmlElement.setAttribute(self.namesInXML[0], valueStr)
                elif self.xmlEntityType & Property.XMLEntityTypes.CHILD_ELEMENT != 0:
                    childNode = xmlDoc.createElement(self.namesInXML[0])
                    if self.isOfPrimitiveType():
                        textNode = xmlDoc.createTextNode(str(value))
                        childNode.appendChild(textNode)
                    else:
                        childNode = xmlDoc.createElement(self.namesInXML[0])
                        type(value).PROPERTY_DEFINITIONS.toXml(config, value, xmlDoc, childNode)
                    xmlElement.appendChild(childNode)
                elif self.xmlEntityType & Property.XMLEntityTypes.INNER_TEXT != 0:
                    textNode = xmlDoc.createTextNode(str(value))
                    xmlElement.appendChild(textNode)

    def __repr__(self):
        s = self.name
        attributeOrChild = ''
        if self.xmlEntityType & Property.XMLEntityTypes.ATTRIBUTE != 0:
            attributeOrChild = 'attribute'
        if self.xmlEntityType & Property.XMLEntityTypes.CHILD_ELEMENT != 0:
            if attributeOrChild: attributeOrChild += ' or '
            attributeOrChild += 'element'
        if self.xmlEntityType & Property.XMLEntityTypes.INNER_TEXT != 0:
            if attributeOrChild: attributeOrChild += ' or '
            attributeOrChild += 'inner text'
        if len(self.namesInXML) > 1:
            plural = 's'
            namesInXML = self.namesInXML
        else:
            plural = ''
            namesInXML = self.namesInXML[0]
        s += ' (cf. the "{namesInXML}" {attributeOrChild}{plural} in XML)'.format(attributeOrChild=attributeOrChild, namesInXML=namesInXML, plural=plural)
        return s

class PropertyGroup(object):
    """ Group properties that must be considered simultaneously when determining whether they are mandatory or not.
        If the group is mandatory, the configuration is full of integrity as long as at least one of the group's properties is defined. """

    class GroupUseContext(object):
        def __init__(self, configuration, object):
            self.configuration = configuration
            self.object = object

    def __init__(self, properties, isMandatory):
        self.properties = properties
        self.isMandatoryCallable = isMandatory if callable(isMandatory) else lambda context: isMandatory

    def isMandatory(self, object):
        return self.isMandatoryCallable(object)

    def checkObjectIntegrity(self, configuration, object, collectedValues):
        isDefined = False
        for prop in self.properties:
            prop.checkObjectIntegrity(configuration, object, collectedValues)
            isDefined |= prop.isDefinedOn(object)

        if self.isMandatory(PropertyGroup.GroupUseContext(configuration, object)) and not isDefined:
            if len(self.properties) == 1:
                raise Configuration.IntegrityException('"{0}" should define the property {1}.'.format(object, self.properties[0]), problematicObject=object)
            else:
                raise Configuration.IntegrityException('"{0}" should define at least one of the properties {1}.'.format(object, self.properties), problematicObject=object)

class PropertyCollection(object):
    """ Collection of properties stored in groups with an associated mandatory status. """
    def __init__(self):
        self.propertyGroups = []
        self.ignoreCheckIntegrityCallable = lambda object: False

    def addProperty(self, propertyName, isMandatory, type, xmlEntityType, namesInXML=None, groupNameInXML = None, isCollection=False, isUnique=False, values=None, getter=None):
        self.propertyGroups.append(PropertyGroup([Property(name=propertyName, type=type, xmlEntityType = xmlEntityType, namesInXML=namesInXML, groupNameInXML=groupNameInXML, isCollection=isCollection, isUnique=isUnique, values=values, getter=getter)], isMandatory))

    def addPropertyGroup(self, properties, isGroupMandatory = True):
        group = PropertyGroup(properties[:], isGroupMandatory)
        self.propertyGroups.append(group)

    def cloneProperties(self, source, destination):
        for propDef in self.properties:
            propDef.clone(source, destination)

    @property
    def properties(self):
        return itertools.chain(*[group.properties for group in self.propertyGroups])

    def getProperty(self, propertyName):
        for group in self.propertyGroups:
            prop = [p for p in group.properties if p.name == propertyName]
            if prop:
                return prop[0]
        raise Exception('No property {0} found in group {1}.'.format(propertyName, self))

    def readObjectFromXML(self, object, xmlElement):
        object.xmlSource = xmlElement.toxml()
        for prop in self.properties:
            if prop.namesInXML != None:
                value = prop.fromXML(xmlElement)

                if value is None:
                    if prop.isDefinedOn(object):
                        # We are better off keeping the current value than
                        # overriding it with the never explicitly-defined (hence rather meaningless) None value.
                        continue
                    else:
                        # Assigning the None value guarantees that all properties are always defined on the
                        # destination object even if the XML configuration is not complete.
                        vars(object)[prop.name] = value
                else:
                    if prop.isCollection and prop.isDefinedOn(object):
                        # Do not override current items!
                        vars(object)[prop.name].extend(value)
                    else:
                        # First definition of collection or assignment of a simple field.
                        vars(object)[prop.name] = value

    def checkIntegrity(self, configuration, obj, collectedValues=None):
        """
        Checks the integrity of an object wrt this collection of properties.

        configuration: Configuration object that contains the object to check.
        obj: Object to check
        collectedValues: Properties' values. It is a dictionary that indexes list of values with property names as keys.
        """
        if collectedValues == None: collectedValues = {}
        objects = obj if isinstance(obj, list) else [obj]
        for o in objects:
            if self.ignoreCheckIntegrityCallable(o): continue
            for group in self.propertyGroups:
                group.checkObjectIntegrity(configuration, o, collectedValues)

    def toXml(self, config, propertyOwner, xmlDoc, xmlElement):
        for prop in self.properties:
            logger.reportDebug('toXml {0} on {1}'.format(prop, propertyOwner))
            if prop.isDefinedOn(propertyOwner):
                prop.toXml(config, propertyOwner, xmlDoc, xmlElement)
            else:
                logger.reportDebug('not defined')

    # def generateDocumentation(self, classs, collector):
        # # Check for reentrance.
        # if collector.containsDocumentationForClass(classs): return
# 
        # # f.write('#{0}\n'.format(classs.__name__))
        # for propertyGroup in self.propertyGroups:
            # for header, entityType in [('Attributes', Property.XMLEntityTypes.ATTRIBUTE), ('Text', Property.XMLEntityTypes.INNER_TEXT), ('Children', Property.XMLEntityTypes.CHILD_ELEMENT)]:
                # for property in propertyGroup.properties:
                    # if entityType & property.xmlEntityType == 0: continue
                    # collector.addDocumentationFor(class, '## {0}'.format(header))
                    # if property.isOfClassType():
                        # collector.addDocumentationFor(classs, '- [{0}](#{1}): {2}'.format(property.namesInXML[0], property.type, property.documentation.summary))
                    # else:
                        # collector.addDocumentationFor(classs, '- {0} ({1}): {2}'.format(property.namesInXML[0], property.type, property.documentation.summary))
                 # if property.documentation != None:
                    # collector.addDocumentationForClass(classs, property.documentation.summary +  '\n')
                # if property.isOfClassType():
                    # typeContent = '[{propType}](#{propType})'.format(propType=property.type.__name__)
                    # if hasattr(property.type, 'PROPERTY_DEFINITIONS'):
                        # property.type.PROPERTY_DEFINITIONS.generateDocumentation(property.type, collector)
                # else:
                    # typeContent = property.type.__name__
                # if len(property.namesInXML) > 1: raise Exception('The documentation generator assumes that there is only a single XML tag name associated to each property.')
                # collector.addDocumentationForClass(classs, 'Xml tag name: {0}'.format('`<{0}/>`'.format(property.namesInXML[0])))
                # collector.addDocumentationForClass(classs, 'type: {0}'.format(typeContent))
                # if property.values != None and not callable(property.values):
                    # collector.addDocumentationForClass(classs, 'Accepted Values: {0}'.format(list(property.values)))

class ParameterizableString(object):
    """
    Represents a string in the XML configuration that can be parameterized with <context> children.

    Refer to the 'context handler' concept to understand how parameterization can take place with those children.
    This class is quite useless but is required to have an object that holds the automatically-created xmlSource property.
    """
    pass

class PyknxService(object):
    """Represents the configuration for the communication with the hosting Pyknx daemon.

    The Pyknx daemon is the underlying process for Homewatcher that handles the communication with the Linknx daemon.
    """
    PROPERTY_DEFINITIONS = PropertyCollection()
    PROPERTY_DEFINITIONS.addProperty('host', isMandatory=False, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE|Property.XMLEntityTypes.CHILD_ELEMENT)
    PROPERTY_DEFINITIONS.addProperty('port', isMandatory=False, type=int, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE|Property.XMLEntityTypes.CHILD_ELEMENT)

    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 1029

    def __repr__(self):
        return 'PyknxService(host={host}, port={port})'.format(**vars(self))

# class SMTPService(object):
    # PROPERTY_DEFINITIONS = PropertyCollection()
    # PROPERTY_DEFINITIONS.addProperty('host', isMandatory=False, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE|Property.XMLEntityTypes.CHILD_ELEMENT)
    # PROPERTY_DEFINITIONS.addProperty('port', isMandatory=False, type=int, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE|Property.XMLEntityTypes.CHILD_ELEMENT)
    # PROPERTY_DEFINITIONS.addProperty('fromAddress', isMandatory=False, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE|Property.XMLEntityTypes.CHILD_ELEMENT)
# 
    # def __init__(self):
        # self.host = 'localhost'
        # self.port = 25
# 
    # def __repr__(self):
        # return 'SMTPService(host={host}, port={port})'.format(**vars(self))

class LinknxService(object):
    PROPERTY_DEFINITIONS = PropertyCollection()
    hostProp = Property('host', type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE|Property.XMLEntityTypes.CHILD_ELEMENT)
    portProp = Property('port', type=int, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE|Property.XMLEntityTypes.CHILD_ELEMENT)
    PROPERTY_DEFINITIONS.addPropertyGroup((hostProp, portProp))
    PROPERTY_DEFINITIONS.addProperty('ignoreEmail', isMandatory=False, type=bool, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE)

    def __init__(self):
        self.host = '127.0.0.1'
        self.port = 1028
        self.ignoreEmail = False

    @property
    def address(self):
        return (self.host, self.port)

    def __repr__(self):
        return 'LinknxService(host={host},port={port})'.format(**vars(self))

class ServicesRepository(object):
    PROPERTY_DEFINITIONS = PropertyCollection()
    PROPERTY_DEFINITIONS.addProperty('linknx', isMandatory=False, type=LinknxService, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT)
    PROPERTY_DEFINITIONS.addProperty('daemon', isMandatory=False, type=PyknxService, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT)
    # PROPERTY_DEFINITIONS.addProperty('smtp', isMandatory=False, type=SMTPService, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT)

    def __init__(self):
        self.linknx = LinknxService()
        self.daemon = PyknxService()

class ModeDependentValue(object):

    class Value(object):
        PROPERTY_DEFINITIONS = PropertyCollection()
        PROPERTY_DEFINITIONS.addProperty('value', isMandatory=True, type=float, xmlEntityType=Property.XMLEntityTypes.INNER_TEXT)
        PROPERTY_DEFINITIONS.addProperty('modeName', isMandatory=False, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, namesInXML='mode', isUnique=True)

        def __init__(self, value, modeName):
            if type(value) not in [int, float]:
                raise ValueError('int or float expected, {0} found'.format(type(value)))
            self.value = value
            self.modeName = modeName

        def copy(self):
            v = ModeDependentValue.Value(0.0, None)
            self.PROPERTY_DEFINITIONS.cloneProperties(self, v)
            return v

        @staticmethod
        def fromString(string):
            return ModeDependentValue.Value(float(string), None)

        @staticmethod
        def fromXML(xmlElement):
            val = ModeDependentValue.Value(0, None)
            ModeDependentValue.Value.PROPERTY_DEFINITIONS.readObjectFromXML(val, xmlElement)
            return val

        def __repr__(self):
            return 'Value({value},{modeName})'.format(**vars(self))

    PROPERTY_DEFINITIONS = PropertyCollection()
    PROPERTY_DEFINITIONS.addProperty('values', isMandatory=True, type=Value, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE|Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML='value', isCollection=True)

    def __init__(self, defaultValue=None):
        self.values = []
        if defaultValue != None:
            self.values.append(ModeDependentValue.Value(value=defaultValue, modeName=None))

    def copy(self):
        v = ModeDependentValue()
        self.PROPERTY_DEFINITIONS.cloneProperties(self, v)
        return v

    @staticmethod
    def fromString(string):
        # This is assumed to be the default value (i.e the one used for modes
        # that do not have a specific value.
        return ModeDependentValue(float(string))

    @staticmethod
    def fromXML(xmlElement):
        value=ModeDependentValue()
        ModeDependentValue.PROPERTY_DEFINITIONS.readObjectFromXML(value, xmlElement)
        return value

    def toXml(self, config, property, propertyOwner, xmlDoc, xmlElement):
        # Opt for an xml attribute if possible as it makes XML simpler.
        if len(self.values) == 1 and self.values[0].modeName == None:
            xmlElement.setAttribute(property.namesInXML[0], str(self.values[0].value))
        else:
            container = xmlDoc.createElement(property.namesInXML[0])
            xmlElement.appendChild(container)
            for value in self.values:
                valueChild = xmlDoc.createElement('value')
                container.appendChild(valueChild)
                type(value).PROPERTY_DEFINITIONS.toXml(config, value, xmlDoc, valueChild)

    def hasDefaultValue(self):
        return None in self.values

    def getDefinedModes(self):
        return {value.modeName for value in self.values}

    def getForMode(self, modeName):
        if not isinstance(modeName, str) and modeName != None:
            raise Exception('A mode name or None is expected.')
        for value in self.values:
            if value.modeName == modeName:
                return value.value
        if modeName == None: raise Exception('Default value not found.')

        # Fall back to the default value.
        return self.getForMode(None)

    def setForMode(self, mode, value):
        self.values[mode] = value

    def inherit(self, other):
        """ Inherits values from another instance for modes that have no specific value in this instance. """
        logger.reportDebug('{0} inherits from {1}'.format(self, other))
        definedModes = self.getDefinedModes()
        for value in other.values:
            # Do not overwrite the value in this instance!
            if value.modeName in definedModes: continue
            self.values.append(value.copy())
        logger.reportDebug('That gives {0}'.format(self, other))

    def __repr__(self):
        return 'ModeDependentValue({values})'.format(**vars(self))

class ActivationCriterion(object):
    """ Describes the rule that determine whether a sensor that is involved in a mode can be activated or if its activation should be deferred. """

    class Type(object):
        SENSOR = 'sensor'
        AND = 'and'
        OR = 'or'

        @staticmethod
        def getAll():
            return (ActivationCriterion.Type.SENSOR, ActivationCriterion.Type.AND, ActivationCriterion.Type.OR)

    def __init__(self):
        self._attributes = {}

    @property
    def attributes(self):
        return self._attributes

    def copy(self):
        clone = ActivationCriterion()
        clone._attributes = self._attributes.copy()
        ActivationCriterion.PROPERTY_DEFINITIONS.cloneProperties(self, clone)
        return clone

    def inherit(self, other):
        # Inheritance does not apply for this object.
        pass

    @staticmethod
    def makeSensorCriterion(sensorName, whenTriggered = False):
        crit = ActivationCriterion()
        crit.type = ActivationCriterion.Type.SENSOR
        crit.sensorName = sensorName
        crit.whenTriggered = whenTriggered
        return crit

    @staticmethod
    def makeAndCriterion():
        return makeBooleanCriterion()

    @staticmethod
    def makeOrCriterion():
        return makeBooleanCriterion()

    @staticmethod
    def makeBooleanCriterion(type):
        if not type in [ActivationCriterion.Type.AND, ActivationCriterion.Type.OR]: raise Exception('Invalid boolean criterion type: {0}'.format(type))
        crit = ActivationCriterion()
        crit.type = type
        crit.children = []
        return crit

    # @staticmethod
    # def fromXML(xmlElement):
        # type = Configuration.getXmlAttribute(xmlElement, 'type', None, mustBeDefined=True)
        # criterion = ActivationCriterion(type)
        # 
        # ActivationCriterion.PROPERTY_DEFINITIONS.readObjectFromXML(criterion, xmlElement)
        # 
        # return criterion

# Define properties outside class because of a reference to the class itself.
ActivationCriterion.PROPERTY_DEFINITIONS = PropertyCollection()
ActivationCriterion.PROPERTY_DEFINITIONS.addProperty('type', isMandatory=True, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, values=ActivationCriterion.Type.getAll())
isOfSensorType=lambda context: context.object.type==ActivationCriterion.Type.SENSOR
getSensorNames = lambda configuration, owner: [s.name for s in configuration.sensors]
ActivationCriterion.PROPERTY_DEFINITIONS.addProperty('sensorName', isMandatory=isOfSensorType, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, namesInXML='sensor', values=getSensorNames)
ActivationCriterion.PROPERTY_DEFINITIONS.addProperty('whenTriggered', isMandatory=isOfSensorType, type=bool, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE)
ActivationCriterion.PROPERTY_DEFINITIONS.addProperty('children', isMandatory=lambda context: context.object.type in (ActivationCriterion.Type.AND, ActivationCriterion.Type.OR), type=ActivationCriterion, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML='activationCriterion', isCollection=True)

class Sensor(object):
    class Type(object):
        ROOT = 'root'
        BOOLEAN = 'boolean'
        FLOAT = 'float'

        @staticmethod
        def getAll():
            return [Sensor.Type.ROOT, Sensor.Type.BOOLEAN, Sensor.Type.FLOAT]

        @staticmethod
        def getBasicTypes():
            all = Sensor.Type.getAll()
            all.remove(Sensor.Type.ROOT)
            return all

    PROPERTY_DEFINITIONS = PropertyCollection()
    PROPERTY_DEFINITIONS.ignoreCheckIntegrityCallable = lambda sensor: sensor.isClass
    # Generic mandatory properties of various types.
    PROPERTY_DEFINITIONS.addProperty('name', isMandatory=True, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, isUnique=True)
    getClassNamesExceptRoot = lambda configuration, owner: [c.name for c in configuration.classes if (not c.isRootType() or owner.name in Sensor.Type.getAll()) and c != owner and not configuration.doesSensorInherit(c, owner)]
    PROPERTY_DEFINITIONS.addProperty('type', isMandatory=lambda context: not context.object.isRootType(), type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, values=getClassNamesExceptRoot)
    PROPERTY_DEFINITIONS.addProperty('isClass', isMandatory=True, type=bool, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE)
    isNotClass = lambda context: not context.object.isClass
    PROPERTY_DEFINITIONS.addProperty('alertName', isMandatory=isNotClass, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, namesInXML='alert')
    PROPERTY_DEFINITIONS.addProperty('enabledObjectId', isMandatory=isNotClass, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, isUnique=True)
    PROPERTY_DEFINITIONS.addProperty('watchedObjectId', isMandatory=isNotClass, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE)
    for propName in ['activationDelay', 'prealertDuration', 'alertDuration']:
        PROPERTY_DEFINITIONS.addProperty(propName, isMandatory=isNotClass, type=ModeDependentValue, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE | Property.XMLEntityTypes.CHILD_ELEMENT)
    PROPERTY_DEFINITIONS.addProperty('activationCriterion', isMandatory=isNotClass, type=ActivationCriterion, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT)

    # Mandatory properties for booleans.
    isBoolean = lambda context: not context.object.isClass and context.configuration.doesSensorInherit(context.object, Sensor.Type.BOOLEAN)
    for propName in ['triggerValue']:
        PROPERTY_DEFINITIONS.addProperty(propName, isMandatory=isBoolean, type=bool, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE)

    # Mandatory properties for float sensors.
    isFloat = lambda context: not context.object.isClass and context.configuration.doesSensorInherit(context.object, Sensor.Type.FLOAT)
    PROPERTY_DEFINITIONS.addPropertyGroup([Property(name, type=float, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE) for name in ['lowerBound', 'upperBound']], isFloat)
    PROPERTY_DEFINITIONS.addProperty('hysteresis', isMandatory=isFloat, type=float, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE)

    # Optional properties.
    PROPERTY_DEFINITIONS.addProperty('description', isMandatory=False, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE|Property.XMLEntityTypes.CHILD_ELEMENT)
    PROPERTY_DEFINITIONS.addProperty('persistenceObjectId', isMandatory=False, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, isUnique=True)

    def __init__(self, type, name, isBuiltIn):
        self.type = type # Sensor type from Sensor.Type or base class name if class.
        self.name = name # Sensor's name or class's name.
        self.isClass = False
        self.isBuiltIn = isBuiltIn

        self._attributes = {}

    @staticmethod
    def makeNew(type, name, desc, isClass, isBuiltIn, alertName=None, enabledObjectId=None, watchedObjectId=None, persistenceObjectId=None):
        s = Sensor(type, name, isBuiltIn)
        s.description = desc
        s.isClass = isClass
        s.alertName = alertName
        s.enabledObjectId = enabledObjectId
        s.watchedObjectId = watchedObjectId
        s.persistenceObjectId = persistenceObjectId
        return s

    def isRootType(self):
        return self.name == Sensor.Type.ROOT

    def addAttribute(self, attributeName, attributeValue):
        self._attributes[attributeName] = attributeValue

    @staticmethod
    def fromXML(xmlElement):
        s = Sensor(None, None, isBuiltIn=False)
        Sensor.PROPERTY_DEFINITIONS.readObjectFromXML(s, xmlElement)
        return s

    @property
    def attributes(self):
        return self._attributes

    def __repr__(self):
        return '{classOrSensor} {name}'.format(classOrSensor='Class' if self.isClass else 'Sensor', name=self.name)

class Action(object):
    def __init__(self, type, eventName):
        pass

    @property
    def type(self):
        return self.linknxActionXml.getAttribute('type')

    @staticmethod
    def fromXML(xmlElement):
        e=Action(None, None)
        Action.PROPERTY_DEFINITIONS.readObjectFromXML(e, xmlElement)

        # Store the input XML to be able to send it to linknx when executing the
        # action.
        e.linknxActionXml = xmlElement
        return e

    def toXml(self, config, property, propertyOwner, xmlDoc, xmlElement):
        linknxActionClone = xmlDoc.importNode(self.linknxActionXml, True)
        xmlElement.appendChild(linknxActionClone)

    def __repr__(self):
        return 'Action of type={type}'.format(type=self.type)

Action.PROPERTY_DEFINITIONS = PropertyCollection()
Action.PROPERTY_DEFINITIONS.addProperty('type', isMandatory=True, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE)

# Subject properties: one for the static, Linknx-defined "subject" attribute,
# one for a Homewatcher-specific, dynamic "subject" element.
staticSubjectProp = Property('staticSubject', type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, namesInXML=('subject',))
parameterizableSubjectProp = Property('parameterizableSubject', type=ParameterizableString, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML=('subject'))
Action.PROPERTY_DEFINITIONS.addPropertyGroup((staticSubjectProp, parameterizableSubjectProp), isGroupMandatory=lambda context: context.object.type == 'send-email')

# Body properties: one for the static, Linknx-defined inner text of the <action>
# element, one for a Homewatcher-specific, dynamic "body" element.
staticBodyProp = Property('staticBody', type=str, xmlEntityType=Property.XMLEntityTypes.INNER_TEXT)
parameterizableBodyProp = Property('parameterizableBody', type=ParameterizableString, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML=('body'))
Action.PROPERTY_DEFINITIONS.addPropertyGroup((staticBodyProp, parameterizableBodyProp), isGroupMandatory=lambda context: context.object.type == 'send-email')

staticValueProp = Property('staticValue', type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, namesInXML=('value',))
parameterizableValueProp = Property('parameterizableValue', type=ParameterizableString, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML=('value'))
Action.PROPERTY_DEFINITIONS.addPropertyGroup((staticValueProp, parameterizableValueProp), isGroupMandatory=lambda context: context.object.type == 'send-sms')
# All actions are handled by linknx except send-email that has to be reworked by
# Homewatcher to customize email text.
# for propName in ('objectId', 'value'):
    # Action.PROPERTY_DEFINITIONS.addProperty(propName, isMandatory=lambda context: context.object.type==Action.Type.CHANGE_OBJECT, type=str, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT|Property.XMLEntityTypes.ATTRIBUTE)

class Event(object):

    def __repr__(self):
        return 'Event "{type}"'.format(**vars(self))

Event.PROPERTY_DEFINITIONS = PropertyCollection()
Event.PROPERTY_DEFINITIONS.addProperty('type', isMandatory=True, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, values=lambda configuration, owner:type(owner).Type.getAll(), isUnique=True)
Event.PROPERTY_DEFINITIONS.addProperty('actions', isMandatory=True, type=Action, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML='action', isCollection=True)

class ModeEvent(Event):
    class Type:
        ENTERED = 'entered'
        LEFT = 'left'

        @staticmethod
        def getAll():
            return [ModeEvent.Type.ENTERED, ModeEvent.Type.LEFT]

class Mode(object):

    PROPERTY_DEFINITIONS = PropertyCollection()
    PROPERTY_DEFINITIONS.addProperty('name', isMandatory=True, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, isUnique=True)
    PROPERTY_DEFINITIONS.addProperty('value', isMandatory=True, type=int, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, isUnique=True)
    PROPERTY_DEFINITIONS.addProperty('sensorNames', isMandatory=False, type=str, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML='sensor', isCollection=True, values=lambda configuration, object: [s.name for s in configuration.sensors])
    PROPERTY_DEFINITIONS.addProperty('events', isMandatory=False, type=ModeEvent, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML='event', isCollection=True)

    def __init__(self, name, value):
        self.name = name # Unique identifier for the mode.
        self.value = value
        self.sensorNames = []
        self.events = []

    @staticmethod
    def fromXML(xmlElement):
        m = Mode(None, None)
        Mode.PROPERTY_DEFINITIONS.readObjectFromXML(m, xmlElement)
        return m

    def __repr__(self):
        return '{name} [value={value}]'.format(**vars(self))

class ModesRepository:
    PROPERTY_DEFINITIONS = PropertyCollection()
    PROPERTY_DEFINITIONS.addProperty('objectId', isMandatory=True, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE|Property.XMLEntityTypes.CHILD_ELEMENT)
    # Temporarily removed in version 1. Mode-independent events imply additional
    # testing that is beyond the scope of the initial version.
    # PROPERTY_DEFINITIONS.addProperty('events', isMandatory=False, type=ModeEvent, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML="event", isCollection=True)
    PROPERTY_DEFINITIONS.addProperty('modes', isMandatory=False, type=Mode, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML="mode", isCollection=True)
    PROPERTY_DEFINITIONS.addProperty('events', isMandatory=False, type=ModeEvent, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML='event', isCollection=True)

    def __init__(self):
        self.events = []
        self.modes = []

    def __iter__(self):
        if ModesRepository.PROPERTY_DEFINITIONS.getProperty('modes').isDefinedOn(self):
            return self.modes.__iter__()
        else:
            return [].__iter__()

    def __len__(self):
        return len(self.modes)

    def __getitem__(self, index):
        return self.modes[index]

    def __repr__(self):
        return 'ModesRepository({0})'.format(self.modes)

class AlertEvent(Event):
    class Type:
        PREALERT_STARTED = 'prealert started'
        ALERT_ACTIVATED = 'activated'
        ALERT_DEACTIVATED = 'deactivated'
        ALERT_PAUSED = 'paused'
        ALERT_RESUMED = 'resumed'
        ALERT_STOPPED = 'stopped'
        ALERT_ABORTED = 'aborted'
        ALERT_RESET = 'reset'
        SENSOR_JOINED = 'sensor joined'
        SENSOR_LEFT = 'sensor left'

        @staticmethod
        def getAll():
            return [AlertEvent.Type.PREALERT_STARTED, AlertEvent.Type.ALERT_ACTIVATED, AlertEvent.Type.ALERT_DEACTIVATED, AlertEvent.Type.ALERT_PAUSED, AlertEvent.Type.ALERT_RESUMED, AlertEvent.Type.ALERT_STOPPED, AlertEvent.Type.ALERT_ABORTED, AlertEvent.Type.ALERT_RESET, AlertEvent.Type.SENSOR_JOINED, AlertEvent.Type.SENSOR_LEFT]

class Alert(object):
    PROPERTY_DEFINITIONS = PropertyCollection()
    PROPERTY_DEFINITIONS.addProperty('name', isMandatory=True, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, isUnique=True)
    PROPERTY_DEFINITIONS.addProperty('persistenceObjectId', isMandatory=False, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE, isUnique=True)
    PROPERTY_DEFINITIONS.addProperty('inhibitionObjectId', isMandatory=False, type=str, xmlEntityType=Property.XMLEntityTypes.ATTRIBUTE)
    PROPERTY_DEFINITIONS.addProperty('events', isMandatory=False, type=AlertEvent, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML='event', isCollection=True)

    def __init__(self):
        self.events = []

    @staticmethod
    def makeNew(id, persistenceObjectId, inhibitionObjectId):
        alert = Alert(id, persistenceObjectId)
        alert.inhibitionObjectId = inhibitionObjectId
        return alert

    def __repr__(self):
        return 'Alert {name}'.format(**vars(self))

class AlertsRepository(object):
    PROPERTY_DEFINITIONS = PropertyCollection()
    PROPERTY_DEFINITIONS.addProperty('alerts', isMandatory=True, type=Alert, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML='alert', isCollection=True)
    PROPERTY_DEFINITIONS.addProperty('events', isMandatory=False, type=AlertEvent, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML='event', isCollection=True)

    def __init__(self):
        self.alerts = []
        self.events = []

    def __iter__(self):
        if AlertsRepository.PROPERTY_DEFINITIONS.getProperty('alerts').isDefinedOn(self):
            return self.alerts.__iter__()
        else:
            return [].__iter__()

    def __len__(self):
        return len(self.alerts)

    def __getitem__(self, index):
        return self.alerts[index]

    def __repr__(self):
        return 'AlertsRepository({0})'.format(self.alerts)

class Configuration(object):
    class IntegrityException(Exception):
        def __init__(self, message, cause = None, problematicObject=None, xmlContext=None):
            Exception.__init__(self, message)
            self.cause = cause
            self._problematicObject = None
            self.xmlContext = None
            self.problematicObject = problematicObject

        @property
        def problematicObject(self):
            return self._problematicObject

        @problematicObject.setter
        def problematicObject(self, obj):
            self._problematicObject = obj
            if self.xmlContext == None and hasattr(self._problematicObject, 'xmlSource'):
                self.xmlContext = self._problematicObject.xmlSource

        def __str__(self):
            s = Exception.__str__(self)
            if self.problematicObject != None:
                s += '\nProblematic object: {0} of type {1}'.format(self.problematicObject, type(self.problematicObject))
            if self.xmlContext != None:
                s += '\nXML context: {0}'.format(self.xmlContext)
            if self.cause != None:
                s += '\nCaused by {0}'.format(self.cause)
            return s

    PROPERTY_DEFINITIONS = PropertyCollection()
    PROPERTY_DEFINITIONS.addProperty('modesRepository', isMandatory=True, type=ModesRepository, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML='modes')
    PROPERTY_DEFINITIONS.addProperty('alerts', isMandatory=True, type=AlertsRepository, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT)
    PROPERTY_DEFINITIONS.addProperty('sensorsAndClasses', isMandatory=True, type=Sensor, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML=('sensor',), groupNameInXML='sensors', isCollection=True, getter=lambda config, configAgain: config.sensorsAndClassesWithoutBuiltIns)
    PROPERTY_DEFINITIONS.addProperty('servicesRepository', isMandatory=False, type=ServicesRepository, xmlEntityType=Property.XMLEntityTypes.CHILD_ELEMENT, namesInXML='services')

    def __init__(self):
        # Default services repository.
        self.servicesRepository = ServicesRepository()

        # Add built-in sensor classes.
        rootClass = Sensor(None, Sensor.Type.ROOT, True)
        rootClass.isClass = True
        rootClass.activationDelay = ModeDependentValue(0)
        rootClass.activationCriterion = ActivationCriterion.makeSensorCriterion('{name}', False) # {name} is resolved for each sensor so that this criterion is true if the sensor is not triggered.
        rootClass.prealertDuration = ModeDependentValue(0)
        rootClass.alertDuration = ModeDependentValue(0)
        booleanClass = Sensor(Sensor.Type.ROOT, Sensor.Type.BOOLEAN, True)
        booleanClass.isClass = True
        booleanClass.triggerValue = True
        floatClass = Sensor(Sensor.Type.ROOT, Sensor.Type.FLOAT, True)
        floatClass.isClass = True
        self.sensorsAndClasses = [rootClass, booleanClass, floatClass]

    @staticmethod
    def parseFile(filename):
        # xsdFilename = os.path.join(os.path.dirname(__file__), 'config.xsd')
        # schema = etree.XMLSchema(file=xsdFilename)
        # parser = etree.XMLParser(schema=schema)
        # try:
            # tree = etree.parse(source=filename, parser=parser)
        # except:
            # logger.reportError('{0} parse errors.'.format(len(parser.error_log)))
            # errIx = 0
            # for err in parser.error_log:
                # errIx += 1
                # logger.reportError('#{ix}@{line}:{col} {message}'.format(ix=errIx, line=err.line, col=err.column, message=err.message))
            # raise
        doc = xml.dom.minidom.parse(filename)
        return Configuration.parse(doc)

    @staticmethod
    def parseString(string):
        doc = xml.dom.minidom.parseString(string)
        return Configuration.parse(doc)

    @staticmethod
    def parse(xmlDocument):
        config = xmlDocument.getElementsByTagName('config')[0]

        configuration = Configuration()

        context = None
        try:
            Configuration.PROPERTY_DEFINITIONS.readObjectFromXML(configuration, config)
            # # Sensors (classes and concrete ones).
            # context = 'sensors block'
            # classesIt = Configuration.getElementsInConfig(config, 'class', 'sensors')
            # sensorsIt = Configuration.getElementsInConfig(config, 'sensor', 'sensors')
            # for xmlElement in itertools.chain(classesIt, sensorsIt):
                # context = xmlElement.toxml()
                # # Consider 'name' and 'type' as optional for now. Integrity checks on the
                # # built configuration will take care of them later (which is
                # # better than checking only the XML way to define
                # # configuration).
                # sensor = Sensor(Configuration.getXmlAttribute(xmlElement, 'type', None, mustBeDefined=False), Configuration.getXmlAttribute(xmlElement, 'name', None, mustBeDefined=False))
                # sensor.isClass = xmlElement.tagName.lower() == 'class'
# 
                # # Automatically read properties that come from attributes or
                # # child elements.
                # Sensor.PROPERTY_DEFINITIONS.readObjectFromXML(sensor, xmlElement)
# 
                # # Xml attributes can be used as parameters for parameterized
                # # values in the config (this is advanced usage).
                # for k, v in xmlElement.attributes.items():
                    # sensor.addAttribute(k, v)
# 
                # configuration.addSensor(sensor)
# 
            # # Modes.
            # context = 'modes block'
            # for modesElement in Configuration.getElementsInConfig(config, 'modes', None):
                # context = modesElement.toxml()
                # ModesRepository.PROPERTY_DEFINITIONS.readObjectFromXML(configuration.modes, modesElement)
# 
            # # Alerts.
            # context = 'alerts block'
            # for alertElement in Configuration.getElementsInConfig(config, 'alert', 'alerts'):
                # context = alertElement.toxml()
                # alert = Alert(None, None)
                # Alert.PROPERTY_DEFINITIONS.readObjectFromXML(alert, alertElement)
                # configuration.addAlert(alert)

        except Configuration.IntegrityException as e:
            if e.xmlContext != None:
                e.xmlContext = context
            raise e
        except ValueError as e:
            raise Configuration.IntegrityException('An exception occurred while parsing {0}'.format(context), e)

        return configuration

    def toXml(self):
        # Creates a new empty DOM.
        doc = xml.dom.minidom.Document()
        config = doc.createElement('config')
        doc.appendChild(config)
        Configuration.PROPERTY_DEFINITIONS.toXml(self, self, doc, config)
        return doc

    @staticmethod
    def parseProperty(object, xmlElement, propertyDefinition):
        # Parse individual properties if definition is a group.
        attributeValue = Configuration.getXmlAttribute(xmlElment, attributeName, defaultAttributeValue)
        vars(object)[attributeName] = valueBuilder(attributeValue)


    @staticmethod
    def getXmlAttribute(xmlElement, attributeName, defaultValue=None, mustBeDefined=False):
        """
        Returns the value of the given element's attribute or None if element does not have such attribute.

        Unlike the getAttribute method on Element, this method does not return an empty string but None whenever attribute does not exist.
        """
        if(xmlElement.hasAttribute(attributeName)):
            return xmlElement.getAttribute(attributeName)
        else:
            if mustBeDefined:
                raise Configuration.IntegrityException('Element {0} misses attribute {1}'.format(xmlElement.tagName, attributeName), xmlContext=xmlElement.toxml() )
            else:
                return defaultValue

    @staticmethod
    def getElementsInConfig(config, sectionName, groupName):
        if not groupName is None:
            for sections in config.childNodes:
                if sections.nodeType != sections.ELEMENT_NODE or sections.tagName != groupName: continue
                for section in sections.childNodes:
                    if section.nodeType != section.ELEMENT_NODE or section.tagName != sectionName: continue
                    yield section
        else:
            for section in config.childNodes:
                if section.nodeType != section.ELEMENT_NODE or section.tagName != sectionName: continue
                yield section

    @staticmethod
    def getTextInElement(elt, mustFind = True):
        text = None
        for node in elt.childNodes:
            if node.nodeType == node.TEXT_NODE:
                if not text:
                    text = ''
                text += node.data

        if mustFind and not text:
            raise Exception('Missing text in element {0}'.format(elt.nodeName))
        return text

    def getClassesInheritedBySensor(self, sensor, includesBuiltIns=False):
        s = sensor if type(sensor) == Sensor else self._getSensorOrClassByName(sensor)
        if s.isRootType():
            return []
        else:
            inheritedClasses = self.getClassesInheritedBySensor(s.type, includesBuiltIns)
            baseClass = self.getClassByName(s.type)
            if baseClass.isBuiltIn and not includesBuiltIns:
                return inheritedClasses
            else:
                return [baseClass] + inheritedClasses

    def doesSensorInherit(self, sensor, classs):
        if isinstance(sensor, Sensor):
            s = sensor
        else:
            s = self._getSensorOrClassByName(sensor)
            if s == None:
                return False

        if isinstance(classs, Sensor):
            className = classs.name
        else:
            className = classs

        if s.isRootType():
            return False
        elif s.type == className:
            return True
        else:
            return self.doesSensorInherit(s.type, className)

    def checkIntegrity(self):
        """
        Checks that the configuration described by this object is full of integrity.

        An exception is raised if a problem is detected. Otherwise, it is safe to assume that configuration is well defined.
        """
        Configuration.PROPERTY_DEFINITIONS.checkIntegrity(self, self)

    @property
    def sensors(self):
        if not self.sensorsAndClasses: return []
        return [s for s in self.sensorsAndClasses if not s.isClass]

    @property
    def classes(self):
        if not self.sensorsAndClasses: return []
        return [s for s in self.sensorsAndClasses if s.isClass]

    @property
    def sensorsAndClassesWithoutBuiltIns(self):
        return [s for s in self.sensorsAndClasses if not s.isBuiltIn]

    def getBuiltInRootClass(self, sensorOrClass):
        if isinstance(sensorOrClass, str):
            sensorOrClass = self._getSensorOrClassByName(sensorOrClass)
        # May happen if None has been passed or if no sensor by the given name
        # could be found (can happen on a misconfigured instance of
        # homewatcher). This should not crash.
        if sensorOrClass == None: return None

        if not sensorOrClass.isBuiltIn:
            return self.getBuiltInRootClass(self.getClassByName(sensorOrClass.type))
        else:
            return sensorOrClass

    def getModeByName(self, modeName):
        modes = [m for m in self.modesRepository.modes if m.name == modeName]
        if modes:
            return modes[0]
        else:
            raise Exception('No mode {0}.'.format(modeName))

    def resolve(self, checkIntegrityWhenDone=True):
        resolvedSensors = []
        for sensor in self.sensorsAndClasses:
            if sensor.isClass:
                resolvedSensors.append(sensor)
            else:
                resolvedSensors.append(self._getResolvedSensor(sensor))

        self.sensorsAndClasses = resolvedSensors

        # Force integrity checks immediately, as this guarantees that resolution
        # did not lead to weird results.
        if checkIntegrityWhenDone: self.checkIntegrity()

    def _getResolvedSensor(self, sensor):
        if sensor.isClass: raise Exception('Sensor classes cannot be resolved.')
        resolvedCopy = Sensor(sensor.type, sensor.name, sensor.isBuiltIn)
        currentClass = sensor
        resolvedCopyVars = vars(resolvedCopy)

        # Recursively assign members from the whole ancestor branch.
        primitiveTypes = (type(None), str, int, float, bool)
        customTypes = (ModeDependentValue, ActivationCriterion)
        while currentClass != None:
            for k, v in vars(currentClass).items():
                if k == '_attributes':
                    newAttributes = v.copy()
                    newAttributes.update(resolvedCopy._attributes)
                    resolvedCopy._attributes = newAttributes
                    continue

                doesMemberExist = not(currentClass == sensor or not k in resolvedCopyVars or resolvedCopyVars[k] is None)
                if isinstance(v, primitiveTypes):
                    if not doesMemberExist:
                        resolvedCopyVars[k] = v
                elif isinstance(v, customTypes):
                    if not doesMemberExist:
                        resolvedCopyVars[k] = v.copy()
                    else:
                        resolvedCopyVars[k].inherit(v)
                else:
                    raise Exception('Unsupported member {0}={1}, type={2}'.format(k, v, type(v)))

            if not currentClass.isRootType():
                currentClass = self.getClassByName(currentClass.type)
            else:
                currentClass = None

        # # Replace the base class by the first class that still exists in the
        # # resolved configuration: this is the first builtin class. In case
        # # something goes wrong when searching for this builtin class, simply
        # # reuse the base class of the original sensor. This will not work
        # # properly but configuration's integrity checks will be more accurate.
        # builtinRootClass = self.getBuiltInRootClass(sensor.type)
        # resolvedCopy.type = sensor.type if builtinRootClass is None else builtinRootClass.name

        # Resolve parameterized string fields.
        self.resolveObject(resolvedCopy, {})
        return resolvedCopy

    def getClassByName(self, name):
        c = self._getSensorOrClassByName(name)
        if c == None or not c.isClass: return None
        return c

    def getSensorByName(self, name):
        s = self._getSensorOrClassByName(name)
        if s is None or s.isClass: return None
        return s

    def _getSensorOrClassByName(self, name):
        # Make sure we do not compare None to any sensor's name. If None is
        # passed, this query must return None even if the configuration is
        # badly defined.
        if name == None: return None
        byNames = [o for o in self.sensorsAndClasses if o.name == name]
        if len(byNames) == 0:
            return None
        elif len(byNames) > 1:
            raise Configuration.IntegrityException('Those sensors are homonymous: {0}'.format(byNames))
        else:
            return byNames[0]

    @staticmethod
    def resolveObject(obj, attributes):
        if obj is None: return obj

        # Logic: some object's members may be parameterized with attributes
        # stored in a 'attributes' dictionary. Attributes may themselves be
        # parameterized with other attributes.
        # First, resolve attributes, taking care of the priority order if
        # required. Then, resolve members. Last, resolve members that are
        # objects by passing them the dictionary of attributes as a base source
        # for attributes.
        # Notice that the attributes passed to this method are assumed to be
        # already resolved.

        # Define comparator method.
        def parameterSort(a, b):
            paramsInA = regex.findall(obj.attributes[a])
            paramsInB = regex.findall(obj.attributes[b])
            if b in paramsInA:
                if a in paramsInB:
                    raise Exception('{a} and {b} are mutually dependent.'.format(a=a, b=b))
                # b must be resolved after a.
                return 1
            elif a in paramsInB:
                # a must be resolved after b.
                return -1
            else:
                # a and b are independent.
                return 0

        # Combine object's attributes with the passed ones. Object's attributes
        # take precedence in case of name conflicts.
        combinedAttributes = attributes.copy()
        if hasattr(obj, 'attributes'):
            combinedAttributes.update(obj.attributes)

        # Resolve object's attributes that need to.
        regex = re.compile('{([a-zA-Z]\w*)}')
        if hasattr(obj, 'attributes'):
            parameterizedAttributeNames = []
            for k, v in obj.attributes.items():
                if isinstance(v, str) and regex.search(v):
                    # Store attribute name, not its value! The comparator will
                    # evaluate the attribute when needed.
                    parameterizedAttributeNames.append(k)

            # Sort attributes by order of resolution.
            parameterizedAttributeNames = sorted(parameterizedAttributeNames, key=cmp_to_key(parameterSort))

            # Resolve them.
            for attributeName in parameterizedAttributeNames:
                attrValue = obj.attributes[attributeName]
                attrValue = attrValue.format(**combinedAttributes)
                obj.attributes[attributeName] = attrValue
                combinedAttributes[attributeName] = attrValue

        # Resolve string members and internal objects.
        isString = lambda o: isinstance(o, str)
        isObject = lambda o: not isinstance(o, (type(None), int, float, bool))
        resolve = lambda v: v.format(**combinedAttributes) if isString(v) else Configuration.resolveObject(v, combinedAttributes) if isObject(v) else v
        if isinstance(obj, (list, tuple)):
            for i in range(len(obj)):
                obj[i] = resolve(obj[i])
        elif isinstance(obj, dict):
            for k, v in obj.items():
                obj[k] = resolve(v)
        else:
            objVars = vars(obj)
            for k, v in objVars.items():
                if k == 'xmlSource': continue
                objVars[k] = resolve(v)

        return obj

    def addAlert(self, alert):
        self.alerts.append(alert)

    def getAlertByName(self, name):
        if name == None: return None
        for a in self.alerts:
            if a.name == name:
                return a
        raise KeyError(name)

    @staticmethod
    def replaceParametersInString(inputString, parameters):
        """ Replaces parameters identified by their name enclosed in curly brackets by their value specified in the passed dictionary. """
        outputString = inputString
        for parameterName, parameterValue in parameters.items():
            outputString = outputString.replace('{{0}}'.format(parameterName), parameterValue)

        return outputString


