@echo off

setlocal

cd /d "E:\myPrivateSpace\nocturne_memory\backend"

set "TMP=E:\myPrivateSpace\nocturne_memory\.tmp\runtime"

set "TEMP=E:\myPrivateSpace\nocturne_memory\.tmp\runtime"

set "NOCTURNE_NO_UI=1"

set "NOCTURNE_DB_URL="

if not exist "%TMP%" mkdir "%TMP%"

"D:\Python\python.exe" "E:\myPrivateSpace\nocturne_memory\backend\mcp_server.py"

