#!/usr/bin/env bash
echo "Starting Verity - Fact Knowledge Layer on http://localhost:8080"
echo "Interactive API Documentation: http://localhost:8080/docs"
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload
