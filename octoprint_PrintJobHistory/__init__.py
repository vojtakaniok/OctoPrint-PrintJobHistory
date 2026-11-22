# coding=utf-8
from __future__ import absolute_import

import logging.handlers
import threading
import time

import octoprint.plugin
from octoprint.events import Events
from octoprint.util.version import is_octoprint_compatible

import datetime
import math
import flask
import os

from octoprint_PrintJobHistory.models.FilamentModel import FilamentModel
from octoprint_PrintJobHistory.models.PrintJobModel import PrintJobModel
from octoprint_PrintJobHistory.models.TemperatureModel import TemperatureModel
from octoprint_PrintJobHistory.models.CostModel import CostModel
from peewee import DoesNotExist

from .common.SettingsKeys import SettingsKeys
from .common.SlicerSettingsParser import SlicerSettingsParser
from .common.ResetAbleLogFileHandler import ResetAbleLogFileHandler
from .api.PrintJobHistoryAPI import PrintJobHistoryAPI
from .api import TransformPrintJob2JSON
from .DatabaseManager import DatabaseManager
from .CameraManager import CameraManager

from octoprint_PrintJobHistory.common import StringUtils, DateTimeUtils

class PrintJobHistoryPlugin(
	PrintJobHistoryAPI,
	octoprint.plugin.SettingsPlugin,
	octoprint.plugin.AssetPlugin,
	octoprint.plugin.TemplatePlugin,
	octoprint.plugin.StartupPlugin,
	octoprint.plugin.EventHandlerPlugin,
	octoprint.plugin.SimpleApiPlugin
):

	def initialize(self):
		self._preHeatPluginImplementation = None
		self._preHeatPluginImplementationState = None
		self._filamentManagerPluginImplementation = None
		self._filamentManagerPluginImplementationState = None
		self._displayLayerProgressPluginImplementation = None
		self._displayLayerProgressPluginImplementationState = None
		self._spoolManagerPluginImplementation = None
		self._spoolManagerPluginImplementationState = None
		self._spoolmanPluginImplementation = None
		self._spoolmanPluginImplementationState = None
		self._ultimakerFormatPluginImplementation = None
		self._ultimakerFormatPluginImplementationState = None
		self._prusaSlicerThumbnailsPluginImplementation = None
		self._prusaSlicerThumbnailsPluginImplementationState = None
		self._costEstimationPluginImplementation = None
		self._costEstimationPluginImplementationState = None
		self._printHistoryPluginImplementation = None

		pluginDataBaseFolder = self.get_plugin_data_folder()

		self._logger.info("Start initializing")
		# self.myInfoLogger("Start initializing")
		# DATABASE
		sqlLoggingEnabled = self._settings.get_boolean([SettingsKeys.SETTINGS_KEY_SQL_LOGGING_ENABLED])
		self._databaseManager = DatabaseManager(self._logger, sqlLoggingEnabled)
		self._databaseManager.initDatabase(pluginDataBaseFolder, self._sendErrorMessageToClient)

		# CAMERA
		self._cameraManager = CameraManager(self._logger)
		pluginBaseFolder = self._basefolder

		self._cameraManager.initCamera(pluginDataBaseFolder, pluginBaseFolder, self._settings)

		# Init values for initial settings view-page
		self._settings.set([SettingsKeys.SETTINGS_KEY_DATABASE_PATH], self._databaseManager.getDatabaseFileLocation())
		self._settings.set([SettingsKeys.SETTINGS_KEY_SNAPSHOT_PATH], self._cameraManager.getSnapshotFileLocation())
		self._settings.save()

		# OTHER STUFF
		self._currentPrintJobModel = None

		self.alreadyCanceled = False

		self._resetableFileLogHandler = None

		self._logger.info("Done initializing")

	def myInfoLogger(self, message):
		"Automatically log the current function details."
		import inspect
		# Get the previous frame in the stack, otherwise it would
		# be this function!!!
		func = inspect.currentframe().f_back.f_code
		# func.co_firstlineno,
		# func2 = inspect.currentframe().f_code
		# Dump the message + the name of this function to the log.
		self._logger.info("%s:%i - %s" % (
			func.co_name,
			func.co_flags,
			message
		))

	################################################################################################## private functions
	def _sendDataToClient(self, payloadDict):
		self._plugin_manager.send_plugin_message(self._identifier,
												 payloadDict)

	# popupType = 'notice', 'info', 'success', or 'error'.
	def _sendMessageToClient(self, popupType, title, message, hide=False):
		self._sendDataToClient(dict(action="messagePopUp",
									popupType=popupType,
									title=title,
									message=message,
									hide=hide))

	def _sendErrorMessageToClient(self, title, message):
		self._sendDataToClient(dict(action="errorPopUp",
									title=title,
									message=message))

	def _sendReloadTableToClient(self, shouldSend=True):
		if (shouldSend):
			payload = {
				"action": "reloadTableItems"
			}
			self._sendDataToClient(payload)

	def _checkAndLoadThirdPartyPluginInfos(self, sendToClient=False):
		pluginInfo = self._getPluginInformation(SettingsKeys.PLUGIN_PREHEAT)
		self._preHeatPluginImplementationState = pluginInfo[0]
		self._preHeatPluginImplementation = pluginInfo[1]
		preHeatCurrentVersion = pluginInfo[2]
		preHeatRequiredVersion = pluginInfo[3]

		pluginInfo = self._getPluginInformation(SettingsKeys.PLUGIN_FILAMENT_MANAGER)
		self._filamentManagerPluginImplementationState = pluginInfo[0]
		self._filamentManagerPluginImplementation = pluginInfo[1]
		filamentManagerCurrentVersion = pluginInfo[2]
		filamentManagerRequiredVersion = pluginInfo[3]

		pluginInfo = self._getPluginInformation(SettingsKeys.PLUGIN_DISPLAY_LAYER_PROGRESS)
		self._displayLayerProgressPluginImplementationState = pluginInfo[0]
		self._displayLayerProgressPluginImplementation = pluginInfo[1]
		displayLayerCurrentVersion = pluginInfo[2]
		displayLayerRequiredVersion = pluginInfo[3]

		pluginInfo = self._getPluginInformation(SettingsKeys.PLUGIN_SPOOL_MANAGER)
		self._spoolManagerPluginImplementationState = pluginInfo[0]
		self._spoolManagerPluginImplementation = pluginInfo[1]
		spoolManagerCurrentVersion = pluginInfo[2]
		spoolManagerRequiredVersion = pluginInfo[3]

		pluginInfo = self._getPluginInformation(SettingsKeys.PLUGIN_SPOOLMAN)
		self._spoolmanPluginImplementationState = pluginInfo[0]
		self._spoolmanPluginImplementation = pluginInfo[1]
		spoolmanCurrentVersion = pluginInfo[2]
		spoolmanRequiredVersion = pluginInfo[3]

		pluginInfo = self._getPluginInformation(SettingsKeys.PLUGIN_ULTIMAKER_FORMAT_PACKAGE)
		self._ultimakerFormatPluginImplementationState = pluginInfo[0]
		self._ultimakerFormatPluginImplementation = pluginInfo[1]
		ultimakerCurrentVersion = pluginInfo[2]
		ultimakerRequiredVersion = pluginInfo[3]

		pluginInfo = self._getPluginInformation(SettingsKeys.PLUGIN_PRUSA_SLICER_THUMNAIL)
		self._prusaSlicerThumbnailsPluginImplementationState = pluginInfo[0]
		self._prusaSlicerThumbnailsPluginImplementation = pluginInfo[1]
		pruseSlicerCurrentVersion = pluginInfo[2]
		pruseSlicerRequiredVersion = pluginInfo[3]

		pluginInfo = self._getPluginInformation(SettingsKeys.PLUGIN_COST_ESTIMATION)
		self._costEstimationPluginImplementationState = pluginInfo[0]
		self._costEstimationPluginImplementation = pluginInfo[1]
		costPluginCurrentVersion = pluginInfo[2]
		costPluginRequiredVersion = pluginInfo[3]

		pluginInfo = self._getPluginInformation(SettingsKeys.PLUGIN_PRINT_HISTORY)
		if ("enabled" == pluginInfo[0]):
			self._printHistoryPluginImplementation = pluginInfo[1]
		else:
			self._printHistoryPluginImplementation = None

		self._logger.info("Plugin-State:\n"
						  "| PreHeat=" + self._preHeatPluginImplementationState + " (" + str(preHeatCurrentVersion) + ")\n"
						  "| filamentmanager=" + self._filamentManagerPluginImplementationState + " (" + str(filamentManagerCurrentVersion) + ")\n"
						  "| DisplayLayerProgress=" + self._displayLayerProgressPluginImplementationState + " (" + str(displayLayerCurrentVersion) + ")\n"
						  "| SpoolManager=" + self._spoolManagerPluginImplementationState + " (" + str(spoolManagerCurrentVersion) + ")\n"
                          "| Spoolman=" + self._spoolmanPluginImplementationState + " (" + str(spoolmanCurrentVersion) + ")\n"
						  "| UltimakerFormat=" + self._ultimakerFormatPluginImplementationState + " (" + str(ultimakerCurrentVersion) + ")\n"
						  "| PrusaSlicerThumbnail=" + self._prusaSlicerThumbnailsPluginImplementationState + " (" + str(pruseSlicerCurrentVersion) + ")\n"
						  "| costestimation=" + self._costEstimationPluginImplementationState + " (" + str(costPluginCurrentVersion) + ")\n"
						  )

		if sendToClient:

			currentPluginVersion = self._plugin_info.version
			lastVersionCheck = self._settings.get([SettingsKeys.SETTINGS_KEY_LAST_PLUGIN_DEPENDENCY_CHECK])
			newPlugiVersionNotifier = False
			if (currentPluginVersion != lastVersionCheck):
				newPlugiVersionNotifier = True

			lastVersionCheck = currentPluginVersion
			self._settings.set([SettingsKeys.SETTINGS_KEY_LAST_PLUGIN_DEPENDENCY_CHECK], lastVersionCheck)
			self._settings.save()

			if (self._settings.get_boolean([SettingsKeys.SETTINGS_KEY_PLUGIN_DEPENDENCY_CHECK]) or newPlugiVersionNotifier):

				missingMessage = ""

				if self._preHeatPluginImplementation is None:
					missingMessage = missingMessage + "<li><a target='_newTab' href='https://plugins.octoprint.org/plugins/preheat/'>PreHeat Button (" + str(preHeatRequiredVersion) + "+)</a> (<b>" + self._preHeatPluginImplementationState + "</b>)</li>"

				# if at least one filemant tracker is installed, then don't inform the user about the missing other plugin
				if (self._spoolManagerPluginImplementation is None and self._filamentManagerPluginImplementation is None and self._spoolmanPluginImplementation is None):
					missingMessage = missingMessage + "<li><a target='_newTab' href='https://plugins.octoprint.org/plugins/SpoolManager/'>SpoolManager (" + str(spoolManagerRequiredVersion) + "+)</a> (<b>" + self._spoolManagerPluginImplementationState + "</b>)<br/><b>or</b></li>"
					missingMessage = missingMessage + "<li><a target='_newTab' href='https://plugins.octoprint.org/plugins/Spoolman/'>Spoolman (" + str(spoolmanRequiredVersion) + "+)</a> (<b>" + self._spoolmanPluginImplementationState + "</b>)<br/><b>or</b></li>"
					missingMessage = missingMessage + "<li><a target='_newTab' href='https://plugins.octoprint.org/plugins/filamentmanager/'>FilamentManager (" + str(filamentManagerRequiredVersion) + "+)</a> (<b>" + self._filamentManagerPluginImplementationState + "</b>)</li>"

				if self._displayLayerProgressPluginImplementation is None:
					missingMessage = missingMessage + "<li><a target='_newTab' href='https://plugins.octoprint.org/plugins/DisplayLayerProgress/'>DisplayLayerProgress (" + str(displayLayerRequiredVersion) + "+)</a> (<b>" + self._displayLayerProgressPluginImplementationState + "</b>)</li>"

				if self._ultimakerFormatPluginImplementation is None and is_octoprint_compatible("<2.0.0"):
					missingMessage = missingMessage + "<li><a target='_newTab' href='https://plugins.octoprint.org/plugins/UltimakerFormatPackage/'>Cura Thumbnails (" + str(ultimakerRequiredVersion) + "+)</a> (<b>" + self._ultimakerFormatPluginImplementationState + "</b>)</li>"

				if self._prusaSlicerThumbnailsPluginImplementation is None and is_octoprint_compatible("<2.0.0"):
					missingMessage = missingMessage + "<li><a target='_newTab' href='https://plugins.octoprint.org/plugins/prusaslicerthumbnails/'>PrusaSlicer Thumbnails (" + str(pruseSlicerRequiredVersion) + "+)</a> (<b>" + self._prusaSlicerThumbnailsPluginImplementationState + "</b>)</li>"

				if self._costEstimationPluginImplementation is None:
					missingMessage = missingMessage + "<li><a target='_newTab' href='https://plugins.octoprint.org/plugins/costestimation/'>CostEstimation (" + str(costPluginRequiredVersion) +"+)</a> (<b>" + self._costEstimationPluginImplementationState + "</b>)</li>"
					# missingMessage = missingMessage + "<li><a target='_newTab' href='https://plugins.octoprint.org/plugins/costestimation/'>CostEstimation</a> (<b>Wrong Version, expected: 3.4.0+ current: " + currentVersion + "</b>)</li>"

				if missingMessage != "":
					missingMessage = "<ul>" + missingMessage + "</ul>"
					self._sendDataToClient(dict(action="missingPlugin",
												message=missingMessage))

	def _checkForMissingFilamentTracking(self):

		currentFilamentTrackingPlugin = self._settings.get([SettingsKeys.SETTINGS_KEY_SELECTED_FILAMENTTRACKER_PLUGIN])
		# check if the current tracking plugin is known
		if (currentFilamentTrackingPlugin != SettingsKeys.KEY_SELECTED_NONE_PLUGIN and
			currentFilamentTrackingPlugin != SettingsKeys.KEY_SELECTED_SPOOLMANAGER_PLUGIN and
			currentFilamentTrackingPlugin != SettingsKeys.KEY_SELECTED_SPOOLMAN_PLUGIN and
			currentFilamentTrackingPlugin != SettingsKeys.KEY_SELECTED_FILAMENTMANAGER_PLUGIN):
			# unknown -> set to none
			self._settings.set([SettingsKeys.SETTINGS_KEY_SELECTED_FILAMENTTRACKER_PLUGIN],
							   SettingsKeys.KEY_SELECTED_NONE_PLUGIN)
			self._settings.save()

		if ( (currentFilamentTrackingPlugin == SettingsKeys.KEY_SELECTED_SPOOLMANAGER_PLUGIN) and
			 (not self._isSpoolManagerInstalledAndEnabled()) ):
			self._settings.set([SettingsKeys.SETTINGS_KEY_SELECTED_FILAMENTTRACKER_PLUGIN],
							   SettingsKeys.KEY_SELECTED_NONE_PLUGIN)
			self._settings.save()

		if ( (currentFilamentTrackingPlugin == SettingsKeys.KEY_SELECTED_SPOOLMAN_PLUGIN) and
			(not self._isSpoolmanInstalledAndEnabled()) ):
			self._settings.set([SettingsKeys.SETTINGS_KEY_SELECTED_FILAMENTTRACKER_PLUGIN],
							   SettingsKeys.KEY_SELECTED_NONE_PLUGIN)
			self._settings.save()

		if ( (currentFilamentTrackingPlugin == SettingsKeys.KEY_SELECTED_FILAMENTMANAGER_PLUGIN) and
			 (not self._isFilamentManagerInstalledAndEnabled()) ):
			self._settings.set([SettingsKeys.SETTINGS_KEY_SELECTED_FILAMENTTRACKER_PLUGIN], SettingsKeys.KEY_SELECTED_NONE_PLUGIN)
			self._settings.save()

		notifyUser = not self._settings.get_boolean([SettingsKeys.SETTINGS_KEY_NO_NOTIFICATION_FILAMENTTRACKERING_PLUGIN_SELECTION])
		if ( (self._isSpoolManagerInstalledAndEnabled() or self._isSpoolmanInstalledAndEnabled() or self._isFilamentManagerInstalledAndEnabled()) and
			 (self._settings.get([SettingsKeys.SETTINGS_KEY_SELECTED_FILAMENTTRACKER_PLUGIN]) == SettingsKeys.KEY_SELECTED_NONE_PLUGIN) ):
				# Plugins installed, but currently 'none' is selected
				self._logger.warning("Filamentracking is disabled, but some plugins are installed!")
				if (notifyUser):
					self._sendMessageToClient("notice", "Filamenttracking is possible!", "Select an tracking plugin in settings", True)
		else:
			if (self._settings.get([SettingsKeys.SETTINGS_KEY_SELECTED_FILAMENTTRACKER_PLUGIN]) == SettingsKeys.KEY_SELECTED_NONE_PLUGIN):
				if (notifyUser):
					self._sendMessageToClient("notice", "Filamenttracking not possible!",
											  "No tracking plugin is installed/enabled", True)

	def _isSpoolManagerInstalledAndEnabled(self):
		return True if self._spoolManagerPluginImplementation is not None and self._spoolManagerPluginImplementationState == "enabled" else False

	def _isSpoolmanInstalledAndEnabled(self):
		return True if self._spoolmanPluginImplementation is not None and self._spoolmanPluginImplementationState == "enabled" else False

	def _isFilamentManagerInstalledAndEnabled(self):
		return True if self._filamentManagerPluginImplementation is not None and self._filamentManagerPluginImplementationState == "enabled" else False

	def _isCostEstimationInstalledAndEnabled(self):
		return True if self._costEstimationPluginImplementation is not None and self._costEstimationPluginImplementationState == "enabled" else False

	def _isPreHeatInstalledAndEnabled(self):
		return True if self._preHeatPluginImplementation is not None and self._preHeatPluginImplementationState == "enabled" else False



	# get the plugin with status information
	# [0] == status-string
	# [1] == implementaiton of the plugin
	# [2] == version of the plugin, as str like 3.3.0
	# [3] == requiredVersion of the plugin, as str like 1.3.0
	def _getPluginInformation(self, pluginInfo):
		pluginKey = pluginInfo["key"]
		requiredVersion = pluginInfo["minVersion"]

		status = None
		implementation = None
		version = None

		if pluginKey in self._plugin_manager.plugins:
			plugin = self._plugin_manager.plugins[pluginKey]
			if plugin is not None:
				if (plugin.enabled):
					status = "enabled"
					# for OP 1.4.x we need to check agains "icompatible"-attribute
					if (hasattr(plugin, 'incompatible')):
						if (not plugin.incompatible):
							implementation = plugin.implementation
						else:
							status = "incompatible"
					else:
						# OP 1.3.x
						implementation = plugin.implementation
					pass
				else:
					status = "disabled"
				version = plugin.version
		else:
			status = "missing"

		# Check requiredVersion, if not compatible --> implementation None
		if (requiredVersion is not None and version is not None):
			canBeUsed = False
			try:
				comparabelVersion = self._get_comparable_version_semantic(version)
				comparabelRequiredVersion = self._get_comparable_version_semantic(requiredVersion)
				canBeUsed = comparabelVersion >= comparabelRequiredVersion
			except (ValueError):
				logging.exception("Something is wrong with the " +pluginKey+ " version numbers")

			if (not canBeUsed):
				status = "wrong version"
				implementation = None
		return [status, implementation, version, requiredVersion]

	def _get_comparable_version_semantic(self, version_string, force_base=False):
		import semantic_version
		version = semantic_version.Version.coerce(version_string, partial=False)
		if force_base:
			version_string = "{}.{}.{}".format(version.major, version.minor, version.patch)
			version = semantic_version.Version.coerce(version_string, partial=False)

		return version

	# Grabs all informations for the filament attributes
	def _createAndAssignFilamentModel(self, printJob, payload):

		self._logger.info("----- Start reading filament -----")
		filePath = payload["path"]
		fileData = self._file_manager.get_metadata(payload["origin"], filePath)

		# - grab calcualted data for each tool
		# - grap measured data for each tool
		filamentCalculatedDict = self._readCalculatedFilamentMetaData(fileData)
		filamentExtrusionArray = self._readMeasuredFilament()
		selectedSpoolDataDict = self._getSelectedSpools()
		# isMultiToolPrint = len(filamentCalculatedDict) > 1

		# - add always "total"
		calculatedTotalLength = 0.0

		totalFilamentModel = FilamentModel()
		totalFilamentModel.toolId = "total"
		printJob.addFilamentModel(totalFilamentModel)

		# - assign all spool informations to total
		allSpoolNames = ""
		allVendors = ""
		allMaterials = ""

		# - assign calculated values
		if (filamentCalculatedDict is not None):

			for toolId in filamentCalculatedDict:
				filamentModel = FilamentModel()
				filamentModel.toolId = toolId

				calculatedLength = filamentCalculatedDict[toolId]["length"]
				# not needed calculatedVolumne = filamentCalculatedDict[toolId]["volume"]

				filamentModel.calculatedLength = calculatedLength
				calculatedTotalLength = calculatedTotalLength + calculatedLength
				printJob.addFilamentModel(filamentModel)

				# Assign SpoolData (e.g. Name) for the calculated tools (only for calc-lenght > 0)
				# get spool data, if available
				if (calculatedLength > 0 and selectedSpoolDataDict is not None and toolId in selectedSpoolDataDict):
					spoolData = selectedSpoolDataDict[toolId]

					filamentModel.spoolName = spoolData["spoolName"]
					filamentModel.vendor = spoolData["vendor"]
					filamentModel.material = spoolData["material"]
					filamentModel.diameter = spoolData["diameter"]
					filamentModel.density = spoolData["density"]

					filamentModel.spoolCost = spoolData["spoolCost"]
					filamentModel.weight = spoolData["weight"]

					if (filamentModel.spoolName is not None and filamentModel.spoolName not in allSpoolNames):
						if (allSpoolNames != ""):
							allSpoolNames = allSpoolNames + ", "
						allSpoolNames = allSpoolNames + filamentModel.spoolName

					if (filamentModel.vendor is not None and filamentModel.vendor not in allVendors):
						if (allVendors != ""):
							allVendors = allVendors + ", "
						allVendors = allVendors + filamentModel.vendor

					if (filamentModel.material is not None and filamentModel.material not in allMaterials):
						if (allMaterials != ""):
							allMaterials = allMaterials + ", "
						allMaterials = allMaterials + filamentModel.material
				pass

		totalFilamentModel.calculatedLength = calculatedTotalLength
		totalFilamentModel.spoolName = allSpoolNames
		totalFilamentModel.vendor = allVendors
		totalFilamentModel.material = allMaterials

		# - assign measured values
		if (filamentExtrusionArray is not None):
			usedTotalLength = 0.0
			usedTotaWeight = 0.0
			usedTotalCost = 0.0
			toolIndex = 0
			for usedLength in filamentExtrusionArray:
				toolId = "tool" + str(toolIndex)
				filamentModel = printJob.getFilamentModelByToolId(toolId)
				if (filamentModel is None):
					filamentModel = FilamentModel()
					filamentModel.toolId = toolId
					printJob.addFilamentModel(filamentModel)

				filamentModel.toolId = toolId
				filamentModel.usedLength = usedLength
				usedTotalLength = usedTotalLength + usedLength

				filamentModel.usedWeight = self._calculateFilamentWeightForLength(usedLength,
																				  filamentModel.diameter,
																				  filamentModel.density)
				usedTotaWeight = usedTotaWeight + filamentModel.usedWeight

				if (filamentModel.spoolCost is not None and
					filamentModel.weight is not None and
					filamentModel.usedWeight is not None):
					filamentModel.usedCost = (filamentModel.spoolCost / filamentModel.weight) * filamentModel.usedWeight
					usedTotalCost = usedTotalCost + filamentModel.usedCost

				self._logger.info(toolId + ": usedLength='"+str(usedLength)+"'; usedWeight='"+str(filamentModel.usedWeight)+"'; usedCost='"+str(filamentModel.usedCost)+"'")

				toolIndex = toolIndex + 1
			# - add total values
			filamentModel = printJob.getFilamentModelByToolId("total")
			if (filamentModel is None):
				filamentModel = FilamentModel()
				filamentModel.toolId = "total"
				printJob.addFilamentModel(filamentModel)

			totalFilamentModel.usedLength = usedTotalLength
			totalFilamentModel.usedWeight = usedTotaWeight
			totalFilamentModel.usedCost = usedTotalCost

			self._logger.info("total: usedTotalLength='"+str(usedTotalLength)+"'; usedTotaWeight='"+str(usedTotaWeight)+"'; usedTotalCost='"+str(usedTotalCost)+"'")


	# read the total extrusion of each tool, like this
	# return [123.123, 234.234, 0, 0]
	def _readMeasuredFilament(self):
		result = None
		# get some data from the selected filament tracker plugin
		filamentTrackerPlugin = self._settings.get([SettingsKeys.SETTINGS_KEY_SELECTED_FILAMENTTRACKER_PLUGIN])
		if (SettingsKeys.KEY_SELECTED_SPOOLMANAGER_PLUGIN == filamentTrackerPlugin):
			# get data from SPOOLMANAGER
			try:
				result = self._spoolManagerPluginImplementation.api_getExtrusionAmount()
			except:
				self._logger.warning("You don't use the latest SpoolManager Version 1.4+")
			if (result is None):
				# try the old way
				result = self._spoolManagerPluginImplementation.myFilamentOdometer.getExtrusionAmount()
			pass
		elif (SettingsKeys.KEY_SELECTED_SPOOLMAN_PLUGIN == filamentTrackerPlugin):
			# get data from SPOOLMAN

			# TODO: should be replaced with a proper exposed function call
			# Currently, we rely on the fact, that the PRINT_DONE event of this plugin is executed before Spoolman.
			# Spoolman clears the extrusionAmount after handling the PRINT_DONE event.
			peek_stats_helpers = self._spoolmanPluginImplementation.lastPrintOdometerLoad.send(False)
			current_extrusion_stats = peek_stats_helpers['get_current_extrusion_stats']()
			result = current_extrusion_stats['extrusionAmount'][:]

			pass
		elif (SettingsKeys.KEY_SELECTED_FILAMENTMANAGER_PLUGIN == filamentTrackerPlugin):
			# myFilamentOdometer, since FilamentManager V1.7.2
			result = self._filamentManagerPluginImplementation.myFilamentOdometer.getExtrusionAmount()
			pass
		else:
			self._logger.info("There is no plugin for filament tracking available. Installed and Enabled?")
		return result

	# dict of this
	# {u'tool4': {u'volume': 185.20129656279946, u'length': 76997.75167999369},
	#  u'tool3': {u'volume': 0.0, u'length': 0.0}, u'tool2': {u'volume': 0.0, u'length': 0.0},
	#  u'tool1': {u'volume': 0.0, u'length': 0.0}, u'tool0': {u'volume': 0.0, u'length': 0.0}}

	def _readCalculatedFilamentMetaData(self, fileData):
		filamentAnalyseDict = None
		if "analysis" in fileData:
			if "filament" in fileData["analysis"]:
				filamentAnalyseDict = fileData["analysis"]["filament"]
		if (filamentAnalyseDict is None):
			self._logger.info("There is no calculated filament data in meta-file")
		return filamentAnalyseDict

	# read the selected tools
	# return  {
	# 'tool0': {'databaseId': 4711, 'spoolName': 'NewSpool', 'weight': 2000.0, 'spoolCost': 123.2, 'material': 'PLA', 'vendor: 'MaterMost', 'density': 4.25, 'diameter': 1.75, },
	# 'tool1': {}
	# },
	def _getSelectedSpools(self):
		result = None
		# get some data from the selected filament tracker plugin
		filamentTrackerPlugin = self._settings.get([SettingsKeys.SETTINGS_KEY_SELECTED_FILAMENTTRACKER_PLUGIN])
		if (SettingsKeys.KEY_SELECTED_SPOOLMANAGER_PLUGIN == filamentTrackerPlugin):
			self._logger.info("Try reading filament from SpoolManager...")
			# get data from SPOOLMANAGER
			selectedSpoolInformations = self._spoolManagerPluginImplementation.api_getSelectedSpoolInformations()
			if (selectedSpoolInformations is not None):
				result = {}
				for spoolData in selectedSpoolInformations:
					if (spoolData is not None):
						toolId = "tool" + str(spoolData["toolIndex"])
						databaseId = spoolData["databaseId"]
						spoolName = spoolData["spoolName"]
						weight = spoolData["weight"]
						spoolCost = spoolData["cost"]

						material = spoolData["material"]
						vendor = spoolData["vendor"]
						density = spoolData["density"]
						diameter = spoolData["diameter"]

						result[toolId] = {
							"databaseId": databaseId,
							"spoolName": spoolName,
							"material": material,
							"vendor":  vendor,
							"density": density,
							"diameter":  diameter,
							"spoolCost": spoolCost,
							"weight": weight
						}
						self._logger.info(
							" reading for '" + toolId + "',  Spool: '" + spoolName + "', Material: '" + material + "', Vendor: '" + vendor + "'")
			pass
		elif (SettingsKeys.KEY_SELECTED_SPOOLMAN_PLUGIN == filamentTrackerPlugin):
			self._logger.info("Try reading filament from Spoolman...")
			# get data from SPOOLMAN

			# TODO: should be replaced with a proper exposed function call
			# Especially getting the selected spools via a protected _settings variable is BAD
			spools_available = self._spoolmanPluginImplementation.getSpoolmanConnector().handleGetSpoolsAvailable()
			selected_spool_ids = self._spoolmanPluginImplementation._settings.get(['selectedSpoolIds'])

			spool_by_id = {str(spool['id']): spool for spool in spools_available['data']['spools']}

			spools = {}
			for tool_id, spool_id in selected_spool_ids.items():
				spool = spool_by_id.get(spool_id['spoolId'])
				if spool:
					spools[tool_id] = spool
				else:
					spools[tool_id] = None

			result = {}
			for toolId, spoolData in spools.items():
				if (spoolData is not None):
					toolId = "tool" + toolId
					spoolName = spoolData["filament"]["name"]
					weight = spoolData["filament"]["weight"]
					spoolCost = spoolData["price"]

					material = spoolData["filament"]["material"]
					vendor = spoolData["filament"]["vendor"]["name"]
					density = spoolData["filament"]["density"]
					diameter = spoolData["filament"]["diameter"]

					result[toolId] = {
						"spoolName": spoolName,
						"material": material,
						"vendor":  vendor,
						"density": density,
						"diameter":  diameter,
						"spoolCost": spoolCost,
						"weight": weight
					}
					self._logger.info(
						" reading for '" + toolId + "',  Spool: '" + spoolName + "', Material: '" + material + "', Vendor: '" + vendor + "'")
			pass
		elif (SettingsKeys.KEY_SELECTED_FILAMENTMANAGER_PLUGIN == filamentTrackerPlugin):
			self._logger.info("Try reading filament from FilamentManager...")
			# myFilamentOdometer, since FilamentManager V1.7.2
			selectedSpools = self._filamentManagerPluginImplementation.filamentManager.get_all_selections(self._filamentManagerPluginImplementation.client_id)
			if selectedSpools is not None and len(selectedSpools) > 0:
				result = {}
				for currentSpoolData in selectedSpools:
					toolId = "tool" + str(currentSpoolData["tool"])
					spoolData = currentSpoolData["spool"]
					databaseId = spoolData["id"]
					spoolName = spoolData["name"]
					weight = spoolData["weight"]
					spoolCost = spoolData["cost"]

					profileData = spoolData["profile"]
					material = profileData["material"]
					vendor = profileData["vendor"]
					density = profileData["density"]
					diameter = profileData["diameter"]

					result[toolId] = {
						"databaseId": databaseId,
						"spoolName": spoolName,
					    "material": material,
					    "vendor":  vendor,
					    "density": density,
					  	"diameter":  diameter,
						"spoolCost": spoolCost,
						"weight": weight
					}
					self._logger.info(" reading for '"+toolId+"',  Spool: '"+spoolName+"', Material: '"+material+"', Vendor: '"+vendor+"'")
					pass
			pass
		else:
			self._logger.info("There is no plugin for spool selection. Installed and Enabled?")
		return result

	def _calculateFilamentWeightForLength(self, usedLength, diameter, density):
		result = 0.0
		if (usedLength is not None and diameter is not None and density is not None):
			radius = diameter / 2.0
			volume = usedLength * math.pi * radius * radius / 1000.0
			result = volume * density
		return result


	def _updatePrintJobModelWithLayerHeightInfos(self, dlpPayload):
		totalLayers = dlpPayload["totalLayer"]
		currentLayer = dlpPayload["currentLayer"]
		self._currentPrintJobModel.printedLayers = currentLayer + " / " + totalLayers

		totalHeight = dlpPayload["totalHeightFormatted"]
		currentHeight = dlpPayload["currentHeightFormatted"]
		self._currentPrintJobModel.printedHeight = currentHeight + " / " + totalHeight


	def _createPrintJobModel(self, payload):
		self._currentPrintJobModel = PrintJobModel()
		self._currentPrintJobModel.printStartDateTime = datetime.datetime.now()

		self._currentPrintJobModel.fileOrigin = payload["origin"]
		self._currentPrintJobModel.fileName = payload["name"]
		self._currentPrintJobModel.filePathName = payload["path"]

		# self._file_manager.path_on_disk()
		if "owner" in payload:
			self._currentPrintJobModel.userName = payload["owner"]
		else:
			self._currentPrintJobModel.userName = "John Doe"
		self._currentPrintJobModel.fileSize = payload["size"]

		tempFound = False
		toolId = self._settings.get([SettingsKeys.SETTINGS_KEY_DEFAULT_TOOL_ID])
		tempTool = -1
		tempBed = 0

		shouldReadTemperatureFromPreHeat = self._settings.get_boolean(
			[SettingsKeys.SETTINGS_KEY_TAKE_TEMPERATURE_FROM_PREHEAT])
		if (shouldReadTemperatureFromPreHeat):
			self._logger.info("Try reading Temperature from PreHeat-Plugin...")

			if (self._preHeatPluginImplementation is not None):
				path_on_disk = octoprint.server.fileManager.path_on_disk(self._currentPrintJobModel.fileOrigin,
																		 self._currentPrintJobModel.filePathName)

				preHeatTemperature = self._preHeatPluginImplementation.read_temperatures_from_file(path_on_disk)
				if preHeatTemperature is not None:
					if "bed" in preHeatTemperature:
						tempBed = preHeatTemperature["bed"]
						tempFound = True
					if toolId in preHeatTemperature:
						tempTool = preHeatTemperature[toolId]  # "tool0"
						tempFound = True
					else:
						self._logger.warning(
							"... PreHeat-Temperatures does not include default Extruder-Tool '" + toolId + "'")
				pass
			else:
				self._logger.warning("... PreHeat Button Plugin not installed/enabled")

		if (tempFound):
			self._logger.info(
				"... Temperature found '" + str(tempBed) + "' Tool '" + toolId + "' '" + str(tempTool) + "'")
			self._addTemperatureToPrintModel(self._currentPrintJobModel, tempBed, toolId, tempTool)
		else:
			# readTemperatureFromPrinter
			# because temperature is 0 at the beginning, we need to wait a couple of seconds (maybe 3)
			self._readAndAssignCurrentTemperatureDelayed(self._currentPrintJobModel)


	def _readCurrentTemperatureFromPrinterAsync(self, printer, printJobModel, addTemperatureToPrintModel):
		dealyInSeconds = self._settings.get_int([SettingsKeys.SETTINGS_KEY_DELAY_READING_TEMPERATURE_FROM_PRINTER])
		time.sleep(dealyInSeconds)

		currentTemps = printer.get_current_temperatures()
		if (currentTemps is not None and "bed" in currentTemps and "tool0" in currentTemps):
			tempBed = currentTemps["bed"]["target"]
			# Maybe an other tool should be used.
			toolId = self._settings.get([SettingsKeys.SETTINGS_KEY_DEFAULT_TOOL_ID])  # "tool0"
			tempTool = -1
			try:
				tempTool = currentTemps[toolId]["target"]
			except Exception as e:
				self._logger.error("Could not read temperature from Tool '" + toolId + "'", e)

			self._logger.info(
				"Temperature read from Printer Bed: '" + str(tempBed) +
				"' Tool " + toolId + ": '" + str(tempTool) + "' after a delay of '"+str(dealyInSeconds)+"' seconds")
			addTemperatureToPrintModel(printJobModel, tempBed, toolId, tempTool)


	def _readAndAssignCurrentTemperatureDelayed(self, printJobModel):
		thread = threading.Thread(name='ReadCurrentTemperature',
								  target=self._readCurrentTemperatureFromPrinterAsync,
								  args=(self._printer, printJobModel, self._addTemperatureToPrintModel,))
		thread.daemon = True
		thread.start()
		pass


	def _addTemperatureToPrintModel(self, printJobModel, bedTemp, toolId, toolTemp):
		tempModel = TemperatureModel()
		tempModel.sensorName = "bed"
		# tempModel.sensorValue = bedTemp if bedTemp is not None else"-"
		tempModel.sensorValue = bedTemp if bedTemp is not None else "-"
		printJobModel.addTemperatureModel(tempModel)

		tempModel = TemperatureModel()
		tempModel.sensorName = toolId  # "tool0"
		tempModel.sensorValue = toolTemp if toolTemp is not None else "-"
		printJobModel.addTemperatureModel(tempModel)


	def _addCostsToPrintModel(self, printJobModel):

		self._logger.info("----- Start reading costs -----")
		#             var costData = {
		#                 filename: filename,
		#                 filepath: filepath,
		#                 costResult: costResult,
		#                 filamentCost: filamentCost,
		#                 electricityCost: electricityCost,
		#                 printerCost: printerCost,
		#                 otherCostLabel: otherCostLabel,
		#                 otherCost: otherCost,
		#             }
		if (self._isCostEstimationInstalledAndEnabled()):
			# self._logger.info("Try reading Costs from CostEstimation-Plugin")
			# costData = self._costEstimationPluginImplementation.api_getCurrentCostsValues()

			# TODO own cost calculation
			printTimeInSeconds = DateTimeUtils.calcDurationInSeconds(printJobModel.printEndDateTime, printJobModel.printStartDateTime)
			allFilamentModels = printJobModel.getFilamentModels(withoutTotal=True)
			self._logger.info("Try calculating Costs with CostEstimation-Plugin settings")
			costData = self._calculateCostData(allFilamentModels , printTimeInSeconds)

			totalCosts = costData["totalCosts"]	# float = 11.96
			filamentCost = costData["filamentCost"] # float = 0.06002333...
			electricityCost = costData["electricityCost"] # float = 0.0213454...
			printerCost = costData["printerCost"] # float = 11.87653993...
			# otherCostLabel = costData["otherCostLabel"] # str = Delivery
			# otherCost = costData["otherCost"] # float = 11.87653993...
			withDefaultSpoolValues = costData["withDefaultSpoolValues"] # boolean

			costModel = CostModel()
			costModel.totalCosts = totalCosts
			costModel.filamentCost = filamentCost
			costModel.electricityCost = electricityCost
			costModel.printerCost = printerCost
			# costModel.otherCostLabel = otherCostLabel
			# costModel.otherCost = otherCost
			costModel.withDefaultSpoolValues = withDefaultSpoolValues

			printJobModel.setCosts(costModel)
			if ("filename" in costData):
				costData.pop("filename")
			if ("filepath" in costData):
				costData.pop("filepath")
			self._logger.info("Adding costs from CostEstimation-Plugin: "+ str(costData))
		else:
			self._logger.info("Costs could not captured, because CostEstimation-Plugin not installed/enabled")

		pass


	def _calculateCostData(self, allFilamentModels, printTimeInSeconds):
		#             var costData = {
		#                 totalCosts:
		#                 filamentCost: filamentCost,
		#                 electricityCost: electricityCost,
		#                 printerCost: printerCost,
		# 				  withDefaultSpoolValues
		#             }

		withDefaultSpoolValues = False
		printTimeInHours = printTimeInSeconds / 3600

		# read cost-settings froom Cost-Plugin

		# calc: electricityCost
		electricityCost = None
		powerConsumption = self._costEstimationPluginImplementation._settings.get(["powerConsumption"]) # kW
		costOfElectricity = self._costEstimationPluginImplementation._settings.get(["costOfElectricity"]) # Euro/kWh

		powerConsumption = StringUtils.transformToFloatOrNone(powerConsumption)
		costOfElectricity = StringUtils.transformToFloatOrNone(costOfElectricity)
		if (powerConsumption is None or costOfElectricity is None):
			self._logger.error(
				"Could not calculate electricityCost, because powerConsumption or costOfElectricity is none")
		else:
			costPerHour = powerConsumption * costOfElectricity
			electricityCost = costPerHour * printTimeInHours
			self._logger.info("costPerHour '"+str(costPerHour)+"' = powerConsumption '"+str(powerConsumption)+"' * costOfElectricity '"+str(costOfElectricity)+"'" )
			self._logger.info("electricityCost '"+str(electricityCost)+"' = costPerHour '"+str(costPerHour)+"' * printTimeInHours '"+str(printTimeInHours)+"'" )

		# calc: printerCost
		printerCost = None
		priceOfPrinter = self._costEstimationPluginImplementation._settings.get(["priceOfPrinter"]) # Euro
		lifespanOfPrinter = self._costEstimationPluginImplementation._settings.get(["lifespanOfPrinter"]) # h
		maintenanceCosts = self._costEstimationPluginImplementation._settings.get(["maintenanceCosts"]) # Euro/h

		priceOfPrinter = StringUtils.transformToFloatOrNone(priceOfPrinter)
		lifespanOfPrinter = StringUtils.transformToFloatOrNone(lifespanOfPrinter)
		maintenancePerHour = StringUtils.transformToFloatOrNone(maintenanceCosts)

		if (priceOfPrinter is None or lifespanOfPrinter is None or maintenancePerHour is None):
			self._logger.error(
				"Could not calculate printerCost, because purchasePrice or lifespanOfPrinter or maintenancePerHour is none")
		else:
			# 	value_when_true if condition else value_when_false
			depreciationPerHour = priceOfPrinter / lifespanOfPrinter if lifespanOfPrinter > 0 else 0
			printerCost = (depreciationPerHour + maintenancePerHour) * printTimeInHours
			self._logger.info("printerCost '"+str(printerCost)+"' = (depreciationPerHour '"+str(depreciationPerHour)+"' + maintenancePerHour '"+str(maintenancePerHour)+"') * printTimeInHours '"+str(printTimeInHours)+"'" )

		# calc: filamentCost
		filamentCost = None
		# - do we have measured filament values or should we use default values
		costOfFilament = None
		weightOfFilament = None
		densityOfFilament = None
		diameterOfFilament = None
		if (allFilamentModels is None):
			#  filament default values
			self._logger.error("No measured/needed filament present. FilamentCost calculation not possible. Maybe metadata not assigned in json file.")
		else:

			# do we have fillamennt-informations for cost-calculation, if not use default filament parameters
			# we need:
			# 1. used filament (per tool)
			# 2. diameterOfFilament
			# 3. densityOfFilament
			# 4. spooldata (costOfFilament, weightOfFilament)
			# if 1 is not available -> skip
			# if 2,3 or 4 not available use default values from cost-plugin

			if (allFilamentModels[0].usedLength is None):
				self._logger.error(
					"No used filament present. FilamentCost calculation not possible. Maybe no filament tracker, like SpoolManager installed.")
			else:
				calcWithDefaultValuesPossible = None
				self._logger.info("Trying to read default filament values, for 'fallback-calculation'")
				default_costOfFilament = self._costEstimationPluginImplementation._settings.get(["costOfFilament"])  # Euro
				default_weightOfFilament = self._costEstimationPluginImplementation._settings.get(["weightOfFilament"])  # g
				default_densityOfFilament = self._costEstimationPluginImplementation._settings.get(["densityOfFilament"])  # g/cm3
				default_diameterOfFilament = self._costEstimationPluginImplementation._settings.get(["diameterOfFilament"])  # mm

				default_costOfFilament = StringUtils.transformToFloatOrNone(default_costOfFilament)
				default_weightOfFilament = StringUtils.transformToFloatOrNone(default_weightOfFilament)
				default_densityOfFilament = StringUtils.transformToFloatOrNone(default_densityOfFilament)
				default_diameterOfFilament = StringUtils.transformToFloatOrNone(default_diameterOfFilament)
				if (default_costOfFilament is None or default_weightOfFilament is None or default_densityOfFilament is None or default_diameterOfFilament is None):
					self._logger.warning(
						"Fallback calculation for filamentCost not possible, because Default costOfFilament or weightOfFilament or densityOfFilament is diameterOfFilament none")
					calcWithDefaultValuesPossible = False
				else:
					calcWithDefaultValuesPossible = True

				for filamentModel in allFilamentModels:
					usedLength = filamentModel.usedLength
					toolId = filamentModel.toolId # tool0
					diameterOfFilament = filamentModel.diameter
					densityOfFilament = filamentModel.density
					costOfFilament = filamentModel.spoolCost
					weightOfFilament = filamentModel.weight

					if (usedLength is None or usedLength == 0.0):
						self._logger.info("No filament calculation for '"+toolId+"', because usedLength is 0")
						continue

					if (diameterOfFilament is None):
						if (calcWithDefaultValuesPossible):
							self._logger.info("No filament diameter from filamenttracker, using default '"+str(default_diameterOfFilament)+"'")
							diameterOfFilament = default_diameterOfFilament
							withDefaultSpoolValues = True
						else:
							self._logger.info(
								"No filament diameter from filamenttracker or as default value")
							continue
					if (densityOfFilament is None):
						if (calcWithDefaultValuesPossible):
							self._logger.info("No filament densityOfFilament from filamenttracker, using default '"+str(default_densityOfFilament)+"'")
							densityOfFilament = default_densityOfFilament
							withDefaultSpoolValues = True
						else:
							self._logger.info(
								"No filament densityOfFilament from filamenttracker or as default value")
							continue
					if (costOfFilament is None):
						if (calcWithDefaultValuesPossible):
							self._logger.info("No filament costOfFilament from filamenttracker, using default '"+str(default_costOfFilament)+"'")
							costOfFilament = default_costOfFilament
							withDefaultSpoolValues = True
						else:
							self._logger.info(
								"No filament costOfFilament from filamenttracker or as default value")
							continue
					if (weightOfFilament is None):
						if (calcWithDefaultValuesPossible):
							self._logger.info("No filament weightOfFilament from filamenttracker, using default '"+str(default_weightOfFilament)+"'")
							weightOfFilament = default_weightOfFilament
							withDefaultSpoolValues = True
						else:
							self._logger.info(
								"No filament weightOfFilament from filamenttracker or as default value")
							continue

					self._logger.info("Filament cost calculation for '" + toolId + "'")
					# calculated used cost of this curretn tool
					costPerWeight =  costOfFilament / weightOfFilament
					self._logger.info("Cost per weight '"+str(costPerWeight)+"' =  costOfFilament '"+str(costOfFilament)+"' / weightOfFilament '"+str(weightOfFilament)+"'")
					volumeWeight =  self._calculateFilamentWeightForLength(usedLength, diameterOfFilament, densityOfFilament)
					filamentCost = StringUtils.transformToFloatOrZero(filamentCost) + (costPerWeight * volumeWeight)
					self._logger.info("filamentCost '"+str(filamentCost)+"' = costPerWeight '"+str(costPerWeight)+"' * volumeWeight '"+str(volumeWeight)+"'")
					pass

		# calc: totalCost

		totalCost = StringUtils.transformToFloatOrZero(filamentCost) + StringUtils.transformToFloatOrZero(electricityCost) + StringUtils.transformToFloatOrZero(printerCost)
		self._logger.info("totalcost = '"+str(totalCost)+"'")

		costData = dict(
						totalCosts=totalCost,
						# filamentCost=filamentCost,
						filamentCost=filamentCost,
						electricityCost=electricityCost,# done
			 			printerCost=printerCost,
						withDefaultSpoolValues=withDefaultSpoolValues
		)
		return costData

	def _printJobStarted(self, payload):
		self._resetableFileLogHandler.resetLog()
		self._resetableFileLogHandler.startLogging()

		self._logger.info("PrintJob '" + payload["name"] + "' started!")

		self.alreadyCanceled = False
		self._createPrintJobModel(payload)

	#### print job finished
	# printStatus = "success", "failed", "canceled"
	def _printJobFinished(self, printStatus, payload):
		self._logger.info("PrintJob finished!")

		self._capturePrintJobData(printStatus, payload)

	def _capturePrintJobData(self, printStatus, payload):
		captureMode = self._settings.get([SettingsKeys.SETTINGS_KEY_CAPTURE_PRINTJOBHISTORY_MODE])
		self._logger.info("Print result:" + printStatus + ", CaptureMode:" + captureMode)

		if (captureMode == SettingsKeys.KEY_CAPTURE_PRINTJOBHISTORY_MODE_NONE):
			self._logger.info("PrintJob not captured, because it is not enabled in plugin settings")
			return None

		captureThePrint = False
		if (captureMode == SettingsKeys.KEY_CAPTURE_PRINTJOBHISTORY_MODE_ALWAYS):
			captureThePrint = True
		else:
			# check status is neccessary
			if (printStatus == "success"):
				captureThePrint = True

		databaseId = None
		payLoadForClient = None
		# capture the print
		if (captureThePrint):
			self._logger.info("----- Start capturing print job data... -----")

			# - Core Data
			self._currentPrintJobModel.printEndDateTime = datetime.datetime.now()
			self._currentPrintJobModel.duration = (
					self._currentPrintJobModel.printEndDateTime - self._currentPrintJobModel.printStartDateTime).total_seconds()
			self._currentPrintJobModel.printStatusResult = printStatus

			# - Slicer Settings
			selectedFilename = payload.get("path")
			selectedFile = self._file_manager.path_on_disk(payload.get("origin"), selectedFilename)
			slicerSettingsExpressions = self._settings.get([SettingsKeys.SETTINGS_KEY_SLICERSETTINGS_KEYVALUE_EXPRESSION])
			if (slicerSettingsExpressions is not None and len(slicerSettingsExpressions) != 0):
				slicerSettings = SlicerSettingsParser(self._logger).extractSlicerSettings(selectedFile, slicerSettingsExpressions)
				if (slicerSettings.settingsAsText is not None and len(slicerSettings.settingsAsText) != 0):
					self._currentPrintJobModel.slicerSettingsAsText = slicerSettings.settingsAsText

			# - Image / Thumbnail
			self._grabImage(payload)

			# - FilamentInformations e.g. length
			self._createAndAssignFilamentModel(self._currentPrintJobModel, payload)

			# - Costs
			self._addCostsToPrintModel(self._currentPrintJobModel)

			# store everything in the database
			self._logger.info("----- Try storing printjob model ----")
			databaseId = self._databaseManager.insertPrintJob(self._currentPrintJobModel)
			if (databaseId is None):
				self._logger.error("PrintJob not captured, see previous error log!")
				return None
			printJobItem = None
			if self._settings.get_boolean([SettingsKeys.SETTINGS_KEY_SHOW_PRINTJOB_DIALOG_AFTER_PRINT]):

				self._settings.set_int([SettingsKeys.SETTINGS_KEY_SHOW_PRINTJOB_DIALOG_AFTER_PRINT_JOB_ID], databaseId)
				self._settings.save()

				# inform client to show job edit dialog
				printJobModel = self._databaseManager.loadPrintJob(databaseId)

				# check the correct status (redundent code, see event client_open)
				printJobItem = None
				showDisplayAfterPrintMode = self._settings.get(
					[SettingsKeys.SETTINGS_KEY_SHOWPRINTJOBDIALOGAFTERPRINT_MODE])
				printJobModelStatus = printJobModel.printStatusResult

				if (showDisplayAfterPrintMode == SettingsKeys.KEY_SHOWPRINTJOBDIALOGAFTERPRINT_MODE_SUCCESSFUL):
					# show only when succesfull
					if ("success" == printJobModelStatus):
						printJobItem = TransformPrintJob2JSON.transformPrintJobModel(printJobModel, self._file_manager)
				elif (showDisplayAfterPrintMode == SettingsKeys.KEY_SHOWPRINTJOBDIALOGAFTERPRINT_MODE_FAILED):
					if ("failed" == printJobModelStatus or "canceled" == printJobModelStatus):
						printJobItem = TransformPrintJob2JSON.transformPrintJobModel(printJobModel, self._file_manager)

				else:
					# always
					printJobItem = TransformPrintJob2JSON.transformPrintJobModel(printJobModel, self._file_manager)

			# inform client for a reload (and show dialog)
			payLoadForClient = {
				"action": "printFinished",
				"printJobItem": printJobItem  # if present then the editor dialog is shown
			}
			# self._sendDataToClient(payLoadForClient)
			self._logger.info("----- ... End PrintJob captured! -----")
		else:
			self._logger.info("----- ... PrintJob not captured, because not activated! -----")

		# capture the technical log and send updated model to browser
		self._resetableFileLogHandler.stopLogging()
		if (databaseId is not None):
			techLog = self._resetableFileLogHandler.readLogContent()
			lastPrintJobModel = self._databaseManager.loadPrintJob(databaseId)
			lastPrintJobModel.technicalLog = techLog
			self._databaseManager.updatePrintJob(lastPrintJobModel)
			if (payload is not None):
				if (payLoadForClient["printJobItem"] is not None):
					printJobItem = TransformPrintJob2JSON.transformPrintJobModel(lastPrintJobModel, self._file_manager)
					payLoadForClient["printJobItem"] = printJobItem
				self._sendDataToClient(payLoadForClient)
			pass

		return databaseId


	def _grabImage(self, payload):
		self._logger.info("----- Start grab Image/thumbnail... -----")
		isCameraPresent = self._cameraManager.isCamaraSnahotURLPresent()

		takeSnapshotAfterPrint = self._settings.get_boolean([SettingsKeys.SETTINGS_KEY_TAKE_SNAPSHOT_AFTER_PRINT])
		takeSnapshotOnGCode = self._settings.get_boolean([SettingsKeys.SETTINGS_KEY_TAKE_SNAPSHOT_ON_GCODE_COMMAND])
		takeSnapshotOnM118Code = self._settings.get_boolean([SettingsKeys.SETTINGS_KEY_TAKE_SNAPSHOT_ON_M118_COMMAND])
		takeThumbnailAfterPrint = self._settings.get_boolean(
			[SettingsKeys.SETTINGS_KEY_TAKE_PLUGIN_THUMBNAIL_AFTER_PRINT])

		preferedThumbnail = self._settings.get(
			[SettingsKeys.SETTINGS_KEY_PREFERED_IMAGE_SOURCE]) == SettingsKeys.KEY_PREFERED_IMAGE_SOURCE_THUMBNAIL

		isThumbnailPresent = self._isThumbnailPresent(payload)

		# - No Image
		if (not takeSnapshotAfterPrint and not takeSnapshotOnGCode and not takeSnapshotOnM118Code and not takeThumbnailAfterPrint):
			self._logger.info("No image should be taken")
			return
		# - Only Thumbnail
		if (takeThumbnailAfterPrint and not takeSnapshotAfterPrint and not takeSnapshotOnGCode and not takeSnapshotOnM118Code):
			# Try to take the thumbnail
			self._logger.info("Try to take thumbnail, because afterprint/gcode not selected")
			self._takeThumbnailImage(payload)
			return
		if (takeThumbnailAfterPrint and isThumbnailPresent and preferedThumbnail):
			self._logger.info("Try to take thumbnail, because thumbnail is present and prefered")
			self._takeThumbnailImage(payload)
			return
		# - Only Camera
		if (takeSnapshotAfterPrint and not takeThumbnailAfterPrint):
			if (not isCameraPresent):
				self._logger.info("Camera Snapshot is selected but no camera url is available")
				return
			self._logger.info("Try capturing snapshot asyc from camera, because thumbnail not selected")
			self._cameraManager.takeSnapshotAsync(
				CameraManager.buildSnapshotFilename(self._currentPrintJobModel.printStartDateTime),
				self._sendErrorMessageToClient,
				self._sendReloadTableToClient
			)

			return
		# - Camera
		if (isCameraPresent and takeSnapshotAfterPrint):
			self._logger.info("Try capturing snapshot asyc")
			self._cameraManager.takeSnapshotAsync(
				CameraManager.buildSnapshotFilename(self._currentPrintJobModel.printStartDateTime),
				self._sendErrorMessageToClient,
				self._sendReloadTableToClient
			)


	def _isThumbnailPresent(self, payload):
		return self._takeThumbnailImage(payload, storeImage=False)


	def _takeThumbnailImage(self, payload, storeImage=True):
		self._logger.info("Try reading Thumbnail")
		thumbnailPresent = False
		metadata = self._file_manager.get_metadata(payload["origin"], payload["path"])
		# check if available
		if (hasattr(self._file_manager, "has_thumbnail") and self._file_manager.has_thumbnail(payload["origin"], payload["path"])):
			# Thumbnail provided by OctoPrint itself (2.x only)
			thumbnailPresent = True
			if (storeImage):
				thumbnail = self._file_manager.read_thumbnail(payload["origin"], payload["path"])[1]
				self._cameraManager.takeOctoPrintThumbnail(CameraManager.buildSnapshotFilename(self._currentPrintJobModel.printStartDateTime), thumbnail)
				thumbnail.close()
		elif ("thumbnail" in metadata):
			# Thumbnail provided by another plugin
			thumbnailPresent = self._cameraManager.takePluginThumbnail(
				CameraManager.buildSnapshotFilename(self._currentPrintJobModel.printStartDateTime),
				metadata["thumbnail"],
				storeImage=storeImage
			)
		else:
			self._logger.warning("Thumbnail not found in print metadata")

		if (not thumbnailPresent):
			self._logger.warning("Thumbnail not found for cameraManager")
		else:
			self._logger.info("Thumbnail was captured from metadata")

		return thumbnailPresent


	#######################################################################################   OP - HOOKs

	def on_after_startup(self):
		# check if needed plugins were available
		self._checkAndLoadThirdPartyPluginInfos(False) # don't inform the client, because client is maybe not opened

		# helpers = self._plugin_manager.get_helpers("multicam")
		# if helpers and "get_webcam_profiles" in helpers:
		# 	get_webcam_profiles = helpers["get_webcam_profiles"]
		#
		# 	self.camProfiles = get_webcam_profiles()

		logFilename = os.path.join(self._settings.getBaseFolder("logs"), "plugin_PrintJobHistory_singlePrintJob.log")
		formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
		self._resetableFileLogHandler = ResetAbleLogFileHandler(logFilename, "octoprint.plugins.PrintJobHistory")
		self._resetableFileLogHandler.setFormatter(formatter)
		# self._resetableFileLogHandler.assignLoggerNameToCapture("octoprint.plugins.PrintJobHistory")
		# add to current plugin logger
		pluginLogger = logging.getLogger(self._logger.name)
		pluginLogger.addHandler(self._resetableFileLogHandler)

		self._logger.info("on after startup done")
		pass




	# Listen to all  g-code which where already sent to the printer (thread: comm.sending_thread)
	def on_sentGCodeHook(self, comm_instance, phase, cmd, cmd_type, gcode, *args, **kwargs):
		# take snapshot an gcode command
		if (self._settings.get_boolean([SettingsKeys.SETTINGS_KEY_TAKE_SNAPSHOT_ON_GCODE_COMMAND])):
			gcodePattern = self._settings.get([SettingsKeys.SETTINGS_KEY_TAKE_SNAPSHOT_GCODE_COMMAND_PATTERN])
			if (gcodePattern is not None and len(gcodePattern.strip()) != 0):
				commandAsString = StringUtils.to_native_str(cmd)
				if (commandAsString.startswith(gcodePattern)):
					self._logger.info("M117 message for taking snapshot detected. Try to capture image!")
					self._cameraManager.takeSnapshotAsync(
						CameraManager.buildSnapshotFilename(self._currentPrintJobModel.printStartDateTime),
						self._sendErrorMessageToClient
					)
				pass
		pass

	# Receiving commands from the printer
	# Terminal: !!DEBUG:send //action:pjhTakeSnapshot
	def on_receivedActionHook(self, comm, line, action, *args, **kwargs):
		if (action == "pjhTakeSnapshot"):
			self._logger.info("Received \"pjhTakeSnapshot\" action from printer")

			if (self._settings.get_boolean(
				[SettingsKeys.SETTINGS_KEY_TAKE_SNAPSHOT_ON_M118_COMMAND])):
				self._logger.info("M118 command enabled for taking snapshot. Try to capture image!")
				if (self._currentPrintJobModel is not None and self._currentPrintJobModel.printStartDateTime is not None):

					if (self._cameraManager.isCamaraSnahotURLPresent()):
						# Try to take the snapshot
						self._cameraManager.takeSnapshotAsync(
							CameraManager.buildSnapshotFilename(self._currentPrintJobModel.printStartDateTime),
							self._sendErrorMessageToClient)
					else:
						self._logger.error("Camera Snapshot is selected, but no camera url is available")
				else:
					self._logger.error("M118 command detected, but there is no printjob started!")
			else:
				self._logger.info("Take Snapshot via M118 command is not activated in plugin settings")

		return

	def additional_permissions_hook(self):
		from octoprint.access import ADMIN_GROUP
		from octoprint.access import USER_GROUP
		return [
			{
				"key": "DELETE_JOB",
				"name": "Delete print jobs",
				"description": "Allows to delete print jobs from history",
				"default_groups": [ADMIN_GROUP, USER_GROUP],
				"roles": ["print_operator"],
			},
			{
				"key": "EDIT_JOB",
				"name": "Edit print jobs",
				"description": "Allows to edit print jobs",
				"default_groups": [ADMIN_GROUP, USER_GROUP],
				"roles": ["print_operator"],
			},
		]

	# Main Event-Handler
	def on_event(self, event, payload):

		# print("****************************")
		# print(event)
		# print("****************************")
		# WebBrowser opened
		# TODO when OP 1.8.0 is release, implement FileMoved event
		if ("FileMoved" == event):
			print("******* MOVED ***********")

		if Events.CLIENT_OPENED == event:

			# - Check if all needed Plugins are available, if not modale dialog to User
			self._checkAndLoadThirdPartyPluginInfos(True)

			# Send plugin storage information
			# - Storage
			if (hasattr(self, "_databaseManager")):
				databaseFileLocation = self._databaseManager.getDatabaseFileLocation()
				snapshotFileLocation = self._cameraManager.getSnapshotFileLocation()
				# Eval currencySymbol
				currencySymbol = self._settings.get([SettingsKeys.SETTINGS_KEY_CURRENCY_SYMBOL])
				currencyFormat = self._settings.get([SettingsKeys.SETTINGS_KEY_CURRENCY_FORMAT])
				if (self._isCostEstimationInstalledAndEnabled()):
					currencySymbol = self._costEstimationPluginImplementation._settings.get(["currency"])
					currencyFormat = self._costEstimationPluginImplementation._settings.get(["currencyFormat"])
				self._sendDataToClient(dict(action="initalData",
											databaseFileLocation=databaseFileLocation,
											snapshotFileLocation=snapshotFileLocation,
											isPrintHistoryPluginAvailable=self._printHistoryPluginImplementation is not None,
											isSpoolManagerInstalled = self._isSpoolManagerInstalledAndEnabled(),
											isSpoolmanInstalled = self._isSpoolmanInstalledAndEnabled(),
											isFilamentManagerInstalled = self._isFilamentManagerInstalledAndEnabled(),
											isCostEstimationPluginAvailable = self._isCostEstimationInstalledAndEnabled(),
											isPreHeatPluginAvailable = self._isPreHeatInstalledAndEnabled(),
											currencySymbol = currencySymbol,
											currencyFormat = currencyFormat,
											))

			# - Show last Print-Dialog
			if self._settings.get_boolean([SettingsKeys.SETTINGS_KEY_SHOW_PRINTJOB_DIALOG_AFTER_PRINT]):
				printJobId = self._settings.get_int([SettingsKeys.SETTINGS_KEY_SHOW_PRINTJOB_DIALOG_AFTER_PRINT_JOB_ID])
				if (printJobId is not None):
					try:
						printJobModel = self._databaseManager.loadPrintJob(printJobId)

						# check the correct status
						printJobItem = None
						showDisplayAfterPrintMode = self._settings.get([SettingsKeys.SETTINGS_KEY_SHOWPRINTJOBDIALOGAFTERPRINT_MODE])
						printJobModelStatus = printJobModel.printStatusResult

						if (showDisplayAfterPrintMode == SettingsKeys.KEY_SHOWPRINTJOBDIALOGAFTERPRINT_MODE_SUCCESSFUL):
							# show only when succesfull
							if ("success" == printJobModelStatus):
								printJobItem = TransformPrintJob2JSON.transformPrintJobModel(printJobModel, self._file_manager)
						elif (showDisplayAfterPrintMode == SettingsKeys.KEY_SHOWPRINTJOBDIALOGAFTERPRINT_MODE_FAILED):
							if ("failed" == printJobModelStatus or "canceled" == printJobModelStatus):
								printJobItem = TransformPrintJob2JSON.transformPrintJobModel(printJobModel, self._file_manager)
						else:
							# always
							printJobItem = TransformPrintJob2JSON.transformPrintJobModel(printJobModel, self._file_manager)

						payload = {
							"action": "showPrintJobDialogAfterClientConnection",
							"printJobItem": printJobItem
						}
						self._sendDataToClient(payload)
					except DoesNotExist:
						self._settings.remove([SettingsKeys.SETTINGS_KEY_SHOW_PRINTJOB_DIALOG_AFTER_PRINT_JOB_ID])

			self._checkForMissingFilamentTracking()

		elif Events.PRINT_STARTED == event:
			self._printJobStarted(payload)

		elif "DisplayLayerProgress_layerChanged" == event or event == "DisplayLayerProgress_heightChanged":
			self._updatePrintJobModelWithLayerHeightInfos(payload)

		elif Events.PRINT_DONE == event:
			self._printJobFinished("success", payload)
		elif Events.PRINT_FAILED == event:
			if not self.alreadyCanceled:
				self._printJobFinished("failed", payload)
		elif Events.PRINT_CANCELLED == event:
			self.alreadyCanceled = True
			self._printJobFinished("canceled", payload)
		pass


	def on_settings_save(self, data):
		# default save function
		octoprint.plugin.SettingsPlugin.on_settings_save(self, data)

		# reinitialize some fields
		sqlLoggingEnabled = self._settings.get_boolean([SettingsKeys.SETTINGS_KEY_SQL_LOGGING_ENABLED])
		self._databaseManager.showSQLLogging(sqlLoggingEnabled)


	##~~ SimpleApiPlugin mixin
	def is_api_protected(self):
		return True

	# to allow the frontend to trigger an GET call
	def on_api_get(self, request):
		if len(request.values) != 0:
			action = request.values["action"]

			# deceide if you want the reset function in you settings dialog
			if "isResetSettingsEnabled" == action:
				return flask.jsonify(enabled="true")

			if "resetSettings" == action:
				self._settings.set([], self.get_settings_defaults())
				self._settings.save()
				return flask.jsonify(self.get_settings_defaults())
		pass


	##~~ SettingsPlugin mixin
	def get_settings_defaults(self):
		settings = dict(
			installed_version=self._plugin_version
		)
		## General
		settings[SettingsKeys.SETTINGS_KEY_PLUGIN_DEPENDENCY_CHECK] = True
		settings[SettingsKeys.SETTINGS_KEY_SHOW_PRINTJOB_DIALOG_AFTER_PRINT] = True
		settings[SettingsKeys.SETTINGS_KEY_SHOW_PRINTJOB_DIALOG_AFTER_PRINT_JOB_ID] = None
		settings[SettingsKeys.SETTINGS_KEY_SHOWPRINTJOBDIALOGAFTERPRINT_MODE] = SettingsKeys.KEY_SHOWPRINTJOBDIALOGAFTERPRINT_MODE_SUCCESSFUL
		settings[SettingsKeys.SETTINGS_KEY_CAPTURE_PRINTJOBHISTORY_MODE] = SettingsKeys.KEY_CAPTURE_PRINTJOBHISTORY_MODE_SUCCESSFUL
		# settings[SettingsKeys.SETTINGS_KEY_SELECTED_FILAMENTTRACKER_PLUGIN] = SettingsKeys.KEY_SELECTED_SPOOLMANAGER_PLUGIN
		settings[SettingsKeys.SETTINGS_KEY_SELECTED_FILAMENTTRACKER_PLUGIN] = SettingsKeys.KEY_SELECTED_NONE_PLUGIN
		settings[SettingsKeys.SETTINGS_KEY_NO_NOTIFICATION_FILAMENTTRACKERING_PLUGIN_SELECTION] = False

		settings[SettingsKeys.SETTINGS_KEY_SLICERSETTINGS_KEYVALUE_EXPRESSION] = ";(.*)=(.*)\n;   (.*),(.*)"
		settings[SettingsKeys.SETTINGS_KEY_SINGLE_PRINTJOB_REPORT_TEMPLATENAME] = SettingsKeys.SETTINGS_DEFAULT_VALUE_SINGLE_PRINTJOB_REPORT_TEMPLATENAME
		settings[SettingsKeys.SETTINGS_KEY_MULTI_PRINTJOB_REPORT_TEMPLATENAME] = SettingsKeys.SETTINGS_DEFAULT_VALUE_MULTI_PRINTJOB_REPORT_TEMPLATENAME

		settings[SettingsKeys.SETTINGS_KEY_CURRENCY_SYMBOL] = "€"
		settings[SettingsKeys.SETTINGS_KEY_CURRENCY_FORMAT] = "%v %s"


		## Camera
		settings[SettingsKeys.SETTINGS_KEY_TAKE_SNAPSHOT_AFTER_PRINT] = True
		settings[SettingsKeys.SETTINGS_KEY_TAKE_PLUGIN_THUMBNAIL_AFTER_PRINT] = True
		settings[SettingsKeys.SETTINGS_KEY_TAKE_SNAPSHOT_ON_M118_COMMAND] = False
		settings[SettingsKeys.SETTINGS_KEY_TAKE_SNAPSHOT_ON_GCODE_COMMAND] = False
		settings[SettingsKeys.SETTINGS_KEY_TAKE_SNAPSHOT_GCODE_COMMAND_PATTERN] = "M117 Snap"
		settings[SettingsKeys.SETTINGS_KEY_PREFERED_IMAGE_SOURCE] = SettingsKeys.KEY_PREFERED_IMAGE_SOURCE_THUMBNAIL

		## Temperature
		settings[SettingsKeys.SETTINGS_KEY_DEFAULT_TOOL_ID] = "tool0"
		settings[SettingsKeys.SETTINGS_KEY_TAKE_TEMPERATURE_FROM_PREHEAT] = True
		settings[SettingsKeys.SETTINGS_KEY_DELAY_READING_TEMPERATURE_FROM_PRINTER] = 60

		## Export / Import
		settings[SettingsKeys.SETTINGS_KEY_IMPORT_CSV_MODE] = SettingsKeys.KEY_IMPORTCSV_MODE_APPEND

		settings["datbaseSettings"] = {
			"useExternal": "true",
			"type": "postgres",
			"host": "localhost",
			"port": 5432,
			"databaseName": "PrintJobDatabase",
			"user": "Olli",
			"password": "illO"
		}

		## Debugging
		settings[SettingsKeys.SETTINGS_KEY_SQL_LOGGING_ENABLED] = False

		## Other stuff
		settings[SettingsKeys.SETTINGS_KEY_LAST_PLUGIN_DEPENDENCY_CHECK] = None


		# ## Storage
		# if (hasattr(self,"_databaseManager") == True):
		# 	settings[SettingsKeys.SETTINGS_KEY_DATABASE_PATH] = self._databaseManager.getDatabaseFileLocation()
		# 	settings[SettingsKeys.SETTINGS_KEY_SNAPSHOT_PATH] = self._cameraManager.getSnapshotFileLocation()
		# else:
		# 	settings[SettingsKeys.SETTINGS_KEY_DATABASE_PATH] = ""
		# 	settings[SettingsKeys.SETTINGS_KEY_SNAPSHOT_PATH] = ""

		return settings


	##~~ TemplatePlugin mixin
	def get_template_configs(self):
		return [
			dict(type="tab", name="Print Job History"),
			dict(type="settings", custom_bindings=True, name="Print Job History")
		]

	def is_template_autoescaped(self):
		return True


	##~~ AssetPlugin mixin
	def get_assets(self):
		# Define your plugin's asset files to automatically include in the
		# core UI here.
		return dict(
			# "js/ulog.full.min.js",
			js=[
				"js/PrintJobHistory.js",
				"js/PrintJobHistory-APIClient.js",
				"js/PrintJobHistory-PluginCheckDialog.js",
				"js/PrintJobHistory-EditJobDialog.js",
				"js/PrintJobHistory-ImportDialog.js",
				"js/PrintJobHistory-StatisticDialog.js",
				"js/PrintJobHistory-SettingsCompareDialog.js",
				"js/PrintJobHistory-ComponentFactory.js",
				"js/quill.min.js",
				"js/dayjs.min.js",
				"js/plugin/customParseFormat.min.js",
				"js/jquery.datetimepicker.full.min.js",
				"js/TableItemHelper.js",
				"js/ResetSettingsUtilV3.js"],
			css=[
				"css/PrintJobHistory.css",
				"css/jquery.datetimepicker.min.css",
				"css/quill.snow.css"],
			less=["less/PrintJobHistory.less"]
		)


	##~~ Softwareupdate hook
	def get_update_information(self):
		# Define the configuration for your plugin to use with the Software Update
		# Plugin here. See https://github.com/foosel/OctoPrint/wiki/Plugin:-Software-Update
		# for details.
		return dict(
			PrintJobHistory=dict(
				displayName="PrintJobHistory Plugin",
				displayVersion=self._plugin_version,

				# version check: github repository
				type="github_release",

				user="vojtakaniok",
				repo="OctoPrint-PrintJobHistory",
				current=self._plugin_version,

				stable_branch=dict(
					name="Only Release",
					branch="main",
					comittish=["main"]
				),
				prerelease_branches=[
					# dict(
					# 	name="Release & Candidate",
					# 	branch="pre-release",
					# 	comittish=["pre-release", "main"],
					# ),
					dict(
						name="Release & in development",
						branch="dev",
						comittish=["dev", "main"],
					)
				],

				# update method: pip
				pip="https://github.com/vojtakaniok/OctoPrint-PrintJobHistory/releases/download/{target_version}/main.zip"
			)
		)


	# Increase upload-size (default 100kb) for uploading images
	def bodysize_hook(self, current_max_body_sizes, *args, **kwargs):
		return [("POST", r"/upload/", 20 * 1024 * 1024)]  # size in bytes


	# # For Streaming I need a special ResponseHandler
	# def route_hook(self, server_routes, *args, **kwargs):
	# 	from octoprint.server.util.tornado import LargeResponseHandler, UrlProxyHandler, path_validation_factory
	# 	from octoprint.util import is_hidden_path
	#
	# 	return [
	# 		# (r'myvideofeed', StreamHandler, dict(url=self._settings.global_get(["webcam", "snapshot"]),
	# 		# 									 as_attachment=True)),
	# 		(r"mysnapshot", UrlProxyHandler, dict(url=self._settings.global_get(["webcam", "snapshot"]),
	# 											 as_attachment=True))
	# 	]


