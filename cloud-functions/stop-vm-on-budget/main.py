import base64
import json

import functions_framework
from google.cloud import compute_v1

PROJECT = "glossy-reserve-153120"
ZONE = "us-central1-a"
INSTANCE = "myfeeds"


@functions_framework.cloud_event
def stop_vm_on_budget(cloud_event):
    """Stop the VM when spending reaches the budget amount."""
    data = base64.b64decode(cloud_event.data["message"]["data"]).decode()
    notification = json.loads(data)

    cost = notification.get("costAmount", 0)
    budget = notification.get("budgetAmount", 0)

    if cost < budget:
        print(f"Cost ${cost:.2f} under budget ${budget:.2f}, no action")
        return

    print(f"Cost ${cost:.2f} >= budget ${budget:.2f}, stopping {INSTANCE}")
    client = compute_v1.InstancesClient()
    client.stop(project=PROJECT, zone=ZONE, instance=INSTANCE)
    print(f"Stop request sent for {INSTANCE}")
