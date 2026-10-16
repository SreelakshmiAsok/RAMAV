#!/usr/bin/env bash
curl -s -X POST http://localhost:8000/api/demo/security | python3 -m json.tool
