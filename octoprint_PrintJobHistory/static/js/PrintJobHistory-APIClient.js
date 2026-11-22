

function PrintJobHistoryAPIClient(pluginId, baseUrl) {

    this.pluginId = pluginId;
    this.baseUrl = baseUrl;


    // see https://gomakethings.com/how-to-build-a-query-string-from-an-object-with-vanilla-js/
    var _buildRequestQuery = function (data) {
        // If the data is already a string, return it as-is
        if (typeof (data) === 'string') return data;

        // Create a query array to hold the key/value pairs
        var query = [];

        // Loop through the data object
        for (var key in data) {
            if (data.hasOwnProperty(key)) {

                // Encode each key and value, concatenate them into a string, and push them to the array
                query.push(encodeURIComponent(key) + '=' + encodeURIComponent(data[key]));
            }
        }
        // Join each item in the array with a `&` and return the resulting string
        return query.join('&');

    };

    this.getDownloadDatabaseUrl = function(exportType){
        return "./plugin/" + this.pluginId + "/downloadDatabase";
    }

    this.getSampleCSVUrl = function(){
        return "./plugin/" + this.pluginId + "/sampleCSV";
    }

    this.getExportUrl = function(exportType){
        return "./plugin/" + this.pluginId + "/exportPrintJobHistory/" + exportType;
    }

    this.getProxiedSnapshotUrl = function(snapshotFilename){
        http://localhost:5000/plugin/PrintJobHistory/mysnapshot
        return "./plugin/" + this.pluginId + "/mysnapshot";
    }

    this.getSnapshotUrl = function(snapshotFilename){
        //http://localhost:5000/plugin/PrintJobHistory/printJobSnapshot/20191003-153311
        return "./plugin/" + this.pluginId + "/printJobSnapshot/" + snapshotFilename;
    }

    this.callCreateSingleReportUrl = function(databaseId){
        //http://localhost:5000/plugin/PrintJobHistory/singlePrintJobReport/5
        return "./plugin/" + this.pluginId + "/singlePrintJobReport/" + databaseId;
    }

    this.callCreateMultiReportUrl = function (tableQuery){
        query = _buildRequestQuery(tableQuery);
        urlToCall = this.baseUrl + "./plugin/"+this.pluginId+"/multiPrintJobReport?"+query;
        return urlToCall;
    }

    this.getMultiReportUrl = function(databaseId){
        //http://localhost:5000/plugin/PrintJobHistory/multiPrintJobReport/5
        return "./plugin/" + this.pluginId + "/multiPrintJobReport/" + databaseId;
    }

    this.getPrintJobReportTemplateUrl = function(reportType){
        //http://localhost:5000/plugin/PrintJobHistory/downloadSinglePrintJobReportTemplate
        return "./plugin/" + this.pluginId + "/downloadPrintJobReportTemplate/" + reportType;
    }

    this.uploadSnapshotUrl = function(snapshotFilename){
        //http://localhost:5000/plugin/PrintJobHistory/printJobSnapshot/20191003-153311
        return "./plugin/" + this.pluginId + "/upload/snapshot/" + snapshotFilename;
    }

    // load FILTERED/SORTED PrintJob-Items
    this.callLoadPrintJobsByQuery = function (tableQuery, responseHandler){
        query = _buildRequestQuery(tableQuery);
        urlToCall = "plugin/"+this.pluginId+"/loadPrintJobHistoryByQuery?"+query;
        OctoPrint.get(urlToCall).done(function( data ){
            responseHandler(data)
            //shoud be done by the server to make sure the server is informed countdownDialog.modal('hide');
            //countdownDialog.modal('hide');
            //countdownCircle = null;
        });
    }
    // load STATISTICS PrintJob-Items
    this.callLoadStatisticsByQuery = function (tableQuery, responseHandler){
        query = _buildRequestQuery(tableQuery);
        urlToCall = "plugin/"+this.pluginId+"/loadStatisticByQuery?"+query;
        OctoPrint.get(urlToCall).done(function( data ){
            responseHandler(data)
            //shoud be done by the server to make sure the server is informed countdownDialog.modal('hide');
            //countdownDialog.modal('hide');
            //countdownCircle = null;
        });
    }

    // load COMPARE SlicerSettigs
    this.callCompareSlicerSettings = function (selectedJobDatabaseIds, responseHandler){
        urlToCall = "plugin/"+this.pluginId+"/compareSlicerSettings/?databaseIds="+selectedJobDatabaseIds;
        OctoPrint.get(urlToCall).done(function( data ){
            responseHandler(data)
            //shoud be done by the server to make sure the server is informed countdownDialog.modal('hide');
            //countdownDialog.modal('hide');
            //countdownCircle = null;
        });
    }

    this.callDeleteDatabase = function(responseHandler){
        OctoPrint.delete("plugin/"+this.pluginId+"/deleteDatabase").done(function( data ){
            responseHandler(data)
            //shoud be done by the server to make sure the server is informed countdownDialog.modal('hide');
            //countdownDialog.modal('hide');
            //countdownCircle = null;
        });
    }

    // remove PrintJob-Item
    this.callStorePrintJob = function (databaseId, printJobItem, responseHandler){
        jsonPayload = ko.toJSON(printJobItem)

        OctoPrint.put("plugin/" + this.pluginId + "/storePrintJob/" + databaseId, jsonPayload, {
            contentType: "application/json; charset=UTF-8"
        }).done(function( data ){
            responseHandler();
        });
    }

    // remove PrintJob-Item
    this.callRemovePrintJob = function (databaseId, responseHandler){
        OctoPrint.delete("plugin/" + this.pluginId + "/removePrintJob/" + databaseId).done(function( data ){
            responseHandler();
        });
    }

    // select PrintJob-Item for printing
    this.callSelectPrintJobForPrinting = function (databaseId, responseHandler){
        OctoPrint.put("plugin/" + this.pluginId + "/selectPrintJobForPrint/" + databaseId).done(function( data ){
            responseHandler();
        });
    }

    // confirm the message dialog
    this.callConfirmMessageDialog =  function (){
        OctoPrint.put("plugin/"+ this.pluginId +"/confirmMessageDialog").done(function( data ){
            //responseHandler(data)
        });
    }

    // deactivate the Plugin/Check
    this.callDeactivatePluginCheck =  function (){
        OctoPrint.put("plugin/"+ this.pluginId +"/deactivatePluginCheck").done(function( data ){
            //responseHandler(data)
        });
    }


    this.callResetPrintJobReportTemplate =  function (reportType, responseHandler){
        OctoPrint.put("plugin/"+ this.pluginId +"/resetPrintJobReportTemplate/"+reportType).done(function( data ){
            responseHandler(data)
        });
    }

    this.callTakeSnapshot =  function (snapshotFilename, responseHandler){
        OctoPrint.put("plugin/"+ this.pluginId +"/takeSnapshot/"+snapshotFilename).always(function( data ){
            responseHandler(data)
        });
    }

    // delete snapshotImage
    this.callDeleteSnapshotImage =  function (snapshotFilename, responseHandler){
        OctoPrint.delete("plugin/"+ this.pluginId +"/deleteSnapshotImage/"+snapshotFilename).done(function( data ){
            responseHandler(data)
        });
    }

    this.callForceCloseEditDialog = function(responseHandler){
        OctoPrint.put("plugin/"+this.pluginId+"/forceCloseEditDialog").done(function( data ){
            responseHandler(data)
            //shoud be done by the server to make sure the server is informed countdownDialog.modal('hide');
            //countdownDialog.modal('hide');
            //countdownCircle = null;
        });
    }


}
