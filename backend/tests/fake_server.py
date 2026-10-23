"""Protocol-level fixture; contains no model calls or real credentials."""
import json
import sys
import time

for line in sys.stdin:
    request = json.loads(line)
    if "method" not in request:
        if request.get("id") == "approval":
            print(json.dumps({"id": pending, "result": {"approved": "error" not in request}}), flush=True)
        continue
    method = request["method"]
    if "id" not in request:
        continue
    if method == "initialize":
        result = {"userAgent": "fake-test-server"}
    elif method == "account/read":
        result = {"account": {"type": "chatgpt", "email": "test.invalid", "planType": "plus"}}
    elif method == "account/rateLimits/read":
        result = {"rateLimitsByLimitId": {"codex": {"primary": {
            "usedPercent": 91, "windowDurationMins": 300, "resetsAt": int(time.time()) + 300},
            "secondary": {"usedPercent": 35, "windowDurationMins": 10080, "resetsAt": int(time.time()) + 6000}}}}
    elif method == "test/approval":
        pending = request["id"]
        print(json.dumps({"id": "approval", "method": "item/commandExecution/requestApproval", "params": {}}), flush=True)
        continue
    else:
        print(json.dumps({"id": request["id"], "error": {"code": -32601, "message": "unsupported"}}), flush=True)
        continue
    print(json.dumps({"id": request["id"], "result": result}), flush=True)
