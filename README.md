# Overview

To use Kicksaw's integration app, install this package (insert package link here) in your Salesforce organization.

Once your org is ready to-go, instantiate the `KicksawSalesforce` class and operate like normal, but note:

- You need to pass the AWS Step Function payload to the class when instantiating
- Instantiating the client creates an execution object in Salesforce, unless you pass it the id of an already existing execution object
- All of your bulk operations will have their errors parsed and error objects created in Salesforce if applicable

```python
from kicksaw_integration_utils import KicksawSalesforce

step_function_payload = {}
salesforce = KicksawSalesforce(step_function_payload)

salesforce.bulk.Account.upsert()
```

For code examples, please refer to `tests/test_integrations.py`.
