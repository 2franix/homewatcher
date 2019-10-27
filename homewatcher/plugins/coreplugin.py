import homewatcher.plugin
import homewatcher.alarm
import homewatcher.contexthandlers
from pyknx import logger

class SensorListContextHandler(homewatcher.contexthandlers.ContextHandler):
    def __init__(self, xmlConfig):
        homewatcher.contexthandlers.ContextHandler.__init__(self, xmlConfig)
        self.format = 'inline'
        if xmlConfig.hasAttribute('format'):
            formatAttribute = xmlConfig.getAttribute('format').lower()
            if not formatAttribute in ('inline', 'bulleted'):
                raise Exception('Unsupported format "{0}" for {1}'.format(formatAttribute, self.__class__.__contextHandlerName__))
            self.format = formatAttribute

    def formatSensorList(self, sensors):
        message = ''
        sensorNames = [str(s) for s in sensors]
        sensorNames.sort()
        for sensor in sensorNames:
            if self.format == 'inline':
                if message:
                    message += ','
                message += sensor
            elif self.format == 'bulleted':
                if message:
                    message += '\n'
                message += '-{0}'.format(sensor)
        return message

class SensorsStatusContextHandler(SensorListContextHandler):
    __contextHandlerName__ = 'alert.sensors-status'
    def __init__(self, xmlConfig):
        SensorListContextHandler.__init__(self, xmlConfig)
        self.targetedTypes = []
        for attrName in ['inPrealert', 'inAlert', 'inPause']:
            if not xmlConfig.hasAttribute(attrName) or xmlConfig.getAttribute(attrName).lower() == 'true':
                self.targetedTypes.append(attrName)

    def analyzeContext(self, context):
        if isinstance(context, homewatcher.alarm.Alert):
            sensors = []
            if 'inPrealert' in self.targetedTypes:
                sensors.extend(context.sensorsInPrealert)
            if 'inAlert' in self.targetedTypes:
                sensors.extend(context.sensorsInAlert)
            if 'paused' in self.targetedTypes:
                sensors.extend(context.pausedSensors)

            return self.formatSensorList(sensors)
        else:
            return ''

class EnabledSensorsContextHandler(SensorListContextHandler):
    __contextHandlerName__ = 'mode.enabled-sensors'
    def __init__(self, xmlConfig):
        SensorListContextHandler.__init__(self, xmlConfig)
        self.includesPending = False
        attrName = 'includesPending'
        if xmlConfig.hasAttribute(attrName):
            self.includesPending = xmlConfig.getAttribute(attrName).lower() == 'true'

    def analyzeContext(self, context):
        enabledSensors = [s for s in context.daemon.sensors if s.isEnabled or (self.includesPending and s.isActivationPending())]
        return self.formatSensorList(enabledSensors)

class CurrentModeContextHandler(homewatcher.contexthandlers.ContextHandler):
    __contextHandlerName__ = 'mode.current'
    def __init__(self, xmlConfig):
        homewatcher.contexthandlers.ContextHandler.__init__(self, xmlConfig)

    def analyzeContext(self, context):
        return context.daemon.currentMode.name

class AlertNameContextHandler(homewatcher.contexthandlers.ContextHandler):
    __contextHandlerName__ = 'alert.name'
    def __init__(self, xmlConfig):
        homewatcher.contexthandlers.ContextHandler.__init__(self, xmlConfig)

    def analyzeContext(self, context):
        if isinstance(context, homewatcher.alarm.Alert):
            return context.name
        else:
            raise Exception('This context handler cannot be used in the context of "{0}"'.format(context))

class CorePlugin(homewatcher.plugin.Plugin):
    """
    Core plugin that is part of the standard homewatcher package.

    It provides core functionality such as basic context handlers.
    """
    def load(self):
        contextHandlerFactory = homewatcher.contexthandlers.ContextHandlerFactory.getInstance()
        contextHandlerFactory.registerHandler(SensorsStatusContextHandler)
        contextHandlerFactory.registerHandler(EnabledSensorsContextHandler)
        contextHandlerFactory.registerHandler(CurrentModeContextHandler)
        contextHandlerFactory.registerHandler(AlertNameContextHandler)
