import json

from kicksaw_integration_utils.salesforce_client import (
    SfClient,
    SFBulkHandler as BaseSFBulkHandler,
    SFBulkType as BaseSFBulkType,
)


class SFBulkType(BaseSFBulkType):
    def _bulk_operation(self, operation, data, external_id_field=None, **kwargs):
        response = super()._bulk_operation(
            operation, data, external_id_field=external_id_field, **kwargs
        )
        self._process_errors(
            data,
            response,
            operation,
            external_id_field,
            kwargs.get("batch_size", 10000),
        )
        return response

    def _process_errors(self, data, response, operation, external_id_field, batch_size):
        """
        Parse the results of a bulk upload call and push error objects into Salesforce
        """
        object_name = self.object_name
        upsert_key = external_id_field

        assert len(data) == len(
            response
        ), f"{len(data)} (data) and {len(response)} (response) have different lengths!"
        assert (
            KicksawSalesforce.execution_object_id
        ), f"KicksawSalesforce.execution_object_id is not set"

        error_objects = list()
        for payload, record in zip(data, response):
            if not record["success"]:
                for error in record["errors"]:
                    error_object = {
                        f"{KicksawSalesforce.NAMESPACE}{KicksawSalesforce.EXECUTION}": KicksawSalesforce.execution_object_id,
                        f"{KicksawSalesforce.NAMESPACE}{KicksawSalesforce.OPERATION}": operation,
                        f"{KicksawSalesforce.NAMESPACE}{KicksawSalesforce.SALESFORCE_OBJECT}": object_name,
                        f"{KicksawSalesforce.NAMESPACE}{KicksawSalesforce.ERROR_CODE}": error[
                            "statusCode"
                        ],
                        f"{KicksawSalesforce.NAMESPACE}{KicksawSalesforce.ERROR_MESSAGE}": error[
                            "message"
                        ],
                        f"{KicksawSalesforce.NAMESPACE}{KicksawSalesforce.UPSERT_KEY}": upsert_key,
                        # TODO: Add test for bulk inserts where upsert key is None
                        f"{KicksawSalesforce.NAMESPACE}{KicksawSalesforce.UPSERT_KEY_VALUE}": payload.get(
                            upsert_key
                        ),
                        f"{KicksawSalesforce.NAMESPACE}{KicksawSalesforce.OBJECT_PAYLOAD}": json.dumps(
                            payload
                        ),
                    }
                    error_objects.append(error_object)

        # Push error details to Salesforce
        error_client = BaseSFBulkType(
            f"{KicksawSalesforce.NAMESPACE}{KicksawSalesforce.ERROR}",
            self.bulk_url,
            self.headers,
            self.session,
        )
        error_client.insert(error_objects, batch_size=batch_size)


class SFBulkHandler(BaseSFBulkHandler):
    def __getattr__(self, name):
        """
        Source code from this library's SFBulkType
        """
        return SFBulkType(
            object_name=name,
            bulk_url=self.bulk_url,
            headers=self.headers,
            session=self.session,
        )


class KicksawSalesforce(SfClient):
    """
    Salesforce client to use when the integration is using
    the "Integration App" (our Salesforce package for integrations)

    This combines the simple-salesforce client and the
    Orchestrator client from this library
    """

    execution_object_id = None

    NAMESPACE = ""

    # Integration object
    INTEGRATION = "Integration__c"

    # Integration execution object stuff
    EXECUTION = "IntegrationExecution__c"
    EXECUTION_PAYLOAD = "ExecutionPayload__c"  # json input for step function
    EXECUTION_INTEGRATION = "Integration__c"

    # Integration error object stuff
    ERROR = "IntegrationError__c"
    OPERATION = "Operation__c"
    SALESFORCE_OBJECT = "Object__c"
    ERROR_CODE = "ErrorCode__c"
    ERROR_MESSAGE = "ErrorMessage__c"
    UPSERT_KEY = "UpsertKey__c"
    UPSERT_KEY_VALUE = "UpsertKeyValue__c"
    OBJECT_PAYLOAD = "ObjectPayload__c"

    def __init__(
        self, integration_name: str, payload: dict, execution_object_id: str = None
    ):
        """
        In addition to instantiating the simple-salesforce client,
        we also decide whether or not to create an execution object
        based on whether or not we've provided an id for this execution
        """
        self._integration_name = integration_name
        self._execution_payload = payload
        super().__init__()
        self._prepare_execution(execution_object_id)

    def _prepare_execution(self, execution_object_id):
        if not execution_object_id:
            execution_object_id = self._create_execution_object()
        KicksawSalesforce.execution_object_id = execution_object_id

    def _create_execution_object(self):
        """
        Pushes an execution object to Salesforce, returning the
        Salesforce id of the object we just created

        Adds the payload for the first step of the step function
        as a field on the execution object
        """
        results = self.query(
            f"Select Id From {KicksawSalesforce.NAMESPACE}{KicksawSalesforce.INTEGRATION} Where Name = '{self._integration_name}'"
        )

        assert (
            results["totalSize"] == 1
        ), f"No {KicksawSalesforce.NAMESPACE}{KicksawSalesforce.INTEGRATION} named {self._integration_name}"

        record = results["records"][0]
        record_id = record["Id"]

        execution = {
            f"{KicksawSalesforce.NAMESPACE}{KicksawSalesforce.EXECUTION_INTEGRATION}": record_id,
            f"{KicksawSalesforce.NAMESPACE}{KicksawSalesforce.EXECUTION_PAYLOAD}": json.dumps(
                self._execution_payload
            ),
        }
        response = getattr(
            self, f"{KicksawSalesforce.NAMESPACE}{KicksawSalesforce.EXECUTION}"
        ).create(execution)
        return response["id"]

    def get_execution_object(self):
        return getattr(
            self, f"{KicksawSalesforce.NAMESPACE}{KicksawSalesforce.EXECUTION}"
        ).get(self.execution_object_id)

    def __getattr__(self, name):
        """
        This is the source code from simple salesforce, but we swap out
        SFBulkHandler with our own
        """
        if name == "bulk":
            # Deal with bulk API functions
            return SFBulkHandler(
                self.session_id, self.bulk_url, self.proxies, self.session
            )
        return super().__getattr__(name)
