#!/usr/bin/env bash
curl -s -X POST http://localhost:8000/api/demo/repair | python3 -m json.tool
