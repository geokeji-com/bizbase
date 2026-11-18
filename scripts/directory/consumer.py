#!/usr/bin/env python3
"""独立 API 消费者：只使用专属账号调用目录，不直接读取快照。"""
import argparse
import json
from pathlib import Path
import sys
import urllib.error
import urllib.parse
import urllib.request


def request(config, method, **params):
    base = config["base_url"].rstrip("/")
    if base != "http://127.0.0.1:8081":
        raise ValueError("This local acceptance client is restricted to the isolated endpoint")
    url = base + "/api/method/bizbase.api.directory." + method
    if params:
        url += "?" + urllib.parse.urlencode(params)
    req = urllib.request.Request(url, headers={"Authorization": "token " + config["api_key"] + ":" + config["api_secret"], "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as response:
            return json.load(response)["message"]
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"Directory request denied or unavailable (HTTP {error.code})") from None


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--credentials", type=Path, required=True)
    parser.add_argument("--customer-id")
    args = parser.parse_args()
    config = json.loads(args.credentials.read_text())
    customers = request(config, "list_customers")
    customer_id = args.customer_id
    if not customer_id:
        if not customers["items"]:
            print(json.dumps(customers, ensure_ascii=False))
            return
        customer_id = customers["items"][0]["customer_id"]
    subjects = request(config, "list_subjects", source_system=customers["meta"]["source_system"], customer_id=customer_id)
    print(json.dumps(subjects, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    try:
        main()
    except (RuntimeError, ValueError) as error:
        print(str(error), file=sys.stderr)
        sys.exit(1)
