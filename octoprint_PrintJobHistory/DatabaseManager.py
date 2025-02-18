# coding=utf-8
from __future__ import absolute_import

import datetime
import logging
import os
import shutil
import sqlite3

from octoprint_PrintJobHistory.WrappedLoggingHandler import WrappedLoggingHandler
from octoprint_PrintJobHistory.api import TransformPrintJob2JSON
from octoprint_PrintJobHistory.common import StringUtils
from octoprint_PrintJobHistory.models.CostModel import CostModel
from octoprint_PrintJobHistory.models.FilamentModel import FilamentModel
from octoprint_PrintJobHistory.models.PrintJobModel import PrintJobModel
from octoprint_PrintJobHistory.models.PluginMetaDataModel import PluginMetaDataModel
# from octoprint_PrintJobHistory.models.PrintJobSpoolMapModel import PrintJobSpoolMapModel
from octoprint_PrintJobHistory.models.TemperatureModel import TemperatureModel
from peewee import *


FORCE_CREATE_TABLES = False
SQL_LOGGING = False

CURRENT_DATABASE_SCHEME_VERSION = 8

# List all Models
MODELS = [PluginMetaDataModel, PrintJobModel, FilamentModel, TemperatureModel, CostModel]


class DatabaseManager(object):

	def __init__(self, parentLogger, sqlLoggingEnabled):

		self.sqlLoggingEnabled = sqlLoggingEnabled
		self._logger = logging.getLogger(parentLogger.name + "." + self.__class__.__name__)
		self._sqlLogger = logging.getLogger(parentLogger.name + "." + self.__class__.__name__ + ".SQL")

		self._database = None
		self._databaseFileLocation = None
		self._sendDataToClient = None

	################################################################################################## private functions

	def _createOrUpgradeSchemeIfNecessary(self):
		schemeVersionFromDatabaseModel = None
		try:
			schemeVersionFromDatabaseModel = PluginMetaDataModel.get(PluginMetaDataModel.key == PluginMetaDataModel.KEY_DATABASE_SCHEME_VERSION)
			pass
		except Exception as e:
			errorMessage = str(e)
			if errorMessage.startswith("no such table"):

				self._logger.info("Create database-table, because didn't exists")
				self._createDatabaseTables()
			else:
				self._logger.error(str(e))

		if not schemeVersionFromDatabaseModel == None:
			currentDatabaseSchemeVersion = int(schemeVersionFromDatabaseModel.value)
			if (currentDatabaseSchemeVersion < CURRENT_DATABASE_SCHEME_VERSION):
				# evautate upgrade steps (from 1-2 , 1...6)
				self._logger.info("We need to upgrade the database scheme from: '" + str(currentDatabaseSchemeVersion) + "' to: '" + str(CURRENT_DATABASE_SCHEME_VERSION) + "'")

				try:
					self.backupDatabaseFile(self._databasePath)
					self._upgradeDatabase(currentDatabaseSchemeVersion, CURRENT_DATABASE_SCHEME_VERSION)
				except Exception as e:
					self._logger.error("Error during database upgrade!!!!")
					self._logger.exception(e)
					return
				self._logger.info("Database-scheme successfully upgraded.")
		pass

	def _upgradeDatabase(self,currentDatabaseSchemeVersion, targetDatabaseSchemeVersion):

		migrationFunctions = [self._upgradeFrom1To2,
							  self._upgradeFrom2To3,
							  self._upgradeFrom3To4,
							  self._upgradeFrom4To5,
							  self._upgradeFrom5To6,
							  self._upgradeFrom6To7,
							  self._upgradeFrom7To8,
							  self._upgradeFrom8To9,
							  self._upgradeFrom9To10
							  ]

		for migrationMethodIndex in range(currentDatabaseSchemeVersion -1, targetDatabaseSchemeVersion -1):
			self._logger.info("Database migration from '" + str(migrationMethodIndex + 1) + "' to '" + str(migrationMethodIndex + 2) + "'")
			migrationFunctions[migrationMethodIndex]()
			pass
		pass

	def _upgradeFrom9To10(self):
		self._logger.info(" Starting 9 -> 10")
		self._logger.info(" Successfully 9 -> 10")
		pass

	def _upgradeFrom8To9(self):
		self._logger.info(" Starting 8 -> 9")
		self._logger.info(" Successfully 8 -> 9")
		pass

	def _upgradeFrom7To8(self):
		self._logger.info(" Starting 7 -> 8")
		# What is changed:
		# - PrintJobModel:
		# 	- Add Column: technicalLog

		connection = sqlite3.connect(self._databaseFileLocation)
		cursor = connection.cursor()

		sql = """
		PRAGMA foreign_keys=off;
		BEGIN TRANSACTION;

			ALTER TABLE 'pjh_printjobmodel' ADD 'technicalLog' TEXT;

				UPDATE 'pjh_pluginmetadatamodel' SET value=8 WHERE key='databaseSchemeVersion';
		COMMIT;
		PRAGMA foreign_keys=on;
		"""
		cursor.executescript(sql)

		connection.close()

		self._logger.info(" Successfully 7 -> 8")
		pass

	def _upgradeFrom6To7(self):
		self._logger.info(" Starting 6 -> 7")

		connection = sqlite3.connect(self._databaseFileLocation)
		cursor = connection.cursor()

		## Changeset
		# - NEW CostModel
		# - Droping costUnit, because now there is a general plugin-setting

		# 			ALTER TABLE "pjh_filamentmodel" DROP COLUMN "spoolCostUnit"; Not working for DB Release < 3.30.0 (offical 3.35.0)
		sql = """
		PRAGMA foreign_keys=off;
		BEGIN TRANSACTION;

			CREATE TABLE "pjh_costmodel" ("databaseId" INTEGER NOT NULL PRIMARY KEY,
			"created" DATETIME NOT NULL,
			"printJob_id" INTEGER NOT NULL,
			"totalCosts" REAL,
			"filamentCost" REAL,
			"electricityCost" REAL,
			"printerCost" REAL,
			"otherCostLabel" VARCHAR(255),
			"otherCost" REAL,
			"withDefaultSpoolValues" INTEGER,
			FOREIGN KEY ("printJob_id") REFERENCES "pjh_printjobmodel" ("databaseId") ON DELETE CASCADE);

			UPDATE 'pjh_pluginmetadatamodel' SET value=7 WHERE key='databaseSchemeVersion';
		COMMIT;
		PRAGMA foreign_keys=on;
		"""
		cursor.executescript(sql)

		connection.close()

		self._logger.info(" Successfully 6 -> 7")
		pass

	def _upgradeFrom5To6(self):
		self._logger.info(" Starting 5 -> 6")
		# What is changed:
		# - FilamentModel:
		# 	- renameing:
		# 		profileVendor -> vendor
		# 		spoolWeight -> weight
		#   (ALTER TABLE spo_spoolmodel RENAME COLUMN encloserTemperature to enclosureTemperature; not working SQLite did not support the ALTER TABLE RENAME COLUMN syntax before version 3.25.0.
		# 	see https://www.sqlitetutorial.net/sqlite-rename-column/#:~:text=SQLite%20did%20not%20support%20the,the%20version%20lower%20than%203.25.)

		connection = sqlite3.connect(self._databaseFileLocation)
		cursor = connection.cursor()

		sql = """
		PRAGMA foreign_keys=off;
		BEGIN TRANSACTION;

			UPDATE 'pjh_filamentmodel' SET toolId='total' where toolId is NULL;

			UPDATE 'pjh_pluginmetadatamodel' SET value=6 WHERE key='databaseSchemeVersion';
		COMMIT;
		PRAGMA foreign_keys=on;
		"""
		cursor.executescript(sql)

		connection.close()
		self._logger.info(" Successfully 5 -> 6")
		pass

	def _upgradeFrom4To5(self):
		self._logger.info(" Starting 4 -> 5")
		# What is changed:
		# - FilamentModel:
		# 	- renameing:
		# 		profileVendor -> vendor
		# 		spoolWeight -> weight
		#   (ALTER TABLE spo_spoolmodel RENAME COLUMN encloserTemperature to enclosureTemperature; not working SQLite did not support the ALTER TABLE RENAME COLUMN syntax before version 3.25.0.
		# 	see https://www.sqlitetutorial.net/sqlite-rename-column/#:~:text=SQLite%20did%20not%20support%20the,the%20version%20lower%20than%203.25.)

		connection = sqlite3.connect(self._databaseFileLocation)
		cursor = connection.cursor()

		sql = """
		PRAGMA foreign_keys=off;
		BEGIN TRANSACTION;

			ALTER TABLE 'pjh_filamentmodel' RENAME TO 'pjh_filamentmodel_old';

			CREATE TABLE "pjh_filamentmodel" (
				"databaseId" INTEGER NOT NULL PRIMARY KEY,
				"created" DATETIME NOT NULL,
				"printJob_id" INTEGER NOT NULL,
				"vendor" VARCHAR(255),
				"diameter" REAL,
				"density" REAL,
				"material" VARCHAR(255),
				"spoolName" VARCHAR(255),
				"spoolCost" REAL,
				"spoolCostUnit" VARCHAR(255),
				"weight" REAL,
				"usedLength" REAL,
				"calculatedLength" REAL,
				"usedWeight" REAL,
				"usedCost" REAL,
				'toolId' VARCHAR(255),
				FOREIGN KEY ("printJob_id") REFERENCES "pjh_printjobmodel" ("databaseId") ON DELETE CASCADE);

			INSERT INTO 'pjh_filamentmodel'
			(databaseId, created, printJob_id, vendor, diameter, density, material, spoolName, spoolCost, spoolCostUnit, weight, usedLength, calculatedLength, usedWeight, usedCost, toolId)
			 SELECT databaseId, created, printJob_id, profileVendor, diameter, density, material, spoolName, spoolCost, spoolCostUnit, spoolWeight, usedLength, calculatedLength, usedWeight, usedCost, toolId
			 FROM 'pjh_filamentmodel_old';

			DROP TABLE 'pjh_filamentmodel_old';

			UPDATE 'pjh_pluginmetadatamodel' SET value=5 WHERE key='databaseSchemeVersion';
		COMMIT;
		PRAGMA foreign_keys=on;
		"""
		cursor.executescript(sql)

		connection.close()
		self._logger.info(" Successfully 4 -> 5")
		pass

	def _upgradeFrom3To4(self):
		self._logger.info(" Starting 3 -> 4")
		# What is changed:
		# - FilamentModel:
		# 	- add toolId = CharField(null=True) # since V4	--> old values must be total, because no information about single tool

		connection = sqlite3.connect(self._databaseFileLocation)
		cursor = connection.cursor()

		sql = """
		PRAGMA foreign_keys=off;
		BEGIN TRANSACTION;

			ALTER TABLE 'pjh_filamentmodel' ADD 'toolId' VARCHAR(255);
			UPDATE 'pjh_filamentmodel' SET toolId='total';

			UPDATE 'pjh_pluginmetadatamodel' SET value=4 WHERE key='databaseSchemeVersion';
		COMMIT;
		PRAGMA foreign_keys=on;
		"""
		cursor.executescript(sql)

		connection.close()
		self._logger.info(" Successfully 3 -> 4")
		pass

	def _upgradeFrom2To3(self):
		self._logger.info(" Starting 2 -> 3")
		# What is changed:
		# - PrintJobModel:
		# 	- Add Column: slicerSettingsAsText

		connection = sqlite3.connect(self._databaseFileLocation)
		cursor = connection.cursor()

		sql = """
		PRAGMA foreign_keys=off;
		BEGIN TRANSACTION;

			ALTER TABLE 'pjh_printjobmodel' ADD 'slicerSettingsAsText' TEXT;

				UPDATE 'pjh_pluginmetadatamodel' SET value=3 WHERE key='databaseSchemeVersion';
		COMMIT;
		PRAGMA foreign_keys=on;
		"""
		cursor.executescript(sql)

		connection.close()
		self._logger.info(" Successfully 2 -> 3")
		pass

	def _upgradeFrom1To2(self):
		self._logger.info(" Starting 1 -> 2")
		# What is changed:
		# - PrintJobModel: Add Column fileOrigin
		# - FilamentModel: Several ColumnTypes were wrong
		connection = sqlite3.connect(self._databaseFileLocation)
		cursor = connection.cursor()

		sql = """
		PRAGMA foreign_keys=off;
		BEGIN TRANSACTION;

			ALTER TABLE 'pjh_printjobmodel' ADD 'fileOrigin' VARCHAR(255);

			ALTER TABLE 'pjh_filamentmodel' RENAME TO 'pjh_filamentmodel_old';
			CREATE TABLE "pjh_filamentmodel" (
				"databaseId" INTEGER NOT NULL PRIMARY KEY,
				"created" DATETIME NOT NULL,
				"printJob_id" INTEGER NOT NULL,
				"profileVendor" VARCHAR(255),
				"diameter" REAL,
				"density" REAL,
				"material" VARCHAR(255),
				"spoolName" VARCHAR(255),
				"spoolCost" VARCHAR(255),
				"spoolCostUnit" VARCHAR(255),
				"spoolWeight" REAL,
				"usedLength" REAL,
				"calculatedLength" REAL,
				"usedWeight" REAL,
				"usedCost" REAL,
				FOREIGN KEY ("printJob_id") REFERENCES "pjh_printjobmodel" ("databaseId") ON DELETE CASCADE);

				INSERT INTO 'pjh_filamentmodel' (databaseId, created, printJob_id, profileVendor, diameter, density, material, spoolName, spoolCost, spoolCostUnit, spoolWeight, usedLength, calculatedLength, usedWeight, usedCost)
				  SELECT databaseId, created, printJob_id, profileVendor, diameter, density, material, spoolName, spoolCost, spoolCostUnit, spoolWeight, usedLength, calculatedLength, usedWeight, usedCost
				  FROM 'pjh_filamentmodel_old';

				DROP TABLE 'pjh_filamentmodel_old';

				UPDATE 'pjh_pluginmetadatamodel' SET value=2 WHERE key='databaseSchemeVersion';
		COMMIT;
		PRAGMA foreign_keys=on;
		"""
		cursor.executescript(sql)

		connection.close()
		pass



	def _createDatabaseTables(self):
		self._database.connect(reuse_if_open=True)
		self._database.drop_tables(MODELS)
		self._database.create_tables(MODELS)

		PluginMetaDataModel.create(key=PluginMetaDataModel.KEY_DATABASE_SCHEME_VERSION, value=CURRENT_DATABASE_SCHEME_VERSION)
		self._database.close()
		self._logger.info("Database tables created")





	################################################################################################### public functions

	# return:{
	#  connected: True
	#  tablesPresent: True
	#  schemeVersion: 2
	# }
	# else {
	#  errorMessage: "BOOOMMM"
	def testConnection(self, type, host, port,  databaeName, username, password):

		databaseToTest = None
		if ("postgres" == type):
			databaseToTest = PostgresqlDatabase(
				databaeName,
				user=username,
				password=password,
				host=host,
				port=port
			)
		else:
			databaseToTest = SqliteDatabase(self._databaseFileLocation)
		DatabaseManager.db = databaseToTest
		databaseToTest.bind(MODELS)
		# self._logger.info("Check if database-scheme upgrade needed.")
		# self._createOrUpgradeSchemeIfNecessary()

		schemeVersion = None
		jobCount = None
		try:
			databaseToTest.connect(reuse_if_open=True)

			schemeVersionFromDatabaseModel = None
			try:
				# scheme version
				schemeVersionFromDatabaseModel = PluginMetaDataModel.get(
					PluginMetaDataModel.key == PluginMetaDataModel.KEY_DATABASE_SCHEME_VERSION)
				schemeVersionFromDatabaseModel = int(schemeVersionFromDatabaseModel.value)

				# job count
				jobCount = self.countPrintJobsByQuery({
					"filterName" : "all"
				})
				pass
			except Exception as e:
				errorMessage = str(e)
				if errorMessage.startswith("no such table"):
					pass

			databaseToTest.close()


		except Exception as e:
			# Because this block of code is wrapped with "atomic", a
			# new transaction will begin automatically after the call
			# to rollback().
			errorMessage =  str(e);
			self._logger.warning("Test Database-Connection failed:" +errorMessage)
			return {
				"error": errorMessage
			}

		return {
			"schemeVersion": schemeVersionFromDatabaseModel,
			"jobCount": jobCount
		}


	# datapasePath '/Users/o0632/Library/Application Support/OctoPrint/data/PrintJobHistory'
	def initDatabase(self, databasePath, sendErrorMessageToClient):
		self._logger.info("Init DatabaseManager")
		self.sendErrorMessageToClient = sendErrorMessageToClient
		self._databasePath = databasePath
		self._databaseFileLocation = os.path.join(databasePath, "printJobHistory.db")

		self._logger.info("Using database in: " + str(self._databaseFileLocation))

		import logging
		logger = logging.getLogger('peewee')
		# we need only the single logger without parent
		logger.parent = None
		# logger.addHandler(logging.StreamHandler())
		# activate SQL logging on PEEWEE side and on PLUGIN side

		# logger.setLevel(logging.DEBUG)
		# self._sqlLogger.setLevel(logging.DEBUG)
		self.showSQLLogging(self.sqlLoggingEnabled)

		wrappedHandler = WrappedLoggingHandler(self._sqlLogger)
		logger.addHandler(wrappedHandler)

		self._createDatabase(FORCE_CREATE_TABLES)

		pass

	def showSQLLogging(self, enabled):
		import logging
		logger = logging.getLogger('peewee')

		if (enabled):
			logger.setLevel(logging.DEBUG)
			self._sqlLogger.setLevel(logging.DEBUG)
		else:
			logger.setLevel(logging.ERROR)
			self._sqlLogger.setLevel(logging.ERROR)


	def backupDatabaseFile(self, backupFolder):
		now = datetime.datetime.now()
		currentDate = now.strftime("%Y%m%d-%H%M")
		currentSchemeVersion = "unknown"
		try:
			currentSchemeVersion = PluginMetaDataModel.get(PluginMetaDataModel.key == PluginMetaDataModel.KEY_DATABASE_SCHEME_VERSION)
			if (currentSchemeVersion != None):
				currentSchemeVersion = str(currentSchemeVersion.value)
		except Exception as e:
			self._logger.exception("Could not read databasescheme version:" + str(e))
		backupDatabaseFileName = "printJobHistory-backup-"+currentDate+"-V"+currentSchemeVersion +".db"
		backupDatabaseFilePath = os.path.join(backupFolder, backupDatabaseFileName)
		if not os.path.exists(backupDatabaseFilePath):
			shutil.copy(self._databaseFileLocation, backupDatabaseFilePath)
			self._logger.info("Backup of printjobhistory database created '"+backupDatabaseFilePath+"'")
		else:
			self._logger.warning("Backup of printjobhistory database ('" + backupDatabaseFilePath + "') is already present. No backup created.")
		return backupDatabaseFilePath


	def _createDatabase(self, forceCreateTables):
		self._database = SqliteDatabase(self._databaseFileLocation, check_same_thread=False)
		DatabaseManager.db = self._database
		self._database.bind(MODELS)

		if forceCreateTables:
			self._logger.info("Creating new database-tables, because FORCE == TRUE!")
			self._createDatabaseTables()
		else:
			# check, if we need an scheme upgrade
			self._logger.info("Check if database-scheme upgrade needed.")
			self._createOrUpgradeSchemeIfNecessary()
		self._logger.info("Done DatabaseManager.createDatabase")


	def getDatabaseFileLocation(self):
		return self._databaseFileLocation

	def reCreateDatabase(self):
		self._logger.info("ReCreating Database")
		self._createDatabase(True)

	def insertPrintJob(self, printJobModel):
		databaseId = None
		with self._database.atomic() as transaction:  # Opens new transaction.
			try:
				printJobModel.save()
				databaseId = printJobModel.get_id()
				# save all relations
				# - Filament
				for filamentModel in printJobModel.getFilamentModels():
					filamentModel.printJob = printJobModel
					filamentModel.save()
				# - Temperature
				for temperatureModel in printJobModel.getTemperatureModels():
					temperatureModel.printJob = printJobModel
					temperatureModel.save()
				# - Costs
				if (printJobModel.getCosts() != None):
					printJobModel.getCosts().save()

				# do expicit commit
				transaction.commit()
			except Exception as e:
				# Because this block of code is wrapped with "atomic", a
				# new transaction will begin automatically after the call
				# to rollback().
				transaction.rollback()
				databaseId = None
				self._logger.exception("Could not insert printJob into database:" + str(e))

				self.sendErrorMessageToClient("PJH-DatabaseManager", "Could not insert the printjob into the database. See OctoPrint.log for details!")
			pass

		return databaseId

	def updatePrintJob(self, printJobModel, rollbackHandler = None):
		with self._database.atomic() as transaction:  # Opens new transaction.
			try:
				printJobModel.save()
				databaseId = printJobModel.get_id()
				# save all relations
				# - Filament
				for filamentModel in printJobModel.getFilamentModels():
					filamentModel.save()

				# # - Temperature not needed for an update
				# for temperatureModel in printJobModel.getTemperatureModels():
				# 	temperatureModel.printJob = printJobModel
				# 	temperatureModel.save()

				# - Costs
				if (printJobModel.getCosts() != None):
					printJobModel.getCosts().save()
			except Exception as e:
				# Because this block of code is wrapped with "atomic", a
				# new transaction will begin automatically after the call
				# to rollback().
				transaction.rollback()
				self._logger.exception("Could not update printJob into database:" + str(e))
				rollbackHandler()
				self.sendErrorMessageToClient("PJH-DatabaseManager", "Could not update the printjob ('"+ printJobModel.fileName +"') into the database. See OctoPrint.log for details!")
			pass

	#
	def calculatePrintJobsStatisticByQuery(self, tableQuery):

		printJobCount = 0
		duration = 0
		length = 0.0
		weight = 0.0
		fileSize = 0
		statusDict = dict()
		materialDict = dict()
		spoolDict = dict()
		firstDate = None
		lastDate = None
		newTableQuery = tableQuery.copy()
		newTableQuery["sortColumn"] = "printStartDateTime"
		newTableQuery["sortOrder"] = "asc"
		newTableQuery["from"] = 0
		newTableQuery["to"] = 999999
		allJobModels = self.loadPrintJobsByQuery(newTableQuery)

		for job in allJobModels:
			printJobCount = printJobCount + 1
			if (firstDate == None):
				firstDate = job.printStartDateTime
			if (job.printEndDateTime != None):
				lastDate = job.printEndDateTime
			tempJobFileSize = job.fileSize
			if (tempJobFileSize == None):
				tempJobFileSize = 0
			fileSize = fileSize + tempJobFileSize
			duration = duration + job.duration
			statusResult = job.printStatusResult

			if (statusResult in statusDict):
				currentCount = statusDict[statusResult]
				currentCount = currentCount + 1
				statusDict[statusResult] = currentCount
			else:
				statusDict[statusResult] = 1

			allFilaments = job.getFilamentModels()
			if allFilaments != None:
				for filla in allFilaments:
					if filla.toolId == "total":
						# exclude totals, otherwise everything is counted twice
						continue
					if (StringUtils.isEmpty(filla.usedLength) == False):
						length = length + filla.usedLength
					if (StringUtils.isEmpty(filla.usedWeight) == False):
						weight = weight + filla.usedWeight

					if (StringUtils.isEmpty(filla.spoolName) == False):
						# spoolsSet.add(filla.spoolName)
						if (filla.spoolName in spoolDict):
							currentCount = spoolDict[filla.spoolName]
							currentCount = currentCount + 1
							spoolDict[filla.spoolName] = currentCount
						else:
							spoolDict[filla.spoolName] = 1

					if (StringUtils.isEmpty(filla.material) == False):
						# materialsSet.add(filla.material)
						if (filla.material in materialDict):
							currentCount = materialDict[filla.material]
							currentCount = currentCount + 1
							materialDict[filla.material] = currentCount
						else:
							materialDict[filla.material] = 1

		# do formatting
		queryString = self._buildQueryString(tableQuery)
		lastDateString = ""
		if (lastDate != None):
			lastDateString = lastDate.strftime('%d.%m.%Y %H:%M')
		fromToString = firstDate.strftime('%d.%m.%Y %H:%M') + " - " + lastDateString
		durationString = StringUtils.secondsToText(duration)
		lengthString = self._buildLengthString(length)
		weightString = self._buildWeightString(weight)
		statusString = self._buildStatusString(statusDict)
		materialString = self._buildDictlString(materialDict)
		spoolString = self._buildDictlString(spoolDict)
		fileSizeString = StringUtils.get_formatted_size(fileSize)
		return {
			"printJobCount": printJobCount,
			"query": queryString,
			"fromToDate": fromToString,
			"duration": durationString,
			"usedLength": lengthString,
			"usedWeight": weightString,
			"fileSize": fileSizeString,
			"printStatus": statusString,
		    "material": materialString,
			"spools": spoolString
		}

	def _buildLengthString(self, length):
		lengthString = StringUtils.formatFloatSave("{:.02f}", TransformPrintJob2JSON.convertMM2M(length), "-")
		if (lengthString != "-"):
			lengthString = lengthString + "m"
		return lengthString

	def _buildWeightString(self, weight):
		weightString = StringUtils.formatFloatSave("{:.02f}", weight, "-")
		if (weightString != "-"):
			weightString = weightString + "g"
		return weightString

	def _buildQueryString(self, tableQuery):
		result = ""
		if ("startDate" in tableQuery):
			startDate = tableQuery["startDate"]
			endDate = tableQuery["endDate"]
			if (len(startDate) > 0 and len(endDate) > 0):
				# EndDay + 1
				# startDateTime = datetime.datetime.strptime(startDate, "%d.%m.%Y")
				# endDateTime = datetime.datetime.strptime(endDate, "%d.%m.%Y") + datetime.timedelta(days=1)
				result = "Timeframe: " + startDate + " - " + endDate + ","

		if (len(result)== 0):
			result = "Timeframe: all,"

		if (tableQuery["filterName"] == "onlySuccess"):
			result = result + " Filter: only successful"
		if (tableQuery["filterName"] == "onlyFailed"):
			result = result + " Filter: only failed"
		if (tableQuery["filterName"] == "all"):
			result = result + " Filter: all"

		return result

	def _buildStatusString(self, statusDict):
		result = ""
		if ("success" in statusDict):
			result = "success(" + str(statusDict["success"]) + ")"
		if ("canceled" in statusDict):
			if (len(result) != 0):
				result += ", "
			result = result + "canceled(" + str(statusDict["canceled"]) + ")"
		if ("failed" in statusDict):
			if (len(result) != 0):
				result += ", "
			result = result + "failed(" + str(statusDict["failed"]) + ")"

		return result

	def _buildDictlString(self, myDict):
		result = ""

		keys = myDict.keys()
		for key in keys:
			count = myDict[key]
			if (len(result) != 0):
				result = result + ", "
			result = result + key + "(" + str(count) + ")"

		if (len(result) == 0):
			result = "-"
		return result


	def countPrintJobsByQuery(self, tableQuery):

		# filterName = tableQuery["filterName"]

		myQuery = PrintJobModel.select()
		myQuery = self._addTableQueryToSelect(myQuery, tableQuery)
		# self._addTableQueryToSelect(myQuery, tableQuery)
		# if (filterName == "onlySuccess"):
		# 	myQuery = myQuery.where(PrintJobModel.printStatusResult == "success")
		# elif (filterName == "onlyFailed"):
		# 	myQuery = myQuery.where(PrintJobModel.printStatusResult != "success")

		return myQuery.count()


	def loadPrintJobsByQuery(self, tableQuery):
		offset = int(tableQuery["from"])
		limit = int(tableQuery["to"])
		# sortColumn = tableQuery["sortColumn"]
		# sortOrder = tableQuery["sortOrder"]
		# filterName = tableQuery["filterName"]

		# dont use join "Kartesischs-Produkt" myQuery = PrintJobModel.select().join(FilamentModel).offset(offset).limit(limit)
		myQuery = PrintJobModel.select().offset(offset).limit(limit)
		myQuery = self._addTableQueryToSelect(myQuery, tableQuery)
		# if (filterName == "onlySuccess"):
		# 	myQuery = myQuery.where(PrintJobModel.printStatusResult == "success")
		# elif (filterName == "onlyFailed"):
		# 	myQuery = myQuery.where(PrintJobModel.printStatusResult != "success")
		#
		# if ("printStartDateTime" == sortColumn):
		# 	if ("desc" == sortOrder):
		# 		myQuery = myQuery.order_by(PrintJobModel.printStartDateTime.desc())
		# 	else:
		# 		myQuery = myQuery.order_by(PrintJobModel.printStartDateTime)
		# if ("fileName" == sortColumn):
		# 	if ("desc" == sortOrder):
		# 		myQuery = myQuery.order_by(PrintJobModel.fileName.desc())
		# 	else:
		# 		myQuery = myQuery.order_by(PrintJobModel.fileName)
		# if ("startDate" in tableQuery):
		# 	startDate = tableQuery["startDate"]
		# 	endDate = tableQuery["endDate"]
		# 	if (len(startDate) > 0 and len(endDate) > 0):
		# 		# EndDay + 1
		# 		startDateTime = datetime.datetime.strptime(startDate, "%d.%m.%Y")
		# 		endDateTime = datetime.datetime.strptime(endDate, "%d.%m.%Y") + datetime.timedelta(days=1)
		#
		# 		# myQuery = myQuery.where( (( PrintJobModel.printStartDateTime == startDate) | ( PrintJobModel.printStartDateTime >  startDate))
		# 		# 						 &
		# 		# 						 ((PrintJobModel.printStartDateTime == endDate) | ( PrintJobModel.printStartDateTime <  startDate)) )
		# 		myQuery = myQuery.where( ( ( PrintJobModel.printStartDateTime > startDateTime) & ( PrintJobModel.printStartDateTime < endDateTime))
		# 								 )

		return myQuery



	def _addTableQueryToSelect(self, myQuery, tableQuery):

		sortColumn = tableQuery["sortColumn"]
		sortOrder = tableQuery["sortOrder"]
		filterName = tableQuery["filterName"]

		# - status
		if (filterName == "onlySuccess"):
			myQuery = myQuery.where(PrintJobModel.printStatusResult == "success")
		elif (filterName == "onlyFailed"):
			myQuery = myQuery.where(PrintJobModel.printStatusResult != "success")
		# -sorting
		if ("printStartDateTime" == sortColumn):
			if ("desc" == sortOrder):
				myQuery = myQuery.order_by(PrintJobModel.printStartDateTime.desc())
			else:
				myQuery = myQuery.order_by(PrintJobModel.printStartDateTime)
		if ("fileName" == sortColumn):
			if ("desc" == sortOrder):
				myQuery = myQuery.order_by(fn.Lower(PrintJobModel.fileName).desc())
			else:
				myQuery = myQuery.order_by(fn.Lower(PrintJobModel.fileName))
		# - date range
		if ("startDate" in tableQuery):
			startDate = tableQuery["startDate"]
			endDate = tableQuery["endDate"]
			if (len(startDate) > 0 and len(endDate) > 0):
				# EndDay + 1
				startDateTime = datetime.datetime.strptime(startDate, "%d.%m.%Y")
				endDateTime = datetime.datetime.strptime(endDate, "%d.%m.%Y") + datetime.timedelta(days=1)

				# myQuery = myQuery.where( (( PrintJobModel.printStartDateTime == startDate) | ( PrintJobModel.printStartDateTime >  startDate))
				# 						 &
				# 						 ((PrintJobModel.printStartDateTime == endDate) | ( PrintJobModel.printStartDateTime <  startDate)) )
				myQuery = myQuery.where( ( ( PrintJobModel.printStartDateTime > startDateTime) & ( PrintJobModel.printStartDateTime < endDateTime))
										 )
		# - search query (only filename)
		if ("searchQuery" in tableQuery):
			searchQueryValue = tableQuery["searchQuery"]
			if (len(searchQueryValue) > 0):
				myQuery = myQuery.where(PrintJobModel.fileName.contains(searchQueryValue))
				pass
		return myQuery


	def loadSelectedPrintJobs(self, selectedDatabaseIds):
		selectedDatabaseIdsSplitted = selectedDatabaseIds.split(',')
		databaseArray = []

		for dbId in selectedDatabaseIdsSplitted:
			databaseArray.append(dbId)

		return PrintJobModel.select().where(PrintJobModel.databaseId << databaseArray).order_by(PrintJobModel.printStartDateTime.desc())


	def loadAllPrintJobs(self):
		return PrintJobModel.select().order_by(PrintJobModel.printStartDateTime.desc())

		# return PrintJobModel.select().offset(offset).limit(limit).order_by(PrintJobModel.printStartDateTime.desc())
		# all = PrintJobModel.select().join(FilamentModel).switch(PrintJobModel).join(TemperatureModel).order_by(PrintJobModel.printStartDateTime.desc())
		# allDict = all.dicts()
		# result = prefetch(allJobsQuery, FilamentModel)
		# return result
		# return allDict

	def loadPrintJob(self, databaseId):
		databaseIdAsInt = StringUtils.transformToIntOrNone(databaseId)
		if (databaseIdAsInt == None):
			self._logger.error("Could not load PrintJob, because not a valid databaseId '"+str(databaseId)+"' maybe not a number")
			return None
		return PrintJobModel.get_or_none(databaseIdAsInt)

	def deletePrintJob(self, databaseId):
		databaseIdAsInt = StringUtils.transformToIntOrNone(databaseId)
		if (databaseIdAsInt == None):
			self._logger.error("Could not delete PrintJob, because not a valid databaseId '"+str(databaseId)+"' maybe not a number")
			return None

		with self._database.atomic() as transaction:  # Opens new transaction.
			try:
				# first delete relations
				n = FilamentModel.delete().where(FilamentModel.printJob == databaseIdAsInt).execute()
				n = TemperatureModel.delete().where(TemperatureModel.printJob == databaseIdAsInt).execute()
				n = CostModel.delete().where(CostModel.printJob == databaseIdAsInt).execute()

				PrintJobModel.delete_by_id(databaseIdAsInt)
			except Exception as e:
				# Because this block of code is wrapped with "atomic", a
				# new transaction will begin automatically after the call
				# to rollback().
				transaction.rollback()
				self._logger.exception("Could not delete printJob from database:" + str(e))

				self.sendErrorMessageToClient("PJH-DatabaseManager", "Could not delete the printjob ('"+ str(databaseId) +"') from the database. See OctoPrint.log for details!")
			pass