# If you want your plugin to be registered within OctoPrint under a different name than what you defined in setup.py
# ("OctoPrint-PluginSkeleton"), you may define that here. Same goes for the other metadata derived from setup.py that
# can be overwritten via __plugin_xyz__ control properties. See the documentation for that.
# Name is used in the left Settings-Menue
__plugin_name__ = "PrintJobHistory"
__plugin_pythoncompat__ = ">=2.7,<4"

def __plugin_load__():
	global __plugin_implementation__
	__plugin_implementation__ = PrintJobHistoryPlugin()

	global __plugin_hooks__
	__plugin_hooks__ = {
		# "octoprint.server.http.routes": __plugin_implementation__.route_hook,
		# "octoprint.comm.protocol.gcode.sent": __plugin_implementation__.on_sentGCodeHook,
		"octoprint.comm.protocol.gcode.sending": __plugin_implementation__.on_sentGCodeHook,
		"octoprint.comm.protocol.action": __plugin_implementation__.on_receivedActionHook,
		"octoprint.access.permissions": __plugin_implementation__.additional_permissions_hook,
		"octoprint.server.http.bodysize": __plugin_implementation__.bodysize_hook,
		"octoprint.plugin.softwareupdate.check_config": __plugin_implementation__.get_update_information
	}

# # filamentAnalyseDict = fileData["analysis"]["filament"]
# filamentAnalyseDict = {u'tool4': {u'volume': 185.20129656279946, u'length': 76997.75167999369},
#  u'tool3': {u'volume': 0.0, u'length': 0.0}, u'tool2': {u'volume': 0.0, u'length': 0.0},
#  u'tool1': {u'volume': 0.0, u'length': 0.0}, u'tool0': {u'volume': 0.0, u'length': 0.0}}
# #
# print (len(filamentAnalyseDict))
# for toolId in filamentAnalyseDict:
# 	# print(toolId)
# 	length = filamentAnalyseDict[toolId]["length"]
# 	volumne = filamentAnalyseDict[toolId]["volume"]
# 	print(toolId + " " + str(length))
